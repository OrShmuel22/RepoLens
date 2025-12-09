"""
Base classes for the chunking strategy pattern.
"""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from ..consts import (
    CHUNK_OVERLAP_LINES,
    CHUNK_SIZE_LINES,
    MAX_EMBEDDING_TEXT_LENGTH,
    MIN_CHUNK_SIZE_CHARS,
)


@dataclass
class ChunkData:
    """Intermediate chunk data before embedding."""
    id: str
    content: str
    filepath: str
    context_header: str
    chunk_type: str  # 'class', 'method', 'function', 'block', 'file_header'
    start_line: int
    end_line: int
    is_architecture_node: bool
    embedding_text: str  # Pre-formatted text for embedding (includes context)
    summary: str = ""
    file_type: str = ""


class BaseChunker(ABC):
    """
    Abstract base class for language-specific chunkers.
    
    Subclasses must implement:
    - chunk_file(): Parse and chunk a file into semantic units
    - supported_extensions: List of file extensions this chunker handles
    """
    
    def __init__(
        self,
        max_chunk_lines: int = CHUNK_SIZE_LINES,
        overlap_lines: int = CHUNK_OVERLAP_LINES,
        max_text_length: int = MAX_EMBEDDING_TEXT_LENGTH,
        min_chunk_chars: int = MIN_CHUNK_SIZE_CHARS,
    ):
        self.max_chunk_lines = max_chunk_lines
        self.overlap_lines = overlap_lines
        self.max_text_length = max_text_length
        self.min_chunk_chars = min_chunk_chars
    
    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """File extensions this chunker supports (e.g., ['.cs', '.csx'])."""
        pass
    
    @property
    @abstractmethod
    def language_name(self) -> str:
        """Human-readable language name (e.g., 'C#')."""
        pass
    
    @abstractmethod
    def chunk_file(self, filepath: str, content: str) -> List[ChunkData]:
        """
        Parse and chunk a file into semantic units.
        
        Args:
            filepath: Path to the file
            content: File content as string
            
        Returns:
            List of ChunkData objects
        """
        pass
    
    def _generate_chunk_id(self, filepath: str, start_line: int, end_line: int, content: str) -> str:
        """Generate a unique chunk ID."""
        return hashlib.md5(
            f"{filepath}:{start_line}:{end_line}:{hash(content)}".encode()
        ).hexdigest()
    
    def _create_embedding_text(self, context_header: str, filepath: str, chunk_type: str, content: str) -> str:
        """Create the embedding text with context header."""
        return f"""Context: {context_header}
File: {filepath}
Type: {chunk_type}

{content}"""
    
    def _truncate_content(self, content: str) -> str:
        """Truncate content if too long."""
        if len(content) > self.max_text_length:
            return content[:self.max_text_length] + "\n... [truncated]"
        return content
    
    def _split_large_content(
        self,
        filepath: str,
        lines: List[str],
        start_line: int,
        context_header: str,
        chunk_type: str,
        file_type: str,
        arch_indicators: List[str],
    ) -> List[ChunkData]:
        """Split large content into overlapping chunks."""
        chunks = []
        i = 0
        part = 1
        
        while i < len(lines):
            end_idx = min(i + self.max_chunk_lines, len(lines))
            chunk_lines = lines[i:end_idx]
            content = "\n".join(chunk_lines)
            
            header = f"{context_header} (part {part})" if len(lines) > self.max_chunk_lines else context_header
            
            if len(content) >= self.min_chunk_chars:
                content = self._truncate_content(content)
                is_arch = any(ind in content for ind in arch_indicators)
                
                chunks.append(ChunkData(
                    id=self._generate_chunk_id(filepath, start_line + i, start_line + end_idx - 1, content),
                    content=content,
                    filepath=filepath,
                    context_header=header,
                    chunk_type=chunk_type,
                    start_line=start_line + i,
                    end_line=start_line + end_idx - 1,
                    is_architecture_node=is_arch,
                    embedding_text=self._create_embedding_text(header, filepath, chunk_type, content),
                    file_type=file_type,
                ))
            
            i += self.max_chunk_lines - self.overlap_lines
            part += 1
        
        return chunks
