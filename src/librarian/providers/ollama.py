"""
Ollama provider implementation.
"""

import httpx
import os
import time
import logging
from typing import List, Optional
from .base import BaseEmbeddingProvider, BaseLLMProvider

logger = logging.getLogger(__name__)


class OllamaEmbeddingProvider(BaseEmbeddingProvider):
    """
    Ollama embedding provider using HTTP API.
    """

    def __init__(self, model: str = "nomic-embed-text", host: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.host = host or os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        self.timeout = kwargs.get('timeout', 60.0)
        self.max_retries = kwargs.get('max_retries', 5)

        # Create HTTP client with connection pooling
        self.client = httpx.Client(
            base_url=self.host,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
            limits=httpx.Limits(
                max_keepalive_connections=5,
                max_connections=10,
                keepalive_expiry=30.0
            )
        )
        logger.info(f"Initialized Ollama embedding provider: {self.model} @ {self.host}")

    def embed_sync(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                response = self.client.post(
                    "/api/embeddings",
                    json={"model": self.model, "prompt": text}
                )
                response.raise_for_status()
                return response.json()["embedding"]
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 500 and attempt < self.max_retries - 1:
                    wait_time = min(2 ** attempt, 16)
                    logger.debug(f"Ollama 500 error, retry {attempt + 1}/{self.max_retries}")
                    time.sleep(wait_time)
                elif e.response.status_code != 500:
                    raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt, 16))
                else:
                    raise
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt, 16))
                else:
                    raise

        raise last_error or RuntimeError("Embedding failed after all retries")

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        return [self.embed_sync(text) for text in texts]

    def health_check(self) -> bool:
        """Check if Ollama is responsive."""
        try:
            response = self.client.get("/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False

    def __del__(self):
        """Cleanup HTTP client."""
        try:
            self.client.close()
        except Exception:
            pass


class OllamaLLMProvider(BaseLLMProvider):
    """
    Ollama LLM provider using Python SDK.
    """

    def __init__(self, model: str = "llama3.2:3b", host: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.host = host or os.getenv('OLLAMA_HOST', 'http://localhost:11434')

        # Import ollama SDK
        try:
            import ollama

            # Create client with custom host if needed
            if self.host != 'http://localhost:11434':
                self.client = ollama.Client(host=self.host)
            else:
                self.client = ollama
        except ImportError:
            raise ImportError("ollama package not installed. Run: pip install ollama")

        logger.info(f"Initialized Ollama LLM provider: {self.model} @ {self.host}")

    def generate(self, prompt: str, max_tokens: Optional[int] = None,
                 temperature: float = 0.7) -> str:
        """Generate text completion."""
        try:
            options = {
                "temperature": temperature,
            }
            if max_tokens:
                options["num_predict"] = max_tokens

            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                options=options
            )
            return response.get('response', '')
        except Exception as e:
            logger.error(f"Ollama generate error: {e}")
            return f"Error generating response: {e}"

    def generate_stream(self, prompt: str, max_tokens: Optional[int] = None,
                       temperature: float = 0.7):
        """Stream text completion."""
        try:
            options = {
                "temperature": temperature,
            }
            if max_tokens:
                options["num_predict"] = max_tokens

            for chunk in self.client.generate(
                model=self.model,
                prompt=prompt,
                options=options,
                stream=True
            ):
                yield chunk.get('response', '')
        except Exception as e:
            logger.error(f"Ollama stream error: {e}")
            yield f"Error: {e}"

    def health_check(self) -> bool:
        """Check if Ollama is responsive."""
        try:
            # Try to list models
            self.client.list()
            return True
        except Exception as e:
            logger.warning(f"Ollama health check failed: {e}")
            return False

