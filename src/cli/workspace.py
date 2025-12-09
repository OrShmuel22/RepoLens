"""
Workspace management - handles path persistence and smart defaults.

Features:
- Auto-detects current directory or mounted codebase
- Remembers last used path across sessions
- Provides smart defaults for all operations
"""

import os
import json
from pathlib import Path
from typing import Optional
from datetime import datetime


class WorkspaceManager:
    """Manages workspace paths and persistence."""
    
    def __init__(self):
        # Store in data directory (persists in Docker volume)
        self.config_dir = Path("/data/workspace")
        self.config_file = self.config_dir / "last_workspace.json"
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def get_default_path(self) -> str:
        """
        Get the best default path to use.
        
        Priority:
        1. Last used path (if still exists)
        2. /app/codebase (if in Docker and exists)
        3. Current working directory
        """
        # Try last used path
        last_path = self.get_last_path()
        if last_path and os.path.exists(last_path):
            return last_path
        
        # Try Docker mounted codebase
        docker_path = "/app/codebase"
        if os.path.exists(docker_path):
            return docker_path
        
        # Fall back to current directory
        return os.getcwd()
    
    def get_last_path(self) -> Optional[str]:
        """Get the last used path from cache."""
        if not self.config_file.exists():
            return None
        
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
                return data.get('last_path')
        except (json.JSONDecodeError, IOError):
            return None
    
    def save_last_path(self, path: str):
        """Save path for future use."""
        # Normalize path
        path = os.path.abspath(path)
        
        data = {
            'last_path': path,
            'updated_at': datetime.now().isoformat(),
            'exists': os.path.exists(path)
        }
        
        try:
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=2)
        except IOError:
            # Fail silently - not critical
            pass
    
    def get_workspace_info(self) -> dict:
        """Get information about the current workspace."""
        default_path = self.get_default_path()
        
        info = {
            'default_path': default_path,
            'exists': os.path.exists(default_path),
            'is_docker': os.path.exists('/app/codebase'),
            'last_used': self.get_last_path()
        }
        
        if info['exists']:
            # Count supported files
            from src.librarian.chunking import get_factory
            factory = get_factory()
            
            file_count = 0
            for root, dirs, files in os.walk(default_path):
                # Skip common ignored directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and 
                          d not in ['bin', 'obj', 'node_modules', '__pycache__', 'venv']]
                
                for file in files:
                    filepath = os.path.join(root, file)
                    if factory.get_chunker(filepath):
                        file_count += 1
                        
                # Limit scan to avoid long delays
                if file_count > 1000:
                    info['file_count'] = f"{file_count}+"
                    break
            else:
                info['file_count'] = file_count
        
        return info
    
    def detect_project_name(self, path: str) -> str:
        """Detect a friendly project name from path."""
        path = os.path.abspath(path)
        
        # Try common project indicators
        indicators = [
            '.git',
            '.sln',  # Visual Studio solution
            'package.json',  # Node project
            'pyproject.toml',  # Python project
            'pom.xml',  # Maven project
            'build.gradle'  # Gradle project
        ]
        
        for indicator in indicators:
            indicator_path = os.path.join(path, indicator)
            if os.path.exists(indicator_path):
                # Use directory name
                return os.path.basename(path)
        
        # Fall back to directory name
        return os.path.basename(path)


# Global singleton
_workspace_manager = None


def get_workspace_manager() -> WorkspaceManager:
    """Get the global workspace manager instance."""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager()
    return _workspace_manager
