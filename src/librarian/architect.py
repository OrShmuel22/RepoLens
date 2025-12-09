import re
import ollama
from .consts import LLM_MODEL

class ArchitectAnalyzer:
    def __init__(self, model: str = LLM_MODEL):
        self.model = model
        
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
            response = ollama.generate(model=self.model, prompt=prompt)
            return response.get('response', '')
        except Exception as e:
            return f"Error generating summary: {e}"
