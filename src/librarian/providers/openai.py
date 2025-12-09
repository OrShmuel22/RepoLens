"""
OpenAI provider implementation.
"""

import os
import logging
from typing import List, Optional
from .base import BaseEmbeddingProvider, BaseLLMProvider

logger = logging.getLogger(__name__)


class OpenAIEmbeddingProvider(BaseEmbeddingProvider):
    """
    OpenAI embedding provider using official SDK.
    """

    def __init__(self, model: str = "text-embedding-3-small", api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')

        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )

        # Import OpenAI SDK
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

        logger.info(f"Initialized OpenAI embedding provider: {self.model}")

    def embed_sync(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"OpenAI embedding error: {e}")
            raise

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts (batched for efficiency)."""
        try:
            # OpenAI supports batching natively
            response = self.client.embeddings.create(
                model=self.model,
                input=texts
            )
            return [item.embedding for item in response.data]
        except Exception as e:
            logger.error(f"OpenAI batch embedding error: {e}")
            # Fallback to sequential
            return [self.embed_sync(text) for text in texts]

    def health_check(self) -> bool:
        """Check if OpenAI API is accessible."""
        try:
            # Try a minimal embedding
            self.embed_sync("test")
            return True
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            return False


class OpenAILLMProvider(BaseLLMProvider):
    """
    OpenAI LLM provider using official SDK.
    """

    def __init__(self, model: str = "gpt-4o-mini", api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')

        if not self.api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )

        # Import OpenAI SDK
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("openai package not installed. Run: pip install openai")

        logger.info(f"Initialized OpenAI LLM provider: {self.model}")

    def generate(self, prompt: str, max_tokens: Optional[int] = None,
                 temperature: float = 0.7) -> str:
        """Generate text completion."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAI generate error: {e}")
            return f"Error generating response: {e}"

    def generate_stream(self, prompt: str, max_tokens: Optional[int] = None,
                       temperature: float = 0.7):
        """Stream text completion."""
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"OpenAI stream error: {e}")
            yield f"Error: {e}"

    def health_check(self) -> bool:
        """Check if OpenAI API is accessible."""
        try:
            # Try a minimal completion
            self.generate("test", max_tokens=5)
            return True
        except Exception as e:
            logger.warning(f"OpenAI health check failed: {e}")
            return False

