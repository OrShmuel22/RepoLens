"""
Codebase Librarian - Semantic Code Search CLI

Usage:
    python -m src.main          # Show help
    python -m src.main menu     # Interactive menu
    python -m src.main index    # Index a codebase
    python -m src.main search   # Search code
    python -m src.main --help   # See all commands
"""
from src.cli.manage import app

if __name__ == "__main__":
    app()
