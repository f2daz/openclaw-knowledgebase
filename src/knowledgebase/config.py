"""Configuration management for OpenClaw Knowledgebase."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """Knowledgebase configuration."""
    
    # Supabase
    supabase_url: str = ""
    supabase_key: str = ""
    
    # Ollama
    ollama_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    
    # Chunking
    chunk_size: int = 1000
    chunk_overlap: int = 200
    
    # Search
    default_match_count: int = 10
    similarity_threshold: float = 0.5
    semantic_weight: float = 0.7
    
    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Config":
        """Load configuration from environment variables."""
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()
        
        return cls(
            supabase_url=os.getenv("SUPABASE_URL", ""),
            supabase_key=os.getenv("SUPABASE_KEY", ""),
            ollama_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
            embedding_dimensions=int(os.getenv("EMBEDDING_DIMENSIONS", "768")),
            chunk_size=int(os.getenv("CHUNK_SIZE", "1000")),
            chunk_overlap=int(os.getenv("CHUNK_OVERLAP", "200")),
            default_match_count=int(os.getenv("DEFAULT_MATCH_COUNT", "10")),
            similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", "0.5")),
            semantic_weight=float(os.getenv("SEMANTIC_WEIGHT", "0.7")),
        )
    
    def validate(self) -> list[str]:
        """Validate configuration, return list of errors."""
        errors = []
        if not self.supabase_url:
            errors.append("SUPABASE_URL is required")
        if not self.supabase_key:
            errors.append("SUPABASE_KEY is required")
        return errors


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get or create global config instance."""
    global _config
    if _config is None:
        _config = Config.from_env()
    return _config


def set_config(config: Config) -> None:
    """Set global config instance."""
    global _config
    _config = config
