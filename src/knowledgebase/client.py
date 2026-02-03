"""Supabase client for OpenClaw Knowledgebase."""

import requests
from typing import Any, Iterator
from dataclasses import dataclass

from knowledgebase.config import get_config, Config
from knowledgebase.embeddings import get_embedding


@dataclass
class Source:
    """A knowledge source (URL or document)."""
    id: int | str  # Can be int or UUID depending on schema
    url: str
    title: str | None = None
    source_type: str = "web"
    metadata: dict = None
    description: str | None = None  # Optional field
    created_at: str | None = None
    updated_at: str | None = None
    chunk_count: int = 0  # Populated by list_sources in web app
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass  
class Chunk:
    """A text chunk with optional embedding."""
    id: int | str  # Can be int or UUID
    source_id: int | str
    content: str
    chunk_index: int = 0  # Archon schema uses chunk_index
    metadata: dict | None = None
    embedding: list[float] | None = None
    similarity: float | None = None
    # Optional fields from search results (joined from source)
    url: str | None = None
    title: str | None = None
    
    # Alias for compatibility
    @property
    def chunk_number(self) -> int:
        return self.chunk_index


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
        # Table names with configurable prefix
        self._sources_table = f"{self.config.table_prefix}_sources"
        self._chunks_table = f"{self.config.table_prefix}_chunks"
    
    def _request(
        self,
        method: str,
        endpoint: str,
        data: dict | list | None = None,
        params: dict | None = None,
        return_representation: bool = False,
    ) -> requests.Response:
        """Make a request to Supabase REST API."""
        url = f"{self.config.supabase_url}/rest/v1/{endpoint}"
        headers = dict(self._headers)
        
        # For POST/PATCH, request the created/updated row back
        if return_representation and method in ("POST", "PATCH"):
            headers["Prefer"] = "return=representation"
        
        return requests.request(
            method,
            url,
            headers=headers,
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
        
        resp = self._request("POST", self._sources_table, data=data, return_representation=True)
        if resp.status_code == 201:
            try:
                result = resp.json()
                if result:
                    row = result[0] if isinstance(result, list) else result
                    known_fields = {"id", "url", "title", "source_type", "metadata", "description", "created_at", "updated_at"}
                    filtered = {k: v for k, v in row.items() if k in known_fields}
                    return Source(**filtered)
            except Exception:
                pass
        return None
    
    def get_source(self, url: str) -> Source | None:
        """Get a source by URL."""
        resp = self._request("GET", self._sources_table, params={"url": f"eq.{url}"})
        if resp.status_code == 200:
            result = resp.json()
            if result:
                s = result[0]
                known_fields = {"id", "url", "title", "source_type", "metadata", "description", "created_at", "updated_at"}
                filtered = {k: v for k, v in s.items() if k in known_fields}
                return Source(**filtered)
        return None
    
    def list_sources(self, limit: int = 100) -> list[Source]:
        """List all sources."""
        resp = self._request("GET", self._sources_table, params={"limit": str(limit)})
        if resp.status_code == 200:
            sources = []
            for s in resp.json():
                # Filter to known fields only
                known_fields = {"id", "url", "title", "source_type", "metadata", "description", "created_at", "updated_at"}
                filtered = {k: v for k, v in s.items() if k in known_fields}
                sources.append(Source(**filtered))
            return sources
        return []
    
    # --- Chunks ---
    
    def add_chunk(
        self,
        source_id: int | str,
        content: str,
        chunk_index: int = 0,
        metadata: dict | None = None,
        embedding: list[float] | None = None,
        # Legacy params (ignored but accepted for compatibility)
        url: str | None = None,
        chunk_number: int | None = None,
        title: str | None = None,
    ) -> bool:
        """Add a chunk to the knowledgebase. Returns True on success."""
        # Use chunk_number as chunk_index if provided (compatibility)
        idx = chunk_index if chunk_number is None else chunk_number
        
        data = {
            "source_id": source_id,
            "chunk_index": idx,
            "content": content,
            "metadata": metadata or {},
        }
        
        # Include url if provided (required by schema)
        if url:
            data["url"] = url
        if title:
            data["title"] = title
        if embedding:
            data["embedding"] = embedding
        
        resp = self._request("POST", self._chunks_table, data=data)
        return resp.status_code == 201
    
    def add_chunks_batch(self, chunks: list[dict]) -> int:
        """Add multiple chunks at once. Returns number added."""
        if not chunks:
            return 0
            
        resp = self._request("POST", self._chunks_table, data=chunks)
        if resp.status_code in (200, 201):
            return len(chunks)
        return 0
    
    def get_chunks_without_embeddings(self, limit: int = 50) -> list[Chunk]:
        """Get chunks that need embeddings."""
        resp = self._request(
            "GET",
            self._chunks_table,
            params={
                "embedding": "is.null",
                "select": "id,source_id,chunk_index,content,metadata",
                "limit": str(limit),
            },
        )
        if resp.status_code == 200:
            chunks = []
            for c in resp.json():
                chunks.append(Chunk(
                    id=c["id"],
                    source_id=c["source_id"],
                    content=c["content"],
                    chunk_index=c.get("chunk_index", 0),
                    metadata=c.get("metadata"),
                    embedding=None,
                ))
            return chunks
        return []
    
    def update_chunk_embedding(self, chunk_id: int, embedding: list[float]) -> bool:
        """Update a chunk's embedding."""
        resp = self._request(
            "PATCH",
            self._chunks_table,
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
            self._chunks_table,
            params={**params, "limit": "1"},
        )
        resp.headers.get("content-range", "0-0/0")
        
        # Use HEAD with Prefer: count=exact for accurate count
        headers = {**self._headers, "Prefer": "count=exact"}
        resp = requests.head(
            f"{self.config.supabase_url}/rest/v1/{self._chunks_table}",
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
        
        # Try RPC function first (for schemas that have it)
        resp = requests.post(
            f"{self.config.supabase_url}/rest/v1/rpc/{self.config.table_prefix}_search_semantic",
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
            if results:  # Only use if we got results
                return [
                    Chunk(
                        id=r["id"],
                        source_id=r.get("source_id", ""),
                        content=r["content"],
                        chunk_index=r.get("chunk_index", 0),
                        url=r.get("url"),
                        title=r.get("title"),
                        similarity=r.get("similarity"),
                    )
                    for r in results
                ]
        
        # Fallback: direct vector search using match_documents function
        # This is a simpler function that just does cosine similarity
        fallback_resp = requests.post(
            f"{self.config.supabase_url}/rest/v1/rpc/match_documents",
            headers=self._headers,
            json={
                "query_embedding": embedding,
                "match_count": limit,
                "filter": {},
            },
            timeout=30,
        )
        
        if fallback_resp.status_code == 200:
            results = fallback_resp.json()
            if results:
                return [
                    Chunk(
                        id=r.get("id", 0),
                        source_id=r.get("source_id", ""),
                        content=r.get("content", ""),
                        chunk_index=r.get("chunk_index", 0),
                        similarity=r.get("similarity"),
                    )
                    for r in results
                ]
        
        # Final fallback: search using our own simple function
        return self._search_vector_direct(embedding, limit, threshold)
    
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
            f"{self.config.supabase_url}/rest/v1/rpc/{self.config.table_prefix}_search_hybrid",
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
                    source_id=r.get("source_id", ""),
                    content=r["content"],
                    chunk_index=r.get("chunk_index", 0),
                    url=r.get("url"),
                    title=r.get("title"),
                    similarity=r.get("combined_score"),
                )
                for r in results
            ]
        return []
    
    # --- Stats ---
    
    def stats(self) -> dict:
        """Get knowledgebase statistics."""
        # Try RPC function first
        resp = requests.post(
            f"{self.config.supabase_url}/rest/v1/rpc/{self.config.table_prefix}_stats",
            headers=self._headers,
            json={},
            timeout=10,
        )
        
        if resp.status_code == 200:
            result = resp.json()
            if result:
                return result[0] if isinstance(result, list) else result
        
        # Fallback: count manually
        total_chunks = self.count_chunks()
        with_embeddings = self.count_chunks(with_embeddings=True)
        
        return {
            "total_sources": len(self.list_sources()),
            "total_chunks": total_chunks,
            "chunks_with_embeddings": with_embeddings,
            "chunks_without_embeddings": total_chunks - with_embeddings,
        }
    
    def _search_vector_direct(
        self,
        query_embedding: list[float],
        limit: int = 10,
        threshold: float = 0.5,
    ) -> list[Chunk]:
        """
        Direct vector search as fallback.
        Fetches chunks and computes similarity client-side.
        Note: This is slower than using a proper pgvector function.
        """
        import math
        
        def cosine_similarity(a: list[float], b: list[float]) -> float:
            """Compute cosine similarity between two vectors."""
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            if norm_a == 0 or norm_b == 0:
                return 0
            return dot / (norm_a * norm_b)
        
        # Fetch chunks with embeddings (limited to avoid memory issues)
        # This is a fallback, so we accept some limitations
        resp = self._request(
            "GET",
            self._chunks_table,
            params={
                "select": "id,source_id,chunk_index,content,embedding",
                "embedding": "not.is.null",
                "limit": "500",  # Reasonable limit for fallback
            },
        )
        
        if resp.status_code != 200:
            return []
        
        chunks_data = resp.json()
        
        # Compute similarities
        results = []
        for c in chunks_data:
            emb = c.get("embedding")
            if not emb:
                continue
            
            # Parse embedding if it's a string (Supabase returns vectors as strings)
            if isinstance(emb, str):
                # Format: "[0.1,0.2,...]"
                try:
                    emb = [float(x) for x in emb.strip("[]").split(",")]
                except:
                    continue
            
            sim = cosine_similarity(query_embedding, emb)
            if sim >= threshold:
                results.append({
                    "id": c["id"],
                    "source_id": c["source_id"],
                    "content": c["content"],
                    "chunk_index": c.get("chunk_index", 0),
                    "similarity": sim,
                })
        
        # Sort by similarity descending
        results.sort(key=lambda x: x["similarity"], reverse=True)
        
        # Return top N
        return [
            Chunk(
                id=r["id"],
                source_id=r["source_id"],
                content=r["content"],
                chunk_index=r["chunk_index"],
                similarity=r["similarity"],
            )
            for r in results[:limit]
        ]
