"""
Language-agnostic chunking system using Strategy pattern.

To add a new language:
1. Create a new file (e.g., python.py)
2. Subclass BaseChunker and implement chunk_file()
3. Register in factory.py
"""

from .base import BaseChunker, ChunkData
from .factory import ChunkerFactory, get_factory, get_chunker

__all__ = ["BaseChunker", "ChunkData", "ChunkerFactory", "get_factory", "get_chunker"]
