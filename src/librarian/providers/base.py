"""
Base classes for embedding and LLM providers.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class BaseEmbeddingProvider(ABC):
    """
    Abstract base class for embedding providers.
    Supports automatic dimension detection.
    """

    def __init__(self, model: str, **kwargs):
        self.model = model
        self._dimension: Optional[int] = None
        self.config = kwargs

    @abstractmethod
    def embed_sync(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector
        """
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        pass

    def detect_dimension(self) -> int:
        """
        Automatically detect the embedding dimension by embedding a test string.
        Caches the result for future use.

        Returns:
            Integer dimension of the embedding model
        """
        if self._dimension is None:
            logger.info(f"Auto-detecting dimension for model: {self.model}")
            test_embedding = self.embed_sync("test")
            self._dimension = len(test_embedding)
            logger.info(f"Detected dimension: {self._dimension}")
        return self._dimension

    @property
    def dimension(self) -> int:
        """Get the embedding dimension (auto-detects if not cached)."""
        return self.detect_dimension()

    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if the provider is available and responsive.

        Returns:
            True if healthy, False otherwise
        """
        pass


class BaseLLMProvider(ABC):
    """
    Abstract base class for LLM providers.
    """

    def __init__(self, model: str, **kwargs):
        self.model = model
        self.config = kwargs

    @abstractmethod
    def generate(self, prompt: str, max_tokens: Optional[int] = None,
                 temperature: float = 0.7) -> str:
        """
        Generate text completion for a prompt.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)

        Returns:
            Generated text
        """
        pass

    @abstractmethod
    def generate_stream(self, prompt: str, max_tokens: Optional[int] = None,
                       temperature: float = 0.7):
        """
        Stream text completion for a prompt.

        Args:
            prompt: Input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)

        Yields:
            Text chunks as they are generated
        """
        pass

    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if the provider is available and responsive.

        Returns:
            True if healthy, False otherwise
        """
        pass

