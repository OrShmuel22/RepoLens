"""
Configuration constants for the Codebase Librarian.
Loads from config.yaml with environment variable overrides.
"""

import os
from pathlib import Path
from typing import Any

import yaml

def _load_config() -> dict[str, Any]:
    """Load configuration from YAML file."""
    config_paths = [
        Path("/app/config.yaml"),  # Docker
        Path(__file__).parent.parent.parent / "config.yaml",  # Local dev
    ]

    for path in config_paths:
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f)

    return {}

_config = _load_config()

def _get(section: str, key: str, default: Any, env_var: str | None = None) -> Any:
    """Get config value with env override."""
    if env_var and os.getenv(env_var):
        val = os.getenv(env_var)
        if isinstance(default, bool):
            return val.lower() == "true"
        if isinstance(default, int):
            return int(val)
        if isinstance(default, float):
            return float(val)
        return val
    return _config.get(section, {}).get(key, default)

# Paths
LANCEDB_PATH = _get("database", "path", os.path.join(os.getcwd(), ".lancedb"), "LANCEDB_PATH")
MODELS_CACHE_DIR = _get("cache", "models_dir", os.path.join(os.getcwd(), ".models"), "MODELS_CACHE_DIR")
CACHE_DIR = _get("cache", "dir", os.path.join(os.getcwd(), ".cache"), "CACHE_DIR")

# Database
DB_TABLE_NAME = _get("database", "table_name", "codebase_chunks")

# Provider Configuration
EMBEDDING_PROVIDER = _get("providers", "embedding", {}).get("provider", "ollama")
EMBEDDING_MODEL = _get("providers", "embedding", {}).get("model", "nomic-embed-text")
LLM_PROVIDER = _get("providers", "llm", {}).get("provider", "ollama")
LLM_MODEL = _get("providers", "llm", {}).get("model", "llama3.2:3b")
LLM_TEMPERATURE = _get("providers", "llm", {}).get("temperature", 0.7)
LLM_MAX_TOKENS = _get("providers", "llm", {}).get("max_tokens", 2048)

# Provider-specific settings
OLLAMA_HOST = _get("providers", "embedding", {}).get("ollama", {}).get("host",
                   _get("ollama", "host", "http://localhost:11434"))

# Legacy Ollama config (for backward compatibility)
OLLAMA_EMBEDDING_MODEL = _get("ollama", "embedding_model", "nomic-embed-text")
OLLAMA_LLM_MODEL = _get("ollama", "llm_model", "qwen3:8b")

# Performance
MAX_WORKERS = _get("performance", "max_workers", 4, "MAX_WORKERS")
EMBEDDING_BATCH_SIZE = _get("embedding", "batch_size", 50, "EMBEDDING_BATCH_SIZE")
DB_BATCH_SIZE = _get("database", "batch_size", 500, "DB_BATCH_SIZE")

# Chunking
CHUNK_SIZE_LINES = _get("chunking", "chunk_size_lines", 15, "CHUNK_SIZE_LINES")
CHUNK_OVERLAP_LINES = _get("chunking", "overlap_lines", 3, "CHUNK_OVERLAP_LINES")
MAX_CONTEXT_STACK_DEPTH = _get("chunking", "max_context_stack_depth", 10)

# Embedding limits
MAX_EMBEDDING_TEXT_LENGTH = _get("embedding", "max_text_length", 1500, "MAX_EMBEDDING_TEXT_LENGTH")
MIN_CHUNK_SIZE_CHARS = _get("chunking", "min_chunk_chars", 50, "MIN_CHUNK_SIZE_CHARS")

# Watching
DEBOUNCE_SECONDS = _get("performance", "debounce_seconds", 5.0, "DEBOUNCE_SECONDS")

# Cache
EMBEDDING_CACHE_ENABLED = _get("cache", "enabled", True, "EMBEDDING_CACHE_ENABLED")
LRU_CACHE_SIZE = _get("cache", "lru_size", 5000, "LRU_CACHE_SIZE")
