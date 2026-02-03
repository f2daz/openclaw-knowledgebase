"""Supabase client for OpenClaw Knowledgebase."""

import requests
from typing import Any, Iterator
from dataclasses import dataclass

from knowledgebase.config import get_config, Config
from knowledgebase.embeddings import get_embedding


@dataclass
class Source:
    """A knowledge source (URL or document)."""
    id: int
    url: str
    title: str | None
    source_type: str
    metadata: dict


@dataclass  
class Chunk:
    """A text chunk with optional embedding."""
    id: int
    source_id: int
    url: str
    chunk_number: int
    title: str | None
    content: str
    embedding: list[float] | None = None
    similarity: float | None = None


class KnowledgeBase:
    """Client for interacting with the knowledgebase."""
    
    def __init__(self, config: Config | None = None):
        """Initialize with optional config (uses global config if not provided)."""
        self.config = config or get_config()
        self._headers = {
            "apikey": self.config.supabase_key,
            "Authorization": f"Bearer {self.config.supabase_key}",
            "Content-Type": "application/json",
        }
    
    def _request(
        self,
        method: str,
        endpoint: str,
        data: dict | list | None = None,
        params: dict | None = None,
    ) -> requests.Response:
        """Make a request to Supabase REST API."""
        url = f"{self.config.supabase_url}/rest/v1/{endpoint}"
        return requests.request(
            method,
            url,
            headers=self._headers,
            json=data,
            params=params,
            timeout=30,
        )
    
    # --- Sources ---
    
    def add_source(
        self,
        url: str,
        title: str | None = None,
        source_type: str = "web",
        metadata: dict | None = None,
    ) -> Source | None:
        """Add a new source to the knowledgebase."""
        data = {
            "url": url,
            "title": title,
            "source_type": source_type,
            "metadata": metadata or {},
        }
        
        resp = self._request("POST", "kb_sources", data=data)
        if resp.status_code == 201:
            result = resp.json()
            if result:
                return Source(**result[0]) if isinstance(result, list) else Source(**result)
        return None
    
    def get_source(self, url: str) -> Source | None:
        """Get a source by URL."""
        resp = self._request("GET", "kb_sources", params={"url": f"eq.{url}"})
        if resp.status_code == 200:
            result = resp.json()
            if result:
                return Source(**result[0])
        return None
    
    def list_sources(self, limit: int = 100) -> list[Source]:
        """List all sources."""
        resp = self._request("GET", "kb_sources", params={"limit": str(limit)})
        if resp.status_code == 200:
            return [Source(**s) for s in resp.json()]
        return []
    
    # --- Chunks ---
    
    def add_chunk(
        self,
        source_id: int,
        url: str,
        chunk_number: int,
        content: str,
        title: str | None = None,
        embedding: list[float] | None = None,
    ) -> Chunk | None:
        """Add a chunk to the knowledgebase."""
        data = {
            "source_id": source_id,
            "url": url,
            "chunk_number": chunk_number,
            "content": content,
            "title": title,
            "embedding": embedding,
        }
        
        resp = self._request("POST", "kb_chunks", data=data)
        if resp.status_code == 201:
            result = resp.json()
            if result:
                return Chunk(**result[0]) if isinstance(result, list) else Chunk(**result)
        return None
    
    def add_chunks_batch(self, chunks: list[dict]) -> int:
        """Add multiple chunks at once. Returns number added."""
        if not chunks:
            return 0
            
        resp = self._request("POST", "kb_chunks", data=chunks)
        if resp.status_code in (200, 201):
            return len(chunks)
        return 0
    
    def get_chunks_without_embeddings(self, limit: int = 50) -> list[Chunk]:
        """Get chunks that need embeddings."""
        resp = self._request(
            "GET",
            "kb_chunks",
            params={
                "embedding": "is.null",
                "select": "id,source_id,url,chunk_number,title,content",
                "limit": str(limit),
            },
        )
        if resp.status_code == 200:
            return [Chunk(**c, embedding=None) for c in resp.json()]
        return []
    
    def update_chunk_embedding(self, chunk_id: int, embedding: list[float]) -> bool:
        """Update a chunk's embedding."""
        resp = self._request(
            "PATCH",
            "kb_chunks",
            data={"embedding": embedding},
            params={"id": f"eq.{chunk_id}"},
        )
        return resp.status_code in (200, 204)
    
    def count_chunks(self, with_embeddings: bool | None = None) -> int:
        """Count chunks, optionally filtered by embedding status."""
        params = {"select": "id"}
        if with_embeddings is True:
            params["embedding"] = "not.is.null"
        elif with_embeddings is False:
            params["embedding"] = "is.null"
        
        resp = self._request(
            "GET",
            "kb_chunks",
            params={**params, "limit": "1"},
        )
        resp.headers.get("content-range", "0-0/0")
        
        # Use HEAD with Prefer: count=exact for accurate count
        headers = {**self._headers, "Prefer": "count=exact"}
        resp = requests.head(
            f"{self.config.supabase_url}/rest/v1/kb_chunks",
            headers=headers,
            params=params,
            timeout=10,
        )
        
        content_range = resp.headers.get("content-range", "0-0/0")
        try:
            return int(content_range.split("/")[1])
        except (IndexError, ValueError):
            return 0
    
    # --- Search ---
    
    def search_semantic(
        self,
        query: str,
        limit: int | None = None,
        threshold: float | None = None,
    ) -> list[Chunk]:
        """
        Semantic search using vector similarity.
        
        Args:
            query: Search query text
            limit: Max results to return
            threshold: Minimum similarity threshold
            
        Returns:
            List of matching chunks with similarity scores
        """
        embedding = get_embedding(query)
        if not embedding:
            return []
        
        limit = limit or self.config.default_match_count
        threshold = threshold or self.config.similarity_threshold
        
        # Call the search function via RPC
        resp = requests.post(
            f"{self.config.supabase_url}/rest/v1/rpc/kb_search_semantic",
            headers=self._headers,
            json={
                "query_embedding": embedding,
                "match_count": limit,
                "similarity_threshold": threshold,
            },
            timeout=30,
        )
        
        if resp.status_code == 200:
            results = resp.json()
            return [
                Chunk(
                    id=r["id"],
                    source_id=0,  # Not returned by search
                    url=r["url"],
                    chunk_number=0,
                    title=r.get("title"),
                    content=r["content"],
                    similarity=r.get("similarity"),
                )
                for r in results
            ]
        return []
    
    def search_hybrid(
        self,
        query: str,
        limit: int | None = None,
        semantic_weight: float | None = None,
    ) -> list[Chunk]:
        """
        Hybrid search combining semantic and keyword search.
        
        Args:
            query: Search query text
            limit: Max results to return
            semantic_weight: Weight for semantic vs keyword (0-1)
            
        Returns:
            List of matching chunks with combined scores
        """
        embedding = get_embedding(query)
        if not embedding:
            return []
        
        limit = limit or self.config.default_match_count
        semantic_weight = semantic_weight or self.config.semantic_weight
        
        resp = requests.post(
            f"{self.config.supabase_url}/rest/v1/rpc/kb_search_hybrid",
            headers=self._headers,
            json={
                "query_embedding": embedding,
                "query_text": query,
                "match_count": limit,
                "semantic_weight": semantic_weight,
            },
            timeout=30,
        )
        
        if resp.status_code == 200:
            results = resp.json()
            return [
                Chunk(
                    id=r["id"],
                    source_id=0,
                    url=r["url"],
                    chunk_number=0,
                    title=r.get("title"),
                    content=r["content"],
                    similarity=r.get("combined_score"),
                )
                for r in results
            ]
        return []
    
    # --- Stats ---
    
    def stats(self) -> dict:
        """Get knowledgebase statistics."""
        resp = requests.post(
            f"{self.config.supabase_url}/rest/v1/rpc/kb_stats",
            headers=self._headers,
            json={},
            timeout=10,
        )
        
        if resp.status_code == 200:
            result = resp.json()
            if result:
                return result[0] if isinstance(result, list) else result
        return {
            "total_sources": 0,
            "total_chunks": 0,
            "chunks_with_embeddings": 0,
            "chunks_without_embeddings": 0,
        }
