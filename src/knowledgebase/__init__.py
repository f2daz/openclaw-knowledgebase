"""OpenClaw Knowledgebase - Self-hosted RAG with Ollama + Supabase."""

from knowledgebase.client import KnowledgeBase
from knowledgebase.search import search, search_hybrid

__version__ = "0.1.0"
__all__ = ["KnowledgeBase", "search", "search_hybrid"]
