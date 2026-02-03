"""Convenience search functions for OpenClaw Knowledgebase."""

from knowledgebase.client import KnowledgeBase, Chunk


def search(
    query: str,
    limit: int = 10,
    threshold: float = 0.5,
) -> list[dict]:
    """
    Simple semantic search interface.
    
    Args:
        query: Search query text
        limit: Maximum results
        threshold: Minimum similarity (0-1)
        
    Returns:
        List of dicts with url, title, content, similarity
        
    Example:
        >>> results = search("How do I create an automation?", limit=5)
        >>> for r in results:
        ...     print(f"[{r['similarity']:.2f}] {r['title']}")
    """
    kb = KnowledgeBase()
    chunks = kb.search_semantic(query, limit=limit, threshold=threshold)
    
    return [
        {
            "id": c.id,
            "source_id": str(c.source_id) if c.source_id else None,
            "url": c.url,
            "title": c.title,
            "content": c.content,
            "similarity": c.similarity,
            "chunk_number": c.chunk_number,
            "source_type": "web",
        }
        for c in chunks
    ]


def search_hybrid(
    query: str,
    limit: int = 10,
    semantic_weight: float = 0.7,
) -> list[dict]:
    """
    Hybrid search combining semantic and keyword matching.
    
    Args:
        query: Search query text
        limit: Maximum results
        semantic_weight: Balance between semantic (1.0) and keyword (0.0)
        
    Returns:
        List of dicts with url, title, content, similarity
    """
    kb = KnowledgeBase()
    chunks = kb.search_hybrid(query, limit=limit, semantic_weight=semantic_weight)
    
    return [
        {
            "id": c.id,
            "source_id": str(c.source_id) if c.source_id else None,
            "url": c.url,
            "title": c.title,
            "content": c.content,
            "similarity": c.similarity,
            "chunk_number": c.chunk_number,
            "source_type": "web",
        }
        for c in chunks
    ]


def format_results(results: list[dict], max_content: int = 200) -> str:
    """Format search results for display."""
    if not results:
        return "No results found."
    
    lines = []
    for i, r in enumerate(results, 1):
        sim = r.get("similarity", 0)
        title = r.get("title") or r.get("url", "Unknown")
        content = r.get("content", "")[:max_content]
        if len(r.get("content", "")) > max_content:
            content += "..."
        
        lines.append(f"{i}. [{sim:.2f}] {title}")
        lines.append(f"   {content}")
        lines.append("")
    
    return "\n".join(lines)
