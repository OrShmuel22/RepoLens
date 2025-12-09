"""
Provider abstraction layer for embeddings and LLM models.
Supports multiple backends: Ollama, OpenAI, Anthropic, Azure.
"""

from .base import BaseEmbeddingProvider, BaseLLMProvider
from .factory import get_embedding_provider, get_llm_provider

__all__ = [
    "BaseEmbeddingProvider",
    "BaseLLMProvider",
    "get_embedding_provider",
    "get_llm_provider",
]

