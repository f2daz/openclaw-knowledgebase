"""Ollama embedding generation for OpenClaw Knowledgebase."""

import requests
from typing import Optional

from knowledgebase.config import get_config


def get_embedding(
    text: str,
    model: str | None = None,
    ollama_url: str | None = None,
    timeout: int = 120,
) -> list[float] | None:
    """
    Generate embedding for text using Ollama.
    
    Args:
        text: Text to embed
        model: Ollama model name (default: from config)
        ollama_url: Ollama API URL (default: from config)
        timeout: Request timeout in seconds
        
    Returns:
        List of floats (embedding vector) or None on error
    """
    config = get_config()
    model = model or config.embedding_model
    ollama_url = ollama_url or config.ollama_url
    
    # Truncate very long texts (nomic-embed-text has ~8k token limit)
    text = text[:32000] if len(text) > 32000 else text
    
    if not text.strip():
        return None
    
    try:
        response = requests.post(
            f"{ollama_url}/api/embed",
            json={"model": model, "input": text},
            timeout=timeout,
        )
        response.raise_for_status()
        
        data = response.json()
        embeddings = data.get("embeddings", [])
        return embeddings[0] if embeddings else None
        
    except requests.exceptions.RequestException as e:
        # Log error but don't crash
        return None


def get_embeddings_batch(
    texts: list[str],
    model: str | None = None,
    ollama_url: str | None = None,
    timeout: int = 300,
) -> list[list[float] | None]:
    """
    Generate embeddings for multiple texts.
    
    Note: Ollama doesn't support true batching yet,
    so this calls the API sequentially.
    
    Args:
        texts: List of texts to embed
        model: Ollama model name
        ollama_url: Ollama API URL
        timeout: Request timeout per embedding
        
    Returns:
        List of embedding vectors (or None for failed embeddings)
    """
    return [
        get_embedding(text, model=model, ollama_url=ollama_url, timeout=timeout)
        for text in texts
    ]


def test_ollama_connection(ollama_url: str | None = None) -> tuple[bool, str]:
    """
    Test connection to Ollama and check if embedding model is available.
    
    Returns:
        Tuple of (success, message)
    """
    config = get_config()
    ollama_url = ollama_url or config.ollama_url
    
    try:
        # Check if Ollama is running
        response = requests.get(f"{ollama_url}/api/tags", timeout=5)
        response.raise_for_status()
        
        # Check if embedding model is available
        models = response.json().get("models", [])
        model_names = [m.get("name", "").split(":")[0] for m in models]
        
        if config.embedding_model not in model_names:
            return False, f"Model '{config.embedding_model}' not found. Run: ollama pull {config.embedding_model}"
        
        return True, f"Ollama OK, model '{config.embedding_model}' available"
        
    except requests.exceptions.ConnectionError:
        return False, f"Cannot connect to Ollama at {ollama_url}"
    except requests.exceptions.RequestException as e:
        return False, f"Ollama error: {e}"
