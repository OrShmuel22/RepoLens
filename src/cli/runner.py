#!/usr/bin/env python3
"""
Codebase Librarian - Easy CLI Runner

Usage:
    # From host (with docker):
    ./librarian menu                    # Interactive menu
    ./librarian index                   # Index default workspace
    ./librarian index /path/to/code     # Index specific path
    ./librarian search "query"          # Search code
    ./librarian status                  # View status
    ./librarian services                # Manage services
    
    # Inside docker:
    python -m src.cli.runner menu
"""

import sys
import os

# Add src to path
sys.path.insert(0, '/app')

from src.cli.manage import app

if __name__ == "__main__":
    app()
