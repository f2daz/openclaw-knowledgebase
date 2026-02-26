"""Optimized Ollama embedding generation with parallel processing."""

import requests
from typing import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from knowledgebase.config import get_config


def get_embedding(
    text: str,
    model: str | None = None,
    ollama_url: str | None = None,
    timeout: int = 120,
    retries: int = 2,
) -> list[float] | None:
    """
    Generate embedding for text using Ollama with retry logic.
    """
    config = get_config()
    model = model or config.embedding_model
    ollama_url = ollama_url or config.ollama_url
    
    # Truncate long texts
    max_chars = 3000
    text = text[:max_chars] if len(text) > max_chars else text
    
    if not text.strip():
        return None
    
    for attempt in range(retries + 1):
        try:
            response = requests.post(
                f"{ollama_url}/api/embeddings",
                json={"model": model, "prompt": text},
                timeout=timeout,
            )
            response.raise_for_status()
            
            data = response.json()
            embedding = data.get("embedding")
            return embedding if embedding else None
            
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))  # Exponential backoff
                continue
            return None
    
    return None


def get_embeddings_batch_parallel(
    texts: list[str],
    model: str | None = None,
    ollama_url: str | None = None,
    max_workers: int = 4,
    timeout: int = 120,
    on_progress: Callable[[int, int], None] | None = None,
) -> list[list[float] | None]:
    """
    Generate embeddings for multiple texts using parallel processing.
    
    Args:
        texts: List of texts to embed
        model: Ollama model name
        ollama_url: Ollama API URL
        max_workers: Number of parallel workers (default: 4)
        timeout: Request timeout per embedding
        on_progress: Optional callback(completed, total) for progress updates
        
    Returns:
        List of embedding vectors (or None for failed embeddings)
        
    Example:
        >>> def show_progress(done, total):
        ...     print(f"Progress: {done}/{total}")
        >>> embeddings = get_embeddings_batch_parallel(texts, on_progress=show_progress)
    """
    config = get_config()
    model = model or config.embedding_model
    ollama_url = ollama_url or config.ollama_url
    
    total = len(texts)
    results = [None] * total
    completed = 0
    
    def embed_single(index: int, text: str) -> tuple[int, list[float] | None]:
        embedding = get_embedding(text, model=model, ollama_url=ollama_url, timeout=timeout)
        return index, embedding
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(embed_single, i, text): i 
            for i, text in enumerate(texts)
        }
        
        for future in as_completed(futures):
            try:
                index, embedding = future.result()
                results[index] = embedding
            except Exception:
                pass  # Keep None for failed embeddings
            
            completed += 1
            if on_progress:
                on_progress(completed, total)
    
    return results


def embed_chunks_parallel(
    chunks: list[dict],
    update_callback: Callable[[str, list[float]], None],
    max_workers: int = 4,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> tuple[int, int]:
    """
    Embed multiple chunks and update them via callback.
    
    Args:
        chunks: List of chunk dicts with 'id' and 'content'
        update_callback: Function(chunk_id, embedding) to save the embedding
        max_workers: Number of parallel workers
        on_progress: Optional callback(completed, total, current_text) for progress
        
    Returns:
        Tuple of (success_count, error_count)
        
    Example:
        >>> def save_embedding(chunk_id, embedding):
        ...     kb.update_chunk_embedding(chunk_id, embedding)
        >>> success, errors = embed_chunks_parallel(chunks, save_embedding)
    """
    config = get_config()
    total = len(chunks)
    success_count = 0
    error_count = 0
    
    def process_chunk(chunk: dict) -> tuple[str, list[float] | None]:
        chunk_id = chunk['id']
        content = chunk.get('content', '')
        embedding = get_embedding(content)
        return chunk_id, embedding
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_chunk, c): c for c in chunks}
        completed = 0
        
        for future in as_completed(futures):
            chunk = futures[future]
            try:
                chunk_id, embedding = future.result()
                if embedding:
                    update_callback(chunk_id, embedding)
                    success_count += 1
                else:
                    error_count += 1
            except Exception:
                error_count += 1
            
            completed += 1
            if on_progress:
                preview = chunk.get('content', '')[:50] + '...'
                on_progress(completed, total, preview)
    
    return success_count, error_count


# Keep original sequential function for compatibility
def get_embeddings_batch(
    texts: list[str],
    model: str | None = None,
    ollama_url: str | None = None,
    timeout: int = 300,
) -> list[list[float] | None]:
    """Sequential batch embedding (for compatibility)."""
    return [
        get_embedding(text, model=model, ollama_url=ollama_url, timeout=timeout)
        for text in texts
    ]


def test_ollama_connection(ollama_url: str | None = None) -> tuple[bool, str]:
    """Test connection to Ollama and check if embedding model is available."""
    config = get_config()
    ollama_url = ollama_url or config.ollama_url
    
    try:
        response = requests.get(f"{ollama_url}/api/tags", timeout=5)
        response.raise_for_status()
        
        models = response.json().get("models", [])
        model_names = [m.get("name", "").split(":")[0] for m in models]
        
        if config.embedding_model not in model_names:
            return False, f"Model '{config.embedding_model}' not found. Run: ollama pull {config.embedding_model}"
        
        return True, f"Ollama OK, model '{config.embedding_model}' available"
        
    except requests.exceptions.ConnectionError:
        return False, f"Cannot connect to Ollama at {ollama_url}"
    except requests.exceptions.RequestException as e:
        return False, f"Ollama error: {e}"
