"""
Service discovery and management for multi-service codebases.

Features:
- Discover services/projects in a directory
- Select specific services to index
- Track which services are indexed
- Compare indexed vs current state
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Optional, Set
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class ServiceInfo:
    """Information about a discovered service."""
    name: str
    path: str
    file_count: int = 0
    indexed_chunks: int = 0
    last_indexed: Optional[str] = None
    files_changed: int = 0
    is_selected: bool = False


class ServiceManager:
    """Manages discovery and selection of services in a codebase."""
    
    # Files that indicate a service/project root
    SERVICE_INDICATORS = [
        'package.json',      # Node.js
        'pyproject.toml',    # Python
        'pom.xml',           # Maven/Java
        'build.gradle',      # Gradle/Java
        '*.csproj',          # .NET
        '*.sln',             # .NET Solution
        'Cargo.toml',        # Rust
        'go.mod',            # Go
        'Makefile',          # General
        'Dockerfile',        # Container
        'docker-compose.yml', # Docker Compose
        'docker-compose.yaml',
    ]
    
    # Directories to skip when discovering services
    SKIP_DIRS = {
        '.git', '.svn', '.hg',
        'node_modules', 'vendor', 'venv', '.venv',
        'bin', 'obj', 'target', 'dist', 'build',
        '__pycache__', '.pytest_cache', '.mypy_cache',
        '.idea', '.vscode', '.vs',
    }
    
    def __init__(self):
        self.config_dir = Path("/data/services")
        self.config_file = self.config_dir / "service_config.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def discover_services(self, root_path: str, max_depth: int = 3) -> List[ServiceInfo]:
        """
        Discover services/projects in a directory.
        
        Looks for common project indicators to identify service boundaries.
        """
        services = []
        root_path = os.path.abspath(root_path)
        
        if not os.path.exists(root_path):
            return services
        
        # Check if root itself is a service
        if self._is_service_root(root_path):
            services.append(self._create_service_info(root_path, os.path.basename(root_path)))
        
        # Walk directory tree
        for entry in os.scandir(root_path):
            if entry.is_dir() and entry.name not in self.SKIP_DIRS and not entry.name.startswith('.'):
                self._discover_recursive(entry.path, services, 1, max_depth)
        
        # Sort by name
        services.sort(key=lambda s: s.name.lower())
        
        return services
    
    def _discover_recursive(self, path: str, services: List[ServiceInfo], depth: int, max_depth: int):
        """Recursively discover services."""
        if depth > max_depth:
            return
        
        if self._is_service_root(path):
            services.append(self._create_service_info(path, os.path.basename(path)))
            return  # Don't look deeper once we find a service
        
        # Continue searching
        try:
            for entry in os.scandir(path):
                if entry.is_dir() and entry.name not in self.SKIP_DIRS and not entry.name.startswith('.'):
                    self._discover_recursive(entry.path, services, depth + 1, max_depth)
        except PermissionError:
            pass
    
    def _is_service_root(self, path: str) -> bool:
        """Check if a directory is a service root."""
        import glob
        
        for indicator in self.SERVICE_INDICATORS:
            if '*' in indicator:
                # Glob pattern
                matches = glob.glob(os.path.join(path, indicator))
                if matches:
                    return True
            else:
                if os.path.exists(os.path.join(path, indicator)):
                    return True
        
        return False
    
    def _create_service_info(self, path: str, name: str) -> ServiceInfo:
        """Create ServiceInfo with file counts."""
        from src.librarian.chunking import get_factory
        factory = get_factory()
        
        file_count = 0
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS and not d.startswith('.')]
            for file in files:
                filepath = os.path.join(root, file)
                if factory.get_chunker(filepath):
                    file_count += 1
                    if file_count > 5000:  # Limit for performance
                        break
            if file_count > 5000:
                break
        
        return ServiceInfo(
            name=name,
            path=path,
            file_count=file_count
        )
    
    def get_indexed_services(self) -> Dict[str, dict]:
        """Get information about what's been indexed from each service path."""
        from src.librarian.db import LanceDBManager
        
        try:
            db = LanceDBManager()
            results = db.table.search().limit(100000).select(["filepath", "indexed_at"]).to_list()
        except:
            return {}
        
        # Group by service path
        services = {}
        for res in results:
            filepath = res.get('filepath', '')
            indexed_at = res.get('indexed_at', '')
            
            # Find the service root from filepath
            # Assumes paths like /app/codebase/service-name/... or /path/to/service-name/...
            parts = filepath.split('/')
            
            # Try to find a meaningful service name
            service_name = None
            for i, part in enumerate(parts):
                if part in ['app', 'codebase', '']:
                    continue
                service_name = part
                break
            
            if service_name:
                if service_name not in services:
                    services[service_name] = {
                        'chunks': 0,
                        'files': set(),
                        'last_indexed': indexed_at
                    }
                services[service_name]['chunks'] += 1
                services[service_name]['files'].add(filepath)
                if indexed_at > services[service_name]['last_indexed']:
                    services[service_name]['last_indexed'] = indexed_at
        
        # Convert sets to counts
        for name, info in services.items():
            info['file_count'] = len(info['files'])
            del info['files']
        
        return services
    
    def save_service_selection(self, root_path: str, selected_services: List[str]):
        """Save the selected services for a root path."""
        config = self._load_config()
        
        config[root_path] = {
            'selected_services': selected_services,
            'updated_at': datetime.now().isoformat()
        }
        
        self._save_config(config)
    
    def get_service_selection(self, root_path: str) -> List[str]:
        """Get previously selected services for a root path."""
        config = self._load_config()
        return config.get(root_path, {}).get('selected_services', [])
    
    def _load_config(self) -> dict:
        """Load configuration from file."""
        if not self.config_file.exists():
            return {}
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    
    def _save_config(self, config: dict):
        """Save configuration to file."""
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def clear_service_index(self, service_path: str) -> int:
        """
        Remove indexed data for a specific service.
        
        Returns the number of chunks removed.
        """
        from src.librarian.db import LanceDBManager
        from src.librarian.cache import FileHashCache
        
        db = LanceDBManager()
        
        # Find all chunks that belong to this service
        results = db.table.search().limit(100000).select(["filepath"]).to_list()
        
        # Normalize path for comparison
        service_path = os.path.abspath(service_path)
        
        chunks_to_remove = []
        files_to_clear = set()
        
        for i, res in enumerate(results):
            filepath = res.get('filepath', '')
            # Check if file is under service path
            if filepath.startswith(service_path) or f"/codebase/{os.path.basename(service_path)}/" in filepath:
                chunks_to_remove.append(i)
                files_to_clear.add(filepath)
        
        if chunks_to_remove:
            # LanceDB doesn't have easy row deletion, so we'll need to recreate
            # For now, we'll clear the file hash cache for these files
            file_cache = FileHashCache()
            for filepath in files_to_clear:
                file_cache.remove(filepath)
        
        return len(chunks_to_remove)


# Global singleton
_service_manager = None


def get_service_manager() -> ServiceManager:
    """Get the global service manager instance."""
    global _service_manager
    if _service_manager is None:
        _service_manager = ServiceManager()
    return _service_manager
