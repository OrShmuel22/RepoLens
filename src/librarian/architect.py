import re
import logging
from .consts import LLM_MODEL, LLM_PROVIDER, LLM_TEMPERATURE, LLM_MAX_TOKENS, OLLAMA_HOST
from .providers import get_llm_provider

logger = logging.getLogger(__name__)


class ArchitectAnalyzer:
    def __init__(self, model: str = LLM_MODEL, provider: str = LLM_PROVIDER, **provider_kwargs):
        self.model = model
        self.provider_name = provider

        # Initialize provider
        if not provider_kwargs and provider.lower() == "ollama":
            provider_kwargs = {"host": OLLAMA_HOST}

        try:
            self._provider = get_llm_provider(provider, model, **provider_kwargs)
            logger.info(f"Initialized {provider} LLM provider with model: {model}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM provider: {e}")
            raise

    def analyze_structure(self, filepath: str, content: str) -> bool:
        # Dynamic Architecture Detection
        # Returns True if is_architecture_node

        # Patterns to look for
        patterns = [
            r'builder\.Services\.',  # DI
            r'app\.UseMiddleware',   # Middleware
            r'\[ApiController\]',    # Entry Point
            r'\[Route\(.*\)\]',      # Entry Point
            r'\[HttpGet\]',          # Entry Point
            r'IConfiguration',       # Config
            r'appsettings\.json'     # Config (in string)
        ]

        for p in patterns:
            if re.search(p, content):
                return True
        return False

    def generate_summary(self, content: str) -> str:
        prompt = (
            "Analyze this .NET class. Identify:\n"
            "1) The Services it injects (Inter-service dependencies)\n"
            "2) The Interfaces it implements\n"
            "3) Any database tables it modifies.\n"
            "Output as concise bullet points."
            f"\n\nCode:\n{content[:8000]}" # Truncate for safety
        )

        try:
            response = self._provider.generate(
                prompt=prompt,
                max_tokens=LLM_MAX_TOKENS,
                temperature=LLM_TEMPERATURE
            )
            return response
        except Exception as e:
            logger.error(f"Summary generation error: {e}")
            return f"Error generating summary: {e}"
