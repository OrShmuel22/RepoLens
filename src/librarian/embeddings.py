"""
Embedding engine with rate-limited queue, persistent cache, and connection pooling.
"""

import hashlib
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

import httpx

from .cache import EmbeddingCache
from .consts import EMBEDDING_MODEL, MAX_EMBEDDING_TEXT_LENGTH

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def split_text_into_chunks(text: str, max_length: int = MAX_EMBEDDING_TEXT_LENGTH) -> List[str]:
    """
    Split text into chunks to fit within Ollama's token limit.
    
    nomic-embed-text has a STRICT 2048 TOKEN limit.
    CRITICAL: Code tokenizes at 2-3 chars/token (NOT 4!), especially with symbols.
    
    Safe limit: 1500 chars = ~500-600 tokens, well under 2048 with 3x safety margin.
    
    Instead of truncating and losing data, we split into multiple chunks:
    - chunk_1, chunk_2, chunk_3, etc.
    - Each chunk gets embedded separately
    - All chunks are stored and searchable
    - No data is lost!
    """
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    chunk_size = max_length - 50  # Leave room for overlap and metadata
    
    # Try to split at natural boundaries (newlines, sentences, etc.)
    lines = text.split('\n')
    current_chunk = []
    current_length = 0
    
    for line in lines:
        line_length = len(line) + 1  # +1 for newline
        
        # If single line is too long, split it
        if line_length > chunk_size:
            # Save current chunk if any
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = []
                current_length = 0
            
            # Split long line by words
            words = line.split()
            word_chunk = []
            word_length = 0
            
            for word in words:
                word_len = len(word) + 1  # +1 for space
                if word_length + word_len > chunk_size:
                    if word_chunk:
                        chunks.append(' '.join(word_chunk))
                    word_chunk = [word]
                    word_length = word_len
                else:
                    word_chunk.append(word)
                    word_length += word_len
            
            if word_chunk:
                chunks.append(' '.join(word_chunk))
        
        # If adding this line exceeds chunk size, save current chunk
        elif current_length + line_length > chunk_size:
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
            current_chunk = [line]
            current_length = line_length
        
        # Add line to current chunk
        else:
            current_chunk.append(line)
            current_length += line_length
    
    # Add remaining chunk
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    if len(chunks) > 1:
        logger.info(f"Split text into {len(chunks)} chunks (original: {len(text)} chars)")
    
    return chunks


def truncate_text(text: str, max_length: int = MAX_EMBEDDING_TEXT_LENGTH) -> str:
    """
    DEPRECATED: Use split_text_into_chunks() instead to avoid data loss.
    
    This function is kept for backward compatibility but should not be used.
    """
    if len(text) <= max_length:
        return text
    
    truncated = text[:max_length - 20] + "\n... [truncated]"
    logger.warning(f"DEPRECATED TRUNCATION: {len(text)} -> {len(truncated)} chars. Consider using split_text_into_chunks() instead!")
    return truncated


class RateLimitedQueue:
    """
    Rate-limited queue for Ollama requests.
    Uses a semaphore to limit concurrent requests and prevent 500 errors.
    """
    
    def __init__(self, max_concurrent: int = 4, requests_per_second: float = 10.0):
        self.max_concurrent = max_concurrent
        self.min_interval = 1.0 / requests_per_second
        self._semaphore = threading.Semaphore(max_concurrent)
        self._last_request_time = 0.0
        self._time_lock = threading.Lock()
        self._stats = {
            "total_requests": 0,
            "queued_requests": 0,
            "active_requests": 0,
        }
        self._stats_lock = threading.Lock()
    
    def acquire(self):
        """Acquire a slot in the queue (blocks if at capacity)"""
        with self._stats_lock:
            self._stats["queued_requests"] += 1
        
        # Wait for a slot
        self._semaphore.acquire()
        
        with self._stats_lock:
            self._stats["queued_requests"] -= 1
            self._stats["active_requests"] += 1
            self._stats["total_requests"] += 1
        
        # Rate limiting - ensure minimum interval between requests
        with self._time_lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self._last_request_time = time.time()
    
    def release(self):
        """Release a slot back to the queue"""
        with self._stats_lock:
            self._stats["active_requests"] -= 1
        self._semaphore.release()
    
    def get_stats(self) -> Dict:
        """Get queue statistics"""
        with self._stats_lock:
            return self._stats.copy()


