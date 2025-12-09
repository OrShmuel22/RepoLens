"""
Chunker factory for language-specific chunking strategies.
"""

import os
from typing import Dict, List, Optional, Type

from .base import BaseChunker, ChunkData
from .csharp import CSharpChunker


class ChunkerFactory:
    """
    Factory for creating language-specific chunkers.
    
    Usage:
        factory = ChunkerFactory()
        chunker = factory.get_chunker(".cs")
        chunks = chunker.chunk_file(filepath, content)
    
    To add a new language:
        1. Create a new chunker class extending BaseChunker
        2. Call factory.register(YourChunker)
    """
    
    def __init__(self):
        self._chunkers: Dict[str, BaseChunker] = {}
        self._extension_map: Dict[str, str] = {}
        
        # Register built-in chunkers
        self.register(CSharpChunker())
    
    def register(self, chunker: BaseChunker):
        """Register a chunker for its supported extensions."""
        lang = chunker.language_name
        self._chunkers[lang] = chunker
        
        for ext in chunker.supported_extensions:
            self._extension_map[ext.lower()] = lang
    
    def get_chunker(self, filepath_or_extension: str) -> Optional[BaseChunker]:
        """
        Get the appropriate chunker for a file.
        
        Args:
            filepath_or_extension: File path or extension (e.g., ".cs" or "file.cs")
            
        Returns:
            Chunker instance or None if no chunker supports this file type
        """
        if '.' in filepath_or_extension:
            ext = os.path.splitext(filepath_or_extension)[1].lower()
        else:
            ext = filepath_or_extension.lower()
        
        lang = self._extension_map.get(ext)
        return self._chunkers.get(lang) if lang else None
    
    def get_supported_extensions(self) -> List[str]:
        """Get list of all supported file extensions."""
        return list(self._extension_map.keys())
    
    def get_supported_languages(self) -> List[str]:
        """Get list of all supported language names."""
        return list(self._chunkers.keys())
    
    def is_supported(self, filepath: str) -> bool:
        """Check if a file type is supported."""
        return self.get_chunker(filepath) is not None


# Global factory instance
_factory: Optional[ChunkerFactory] = None


def get_factory() -> ChunkerFactory:
    """Get the global factory instance."""
    global _factory
    if _factory is None:
        _factory = ChunkerFactory()
    return _factory


def get_chunker(filepath: str) -> Optional[BaseChunker]:
    """Convenience function to get a chunker for a file."""
    return get_factory().get_chunker(filepath)


def chunk_file(filepath: str, content: str) -> List[ChunkData]:
    """
    Convenience function to chunk a file.
    
    Args:
        filepath: Path to the file
        content: File content
        
    Returns:
        List of chunks, or empty list if file type not supported
    """
    chunker = get_chunker(filepath)
    if chunker:
        return chunker.chunk_file(filepath, content)
    return []
