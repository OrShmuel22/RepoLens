"""
MCP Server for RepoLens with optimized search and caching.
"""

from mcp.server.fastmcp import FastMCP
from typing import Optional, Dict, Any
import threading
from .watcher import start_watching as start_watching_proc, LibrarianWatcher
from .db import LanceDBManager
from .embeddings import EmbeddingEngine
from .cache import EmbeddingCache, FileHashCache

# Initialize core components with caching
engine = EmbeddingEngine(use_cache=True)  # Singleton with caching enabled
db = LanceDBManager()
db.set_dimension(engine.dimension)  # Set correct dimension from embedding model
mcp = FastMCP("RepoLens")

# Watcher state
watcher_thread = None
watcher_instance: Optional[LibrarianWatcher] = None


@mcp.tool()
def start_watching(root_dir: str) -> str:
    """Initializes background watcher for the specified directory."""
    global watcher_thread, watcher_instance

    if watcher_thread and watcher_thread.is_alive():
        return "Watcher already running."

    def run_watcher():
        start_watching_proc(root_dir)

    watcher_thread = threading.Thread(target=run_watcher, daemon=True)
    watcher_thread.start()
    return f"Started watching {root_dir}"


@mcp.tool()
def search_codebase(query: str, file_type: Optional[str] = None, limit: int = 10) -> str:
    """
    Performs vector search with architecture node boosting.

    Args:
        query: Search query
        file_type: Optional file type filter
        limit: Maximum number of results

    Returns:
        Formatted search results with context headers
    """
    # 1. Embed query with prefix (uses cached engine)
    query_vector = engine.embed_sync(query, prefix="search_query: ")

    # 2. Search (fetch more to allow re-ranking)
    results = db.search(query_vector, limit=limit * 3, file_type=file_type)

    if not results:
        return "No results found."

    # 3. Re-rank with architecture boosting
    scored_results = []
    for r in results:
        dist = r.get('_distance', 1.0)
        # Boost architecture nodes by reducing their distance
        if r.get('is_architecture_node'):
            dist = dist / 1.5
        scored_results.append((dist, r))

    # Sort by boosted distance
    scored_results.sort(key=lambda x: x[0])

    # Take top limit
    final_results = [x[1] for x in scored_results[:limit]]

    # Format results
    output = []
    for r in final_results:
        arch_flag = "[ARCH] " if r.get("is_architecture_node") else ""
        header = r.get('context_header', 'Unknown')
        content = r.get('content', '')
        output.append(f"{arch_flag}{header}\n{content}\n---")

    return "\n".join(output)


@mcp.tool()
def get_architecture(directory: str) -> str:
    """
    Retrieves generated summaries for classes in a namespace/folder.

    Args:
        directory: Directory path to search for summaries

    Returns:
        Formatted summaries for files in the directory
    """
    # Sanitize input to prevent injection
    safe_directory = directory.replace("'", "''").replace("%", "\\%")

    try:
        results = db.table.search().where(
            f"filepath LIKE '%{safe_directory}%' AND summary != ''"
        ).limit(50).to_list()

        # Deduplicate by filepath
        seen = set()
        summaries = []
        for r in results:
            filepath = r.get('filepath', '')
            if filepath and filepath not in seen:
                summary = r.get('summary', '')
                summaries.append(f"File: {filepath}\nSummary: {summary}")
                seen.add(filepath)

        if not summaries:
            return "No architecture summaries found for this directory."

        return "\n\n".join(summaries)
    except Exception as e:
        return f"Error retrieving architecture: {e}"


@mcp.tool()
def get_stats() -> Dict[str, Any]:
    """Returns index and cache statistics."""
    stats = db.get_stats()
    stats["cache"] = engine.get_cache_stats()
    return stats


@mcp.tool()
def get_detailed_stats() -> Dict[str, Any]:
    """Returns detailed statistics including cache performance."""
    db_stats = db.get_detailed_stats()
    cache_stats = engine.get_cache_stats()

    # File cache stats
    try:
        file_cache = FileHashCache()
        file_stats = file_cache.get_stats()
    except:
        file_stats = {}

    return {
        "database": db_stats,
        "embedding_cache": cache_stats,
        "file_cache": file_stats
    }


@mcp.tool()
def clear_index() -> str:
    """Wipes LanceDB and all caches."""
    db.clear()
    engine.clear_cache()

    try:
        file_cache = FileHashCache()
        file_cache.clear()
    except:
        pass

    return "Index and caches cleared."


@mcp.tool()
def optimize_database() -> str:
    """Optimizes the database for better search performance."""
    try:
        db.optimize()
        return "Database optimized successfully."
    except Exception as e:
        return f"Optimization error: {e}"


if __name__ == "__main__":
    mcp.run()