class ConnectionPool:
    """HTTP connection pool with keep-alive for Ollama"""
    
    def __init__(self, hosts: List[str], timeout: float = 60.0):
        self.hosts = hosts
        self.clients: Dict[str, httpx.Client] = {}
        self._lock = threading.Lock()
        self.timeout = timeout
        
        # Pre-create clients with connection pooling
        for host in hosts:
            self.clients[host] = httpx.Client(
                base_url=host,
                timeout=httpx.Timeout(timeout, connect=10.0),
                limits=httpx.Limits(
                    max_keepalive_connections=5,
                    max_connections=10,
                    keepalive_expiry=30.0
                )
            )
    
    def get_client(self, host: str) -> httpx.Client:
        """Get a client for the given host"""
        return self.clients.get(host)
    
    def close(self):
        """Close all connections"""
        for client in self.clients.values():
            client.close()


class EmbeddingEngine:
    """
    High-performance embedding engine with rate-limited queue.
    
    Key features:
    1. Rate-limited queue prevents Ollama overload (max 4 concurrent requests)
    2. Persistent SQLite cache for embeddings (80%+ cache hit rate typical)
    3. Connection pooling with keep-alive
    4. Automatic retry with exponential backoff
    """
    
    def __init__(self, model: str = EMBEDDING_MODEL, max_workers: int = 8, use_cache: bool = True):
        self.model = model
        self.use_cache = use_cache
        
        # Initialize persistent cache
        self._cache = EmbeddingCache() if use_cache else None
        self._cache_hits = 0
        self._cache_misses = 0
        
        # Get Ollama host from environment
        self.ollama_host = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
        logger.info(f"Using Ollama at: {self.ollama_host}")
        
        # Connection pool for HTTP keep-alive
        self._conn_pool = ConnectionPool([self.ollama_host])
        
        # Rate-limited queue - key to preventing 500 errors
        # IMPORTANT: Must match OLLAMA_NUM_PARALLEL in docker-compose.yml
        # Semantic chunking creates longer texts, so we use LOWER concurrency
        max_concurrent = int(os.getenv('OLLAMA_MAX_CONCURRENT', '2'))  # Reduced from 4
        self._request_queue = RateLimitedQueue(
            max_concurrent=max_concurrent,
            requests_per_second=8.0  # Reduced from 15 - more conservative for long texts
        )
        
        # Thread pool for parallel processing (limited by queue)
        self.max_workers = max_workers
        
        self._lock = threading.Lock()

    def _get_embedding_direct(self, text: str, max_retries: int = 5) -> List[float]:
        """
        Get embedding with rate limiting and retry logic.
        
        Handles oversized text by using first chunk only (as a fallback).
        Ideally, text should be pre-split by the caller (see watcher.py).
        """
        client = self._conn_pool.get_client(self.ollama_host)
        
        # Safety check: if text is too long, use first chunk
        # This is a fallback - callers should pre-split using split_text_into_chunks()
        if len(text) > MAX_EMBEDDING_TEXT_LENGTH:
            chunks = split_text_into_chunks(text)
            safe_text = chunks[0]
            if len(chunks) > 1:
                logger.warning(
                    f"Oversized text ({len(text)} chars) passed to _get_embedding_direct. "
                    f"Using first of {len(chunks)} chunks. "
                    f"Caller should pre-split using split_text_into_chunks()!"
                )
        else:
            safe_text = text
        
        last_error: Optional[Exception] = None
        
        for attempt in range(max_retries):
            self._request_queue.acquire()
            try:
                response = client.post(
                    "/api/embeddings",
                    json={"model": self.model, "prompt": safe_text}
                )
                response.raise_for_status()
                return response.json()["embedding"]
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code == 500 and attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 16)
                    logger.debug(f"Ollama 500 error, retry {attempt + 1}/{max_retries}")
                    if attempt >= 2:
                        self._check_ollama_health()
                    time.sleep(wait_time)
                elif e.response.status_code != 500:
                    raise
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(min(2 ** attempt, 16))
                else:
                    raise
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(min(2 ** attempt, 16))
                else:
                    raise
            finally:
                self._request_queue.release()
        
        raise last_error or RuntimeError("Embedding failed after all retries")
    
    def _check_ollama_health(self):
        """Check if Ollama is responsive."""
        try:
            client = self._conn_pool.get_client(self.ollama_host)
            response = client.get("/api/tags", timeout=5.0)
            if response.status_code != 200:
                logger.warning(f"Ollama health check failed: HTTP {response.status_code}")
        except Exception as e:
            logger.warning(f"Ollama unresponsive: {e}")

    def _get_embedding_cached(self, text: str) -> List[float]:
        """Get embedding with persistent cache"""
        if self._cache:
            content_hash = EmbeddingCache.hash_content(text)
            cached = self._cache.get(content_hash)
            if cached is not None:
                self._cache_hits += 1
                return cached
            
            self._cache_misses += 1
            embedding = self._get_embedding_direct(text)
            self._cache.set(content_hash, embedding, self.model)
            return embedding
        else:
            return self._get_embedding_direct(text)

    @lru_cache(maxsize=5000)
    def _get_embedding_lru_cached(self, text: str) -> Tuple[float, ...]:
        """LRU cache wrapper (returns tuple for hashability)."""
        return tuple(self._get_embedding_cached(text))

    def embed_sync(self, text: str, prefix: str = "") -> List[float]:
        """Get embedding for a single text."""
        return list(self._get_embedding_lru_cached(f"{prefix}{text}"))

    def embed_batch(self, texts: List[str], prefix: str = "") -> List[List[float]]:
        """
        Batch embedding with caching and parallel processing.
        
        Args:
            texts: List of texts to embed
            prefix: Optional prefix for search queries vs documents
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        prefixed_texts = [f"{prefix}{t}" for t in texts]
        results: List[Optional[List[float]]] = [None] * len(prefixed_texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []
        
        # Check cache first
        if self._cache:
            hashes = [EmbeddingCache.hash_content(t) for t in prefixed_texts]
            cached = self._cache.get_batch(hashes)
            
            for i, (text, h) in enumerate(zip(prefixed_texts, hashes)):
                if h in cached:
                    results[i] = cached[h]
                    self._cache_hits += 1
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)
                    self._cache_misses += 1
        else:
            uncached_indices = list(range(len(prefixed_texts)))
            uncached_texts = prefixed_texts
        
        # Process uncached texts in parallel
        if uncached_texts:
            new_embeddings = self._embed_parallel(uncached_texts)
            
            if self._cache:
                cache_items = [
                    (EmbeddingCache.hash_content(text), new_embeddings[i])
                    for i, text in enumerate(uncached_texts)
                ]
                self._cache.set_batch(cache_items, self.model)
            
            for i, idx in enumerate(uncached_indices):
                results[idx] = new_embeddings[i]
        
        return results

    def _embed_parallel(self, texts: List[str]) -> List[List[float]]:
        """Embed texts in parallel with rate limiting."""
        results: List[Optional[List[float]]] = [None] * len(texts)
        errors: List[Tuple[int, str]] = []
        
        def embed_one(idx: int, text: str) -> Tuple[int, Optional[List[float]], Optional[str]]:
            try:
                return idx, self._get_embedding_direct(text), None
            except Exception as e:
                return idx, None, str(e)
        
        num_workers = min(len(texts), self.max_workers)
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(embed_one, i, t) for i, t in enumerate(texts)]
            for future in as_completed(futures):
                idx, embedding, error = future.result()
                if error:
                    errors.append((idx, error))
                    results[idx] = [0.0] * 768  # Zero vector fallback
                else:
                    results[idx] = embedding
        
        if errors:
            logger.warning(f"{len(errors)} embeddings failed, using zero vectors")
        
        return results

    def get_cache_stats(self) -> Dict[str, any]:
        """Get cache and queue statistics."""
        total = self._cache_hits + self._cache_misses
        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": self._cache_hits / max(1, total),
            "queue": self._request_queue.get_stats(),
            "persistent_cache": self._cache.get_stats() if self._cache else None,
        }

    def clear_cache(self):
        """Clear all caches."""
        self._get_embedding_lru_cached.cache_clear()
        if self._cache:
            self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def close(self):
        """Cleanup connections."""
        self._conn_pool.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
