"""
File watcher with delta indexing and multi-language support.
"""

import hashlib
import logging
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .architect import ArchitectAnalyzer
from .cache import FileHashCache
from .chunking import ChunkerFactory, get_factory
from .consts import DEBOUNCE_SECONDS
from .db import CodeChunk, LanceDBManager
from .embeddings import EmbeddingEngine

logger = logging.getLogger(__name__)


class IndexingPipeline:
    """
    Pipeline for indexing files with multi-language support.
    
    Uses the ChunkerFactory to select the appropriate chunker based on file extension.
    """
    
    def __init__(self, max_workers: int = 12):
        self.chunker_factory = get_factory()
        self.embeddings = EmbeddingEngine(max_workers=max_workers, use_cache=True)
        self.db = LanceDBManager()
        self.file_cache = FileHashCache()
        
        self.chunk_queue = queue.Queue(maxsize=100)
        self.embed_queue = queue.Queue(maxsize=50)
        self._shutdown = False
    
    def is_supported(self, filepath: str) -> bool:
        """Check if file type is supported for indexing."""
        return self.chunker_factory.is_supported(filepath)
    
    def process_file(self, filepath: str) -> Tuple[int, int, Optional[str]]:
        """
        Process a single file through the pipeline.
        Returns (success: 0 or 1, chunk_count, error_message or None)
        """
        try:
            # Get chunker for this file type
            chunker = self.chunker_factory.get_chunker(filepath)
            if not chunker:
                return 0, 0, f"Unsupported file type: {filepath}"
            
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            stat = os.stat(filepath)
            content_hash = hashlib.sha256(content.encode()).hexdigest()[:32]
            
            raw_chunks = chunker.chunk_file(filepath, content)
            if not raw_chunks:
                return 1, 0, None
            
            # Split oversized chunks to avoid embedding truncation
            # If a chunk's embedding_text is too long, split it into multiple chunks
            processed_chunks = []
            for raw_chunk in raw_chunks:
                from .embeddings import split_text_into_chunks, MAX_EMBEDDING_TEXT_LENGTH
                
                # Check if this chunk's embedding text is too long
                if len(raw_chunk.embedding_text) > MAX_EMBEDDING_TEXT_LENGTH:
                    # Split the content into multiple sub-chunks
                    content_parts = split_text_into_chunks(raw_chunk.content, MAX_EMBEDDING_TEXT_LENGTH)
                    
                    logger.info(f"Split large chunk into {len(content_parts)} parts: {raw_chunk.context_header}")
                    
                    # Create a separate chunk for each part
                    for i, content_part in enumerate(content_parts, 1):
                        # Create modified context header to indicate part number
                        part_header = f"{raw_chunk.context_header} [part {i}/{len(content_parts)}]"
                        
                        # Pre-calculate embedding text to pass to constructor
                        part_embedding_text = f"{raw_chunk.filepath}\n{part_header}\n{content_part}"
                        
                        # Create new chunk with part suffix and ALL required fields
                        part_chunk = type(raw_chunk)(
                            id=f"{raw_chunk.id}_part{i}",
                            content=content_part,
                            filepath=raw_chunk.filepath,
                            context_header=part_header,
                            chunk_type=raw_chunk.chunk_type,        # Required: pass original type
                            start_line=raw_chunk.start_line,        # Required: use original start line
                            end_line=raw_chunk.end_line,            # Required: use original end line
                            is_architecture_node=raw_chunk.is_architecture_node if i == 1 else False,
                            embedding_text=part_embedding_text,     # Required: pass calculated text
                            summary=raw_chunk.summary if i == 1 else f"{raw_chunk.summary} (continued)",
                            file_type=raw_chunk.file_type
                        )
                        
                        processed_chunks.append(part_chunk)
                else:
                    # Chunk is fine, use as-is
                    processed_chunks.append(raw_chunk)
            
            # Batch embed using embedding_text (includes context header)
            texts = [c.embedding_text for c in processed_chunks]
            embeddings = self.embeddings.embed_batch(texts, prefix="search_document: ")
            
            # Build CodeChunk objects
            chunks = []
            for raw_chunk, embedding in zip(processed_chunks, embeddings):
                chunk = CodeChunk(
                    id=raw_chunk.id,
                    content=raw_chunk.content,
                    filepath=raw_chunk.filepath,
                    context_header=raw_chunk.context_header,
                    summary=raw_chunk.summary,
                    is_architecture_node=raw_chunk.is_architecture_node,
                    vector=embedding,
                    file_type=raw_chunk.file_type
                )
                chunks.append(chunk)
            
            # Upsert to database
            self.db.upsert_chunks(chunks, filepath)
            
            # Update file hash cache
            self.file_cache.update_file(
                filepath, content_hash, stat.st_mtime, stat.st_size, len(chunks)
            )
            
            return 1, len(chunks), None
            
        except Exception as e:
            # Log error but don't crash - continue with other files
            error_msg = str(e)
            # Only log full error for non-500 errors (500s are logged in embeddings)
            if "500" not in error_msg:
                logger.error(f"Pipeline error for {filepath}: {e}")
            return 0, 0, error_msg
    
    def process_files_batch(self, filepaths: List[str], max_workers: int = 8) -> Tuple[int, int, int]:
        """
        Process multiple files in parallel.
        Returns (files_processed, total_chunks, files_failed)
        """
        if not filepaths:
            return 0, 0, 0
        
        total_files = 0
        total_chunks = 0
        total_failed = 0
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.process_file, fp): fp for fp in filepaths}
            for future in as_completed(futures):
                success, chunks, error = future.result()
                total_files += success
                total_chunks += chunks
                if not success:
                    total_failed += 1
        
        return total_files, total_chunks, total_failed
    
    def get_changed_files(self, filepaths: List[str]) -> List[str]:
        """Filter to only files that have changed since last index"""
        return self.file_cache.get_changed_files(filepaths)


