"""
Persistent caching layer for embeddings and file hashes.
Provides disk-based caching to speed up re-indexing.
"""

import hashlib
import json
import os
import pickle
import sqlite3
import threading
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from .consts import LANCEDB_PATH

# Cache directory alongside LanceDB
CACHE_DIR = os.path.join(os.path.dirname(LANCEDB_PATH), ".cache")


class EmbeddingCache:
    """
    SQLite-based persistent cache for embeddings.
    Uses content hash as key for deduplication.
    Thread-safe with connection pooling.
    """
    
    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.db_path = os.path.join(cache_dir, "embeddings.db")
        self._local = threading.local()
        self._init_db()
        
    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local connection"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent access
            self._local.conn.execute("PRAGMA synchronous=NORMAL")  # Faster writes
        return self._local.conn
    
    def _init_db(self):
        """Initialize the cache database"""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embeddings (
                content_hash TEXT PRIMARY KEY,
                embedding BLOB,
                model TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_model ON embeddings(model)")
        conn.commit()
    
    @staticmethod
    def hash_content(text: str) -> str:
        """Generate a hash for content"""
        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]
    
    def get(self, content_hash: str) -> Optional[List[float]]:
        """Get embedding from cache"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT embedding FROM embeddings WHERE content_hash = ?",
            (content_hash,)
        )
        row = cursor.fetchone()
        if row:
            return pickle.loads(row[0])
        return None
    
    def get_batch(self, content_hashes: List[str]) -> Dict[str, List[float]]:
        """Get multiple embeddings from cache"""
        if not content_hashes:
            return {}
        
        conn = self._get_conn()
        placeholders = ','.join('?' * len(content_hashes))
        cursor = conn.execute(
            f"SELECT content_hash, embedding FROM embeddings WHERE content_hash IN ({placeholders})",
            content_hashes
        )
        
        results = {}
        for row in cursor.fetchall():
            results[row[0]] = pickle.loads(row[1])
        return results
    
    def set(self, content_hash: str, embedding: List[float], model: str = ""):
        """Store embedding in cache"""
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO embeddings (content_hash, embedding, model) VALUES (?, ?, ?)",
            (content_hash, pickle.dumps(embedding), model)
        )
        conn.commit()
    
    def set_batch(self, items: List[Tuple[str, List[float]]], model: str = ""):
        """Store multiple embeddings in cache"""
        if not items:
            return
        
        conn = self._get_conn()
        conn.executemany(
            "INSERT OR REPLACE INTO embeddings (content_hash, embedding, model) VALUES (?, ?, ?)",
            [(h, pickle.dumps(e), model) for h, e in items]
        )
        conn.commit()
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*), SUM(LENGTH(embedding)) FROM embeddings")
        row = cursor.fetchone()
        return {
            "entries": row[0] or 0,
            "size_bytes": row[1] or 0,
            "size_mb": round((row[1] or 0) / (1024 * 1024), 2)
        }
    
    def clear(self):
        """Clear the cache"""
        conn = self._get_conn()
        conn.execute("DELETE FROM embeddings")
        conn.commit()


class FileHashCache:
    """
    Tracks file hashes to enable delta indexing.
    Only re-index files that have changed.
    """
    
    def __init__(self, cache_dir: str = CACHE_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.db_path = os.path.join(cache_dir, "file_hashes.db")
        self._local = threading.local()
        self._init_db()
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get thread-local connection"""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn
    
    def _init_db(self):
        """Initialize the hash database"""
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS file_hashes (
                filepath TEXT PRIMARY KEY,
                content_hash TEXT,
                mtime REAL,
                size INTEGER,
                chunk_count INTEGER,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    
    @staticmethod
    def hash_file(filepath: str) -> Tuple[str, float, int]:
        """Generate hash for a file, returns (hash, mtime, size)"""
        stat = os.stat(filepath)
        with open(filepath, 'rb') as f:
            content_hash = hashlib.sha256(f.read()).hexdigest()[:32]
        return content_hash, stat.st_mtime, stat.st_size
    
    def get_indexed_files(self) -> Dict[str, Tuple[str, float, int]]:
        """Get all indexed files with their hashes"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT filepath, content_hash, mtime, size FROM file_hashes")
        return {row[0]: (row[1], row[2], row[3]) for row in cursor.fetchall()}
    
    def is_file_changed(self, filepath: str) -> bool:
        """Check if a file has changed since last indexing"""
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT content_hash, mtime, size FROM file_hashes WHERE filepath = ?",
            (filepath,)
        )
        row = cursor.fetchone()
        
        if not row:
            return True  # Not indexed yet
        
        try:
            stat = os.stat(filepath)
            # Quick check: mtime and size
            if row[1] != stat.st_mtime or row[2] != stat.st_size:
                return True
            return False
        except OSError:
            return True  # File might have been deleted
    
    def get_changed_files(self, filepaths: List[str]) -> List[str]:
        """Filter list to only files that have changed"""
        indexed = self.get_indexed_files()
        changed = []
        
        for fp in filepaths:
            if fp not in indexed:
                changed.append(fp)
                continue
            
            try:
                stat = os.stat(fp)
                old_hash, old_mtime, old_size = indexed[fp]
                
                # Quick check: mtime and size
                if old_mtime != stat.st_mtime or old_size != stat.st_size:
                    changed.append(fp)
            except OSError:
                changed.append(fp)
        
        return changed
    
    def update_file(self, filepath: str, content_hash: str, mtime: float, size: int, chunk_count: int):
        """Update hash record for a file"""
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO file_hashes 
               (filepath, content_hash, mtime, size, chunk_count, indexed_at) 
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            (filepath, content_hash, mtime, size, chunk_count)
        )
        conn.commit()
    
    def update_files_batch(self, items: List[Tuple[str, str, float, int, int]]):
        """Batch update hash records"""
        if not items:
            return
        
        conn = self._get_conn()
        conn.executemany(
            """INSERT OR REPLACE INTO file_hashes 
               (filepath, content_hash, mtime, size, chunk_count, indexed_at) 
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
            items
        )
        conn.commit()
    
    def remove_file(self, filepath: str):
        """Remove a file from the hash cache"""
        conn = self._get_conn()
        conn.execute("DELETE FROM file_hashes WHERE filepath = ?", (filepath,))
        conn.commit()
    
    def get_stats(self) -> Dict:
        """Get cache statistics"""
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*), SUM(chunk_count) FROM file_hashes")
        row = cursor.fetchone()
        return {
            "indexed_files": row[0] or 0,
            "total_chunks": row[1] or 0
        }
    
    def clear(self):
        """Clear the hash cache"""
        conn = self._get_conn()
        conn.execute("DELETE FROM file_hashes")
        conn.commit()
