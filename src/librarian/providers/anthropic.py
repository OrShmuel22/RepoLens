"""
Anthropic provider implementation.
"""

import os
import logging
from typing import List, Optional
from .base import BaseLLMProvider

logger = logging.getLogger(__name__)


class AnthropicLLMProvider(BaseLLMProvider):
    """
    Anthropic LLM provider (Claude models).
    Note: Anthropic does not provide embedding models.
    """

    def __init__(self, model: str = "claude-3-5-sonnet-20241022", api_key: Optional[str] = None, **kwargs):
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')

        if not self.api_key:
            raise ValueError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )

        # Import Anthropic SDK
        try:
            from anthropic import Anthropic
            self.client = Anthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        logger.info(f"Initialized Anthropic LLM provider: {self.model}")

    def generate(self, prompt: str, max_tokens: Optional[int] = None,
                 temperature: float = 0.7) -> str:
        """Generate text completion."""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens or 1024,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            logger.error(f"Anthropic generate error: {e}")
            return f"Error generating response: {e}"

    def generate_stream(self, prompt: str, max_tokens: Optional[int] = None,
                       temperature: float = 0.7):
        """Stream text completion."""
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=max_tokens or 1024,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            logger.error(f"Anthropic stream error: {e}")
            yield f"Error: {e}"

    def health_check(self) -> bool:
        """Check if Anthropic API is accessible."""
        try:
            # Try a minimal completion
            self.generate("test", max_tokens=5)
            return True
        except Exception as e:
            logger.warning(f"Anthropic health check failed: {e}")
            return False