class LibrarianWatcher(FileSystemEventHandler):
    """
    File system watcher with delta indexing and pipeline processing.
    
    Improvements:
    - Delta indexing: only process changed files
    - Shared pipeline for efficient resource usage
    - Larger worker pools
    - Better debouncing
    """
    
    def __init__(self, root_dir: str, use_delta_indexing: bool = True):
        self.root_dir = root_dir
        self.use_delta_indexing = use_delta_indexing
        
        # Shared pipeline
        self.pipeline = IndexingPipeline(max_workers=12)
        
        # Direct access to pipeline components
        self.embeddings = self.pipeline.embeddings
        self.db = self.pipeline.db
        
        # Architect for cold path
        self.architect = ArchitectAnalyzer()
        self.executor = ThreadPoolExecutor(max_workers=12)
        
        # Debounce/Queue for Tier 2 (Architect)
        self.pending_summaries = {}  # filepath -> timestamp
        self._lock = threading.Lock()

    def on_modified(self, event):
        if event.is_directory:
            return
        
        filename = event.src_path
        
        # Ignore patterns for .NET build artifacts and secrets
        ignore_patterns = ['bin/', 'obj/', '/.git/', '/.vs/', 'appsettings.Development.json']
        if any(pattern in filename for pattern in ignore_patterns):
            return
            
        if not filename.endswith(".cs"):
            return

        self.process_hot_path(filename)
        self.schedule_cold_path(filename)

    def on_created(self, event):
        self.on_modified(event)

    def process_hot_path(self, filepath: str) -> int:
        """
        Hot path: <200ms for immediate indexing.
        Uses the optimized pipeline.
        Returns chunk count.
        """
        success, chunks = self.pipeline.process_file(filepath)
        if success:
            logger.info(f"[Hot Path] Indexed {filepath} ({chunks} chunks)")
        return chunks

    def process_files_parallel(self, filepaths: List[str], use_delta: bool = True) -> Tuple[int, int]:
        """
        Process multiple files in parallel with optional delta indexing.
        Returns (files_processed, total_chunks)
        """
        if use_delta and self.use_delta_indexing:
            # Filter to only changed files
            changed_files = self.pipeline.get_changed_files(filepaths)
            skipped = len(filepaths) - len(changed_files)
            if skipped > 0:
                logger.info(f"[Delta] Skipping {skipped} unchanged files")
            filepaths = changed_files
        
        return self.pipeline.process_files_batch(filepaths, max_workers=8)

    def schedule_cold_path(self, filepath: str):
        """Schedule file for cold path (architect) processing"""
        with self._lock:
            self.pending_summaries[filepath] = time.time()
    
    def run_cold_path_loop(self):
        """Background loop for cold path processing"""
        while True:
            now = time.time()
            to_process = []
            
            with self._lock:
                for fp, ts in list(self.pending_summaries.items()):
                    if now - ts > DEBOUNCE_SECONDS:
                        to_process.append(fp)
                        del self.pending_summaries[fp]
            
            for fp in to_process:
                self.executor.submit(self._run_architect, fp)
                
            time.sleep(1.0)

    def _run_architect(self, filepath: str):
        """Run architect analysis on a file (cold path)"""
        try:
            logger.info(f"[Cold Path] Architect analyzing {filepath}...")
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            summary = self.architect.generate_summary(content)
            if summary:
                self.db.update_summary(filepath, summary)
                logger.info(f"[Cold Path] Summary updated for {filepath}")
                
        except Exception as e:
            logger.error(f"[Cold Path] Error analyzing {filepath}: {e}")

    def get_cache_stats(self) -> Dict:
        """Get statistics from all caches"""
        return {
            "embeddings": self.embeddings.get_cache_stats(),
            "files": self.pipeline.file_cache.get_stats()
        }


def start_watching(path: str):
    """Start the file watcher"""
    event_handler = LibrarianWatcher(path)
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    
    try:
        event_handler.run_cold_path_loop()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()