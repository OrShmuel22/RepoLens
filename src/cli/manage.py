"""
CLI management commands with performance optimizations:
- Delta indexing (only index changed files)
- Higher parallelism
- Better progress tracking
- Cache statistics
- Interactive menu for easy navigation

SIMPLIFIED CLI - Developer-friendly interface:
- Single entry point with smart defaults
- 4 core actions: Index, Search, Status, Settings
- First-run guidance for new users
"""

import typer
import time
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple, Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.syntax import Syntax
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm, IntPrompt

from src.librarian.watcher import start_watching, IndexingPipeline
from src.librarian.db import LanceDBManager
from src.librarian.embeddings import EmbeddingEngine
from src.librarian.cache import FileHashCache, EmbeddingCache
from src.cli.workspace import get_workspace_manager
from src.cli.services import get_service_manager

app = typer.Typer(
    help="🔍 Codebase Librarian - Learn from your codebase with semantic search",
    no_args_is_help=False,
    invoke_without_command=True
)
console = Console()

# Initialize workspace manager
workspace = get_workspace_manager()
service_mgr = get_service_manager()


def format_time(seconds: float) -> str:
    """Format seconds into human-readable string"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds/60)}m {int(seconds%60)}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"


@app.command()
def index(
    path: str = typer.Argument(None, help="Directory to index (auto-detected if not specified)"),
    skip_confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    force: bool = typer.Option(False, "--force", "-f", help="Force re-index all files (ignore delta)"),
    workers: int = typer.Option(8, "--workers", "-w", help="Number of parallel workers")
):
    """
    Scans and indexes a codebase.
    
    Features:
    - Auto-detects directory if not specified
    - Remembers last used path
    - Delta indexing: only indexes changed files (use --force to re-index all)
    - Parallel processing with configurable workers
    - Persistent embedding cache for faster re-indexing
    """
    
    # Auto-detect path if not provided
    if path is None:
        path = workspace.get_default_path()
        project_name = workspace.detect_project_name(path)
        console.print(f"[dim]💡 Auto-detected: {project_name} ({path})[/dim]\n")
    
    if not os.path.exists(path):
        console.print(f"[red]Path {path} does not exist.[/red]")
        return
    
    # Save for next time
    workspace.save_last_path(path)
        
    console.print(f"[bold green]Indexing {path}...[/bold green]")
    
    # Count total .cs files first
    console.print("[yellow]Scanning directory...[/yellow]")
    cs_files = []
    
    for root, dirs, files in os.walk(path):
        # Skip ignored directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['bin', 'obj', 'node_modules']]
        
        for file in files:
            if file.endswith(".cs"):
                cs_files.append(os.path.join(root, file))
    
    total_files = len(cs_files)
    
    if total_files == 0:
        console.print("[yellow]No C# files found in the specified directory.[/yellow]")
        return
    
    # Initialize pipeline for delta indexing check
    pipeline = IndexingPipeline(max_workers=workers)
    
    # Check for delta indexing
    files_to_index = cs_files
    skipped_files = 0
    
    if not force:
        console.print("[cyan]Checking for changed files (delta indexing)...[/cyan]")
        files_to_index = pipeline.get_changed_files(cs_files)
        skipped_files = total_files - len(files_to_index)
        
        if skipped_files > 0:
            console.print(f"[green]✓ Skipping {skipped_files:,} unchanged files[/green]")
    
    if len(files_to_index) == 0:
        console.print("[bold green]✓ All files already indexed and up-to-date![/bold green]")
        return
    
    # Estimate time (optimized: ~8-15 files/sec with caching)
    est_rate = 10.0 if skipped_files > 0 else 5.0  # Faster with warm cache
    est_seconds = len(files_to_index) / est_rate
    est_time = format_time(est_seconds)
    
    console.print(f"[cyan]Files to index: {len(files_to_index):,} / {total_files:,}[/cyan]")
    console.print(f"[yellow]Estimated time: ~{est_time}[/yellow]")
    console.print("")
    
    # Confirmation for large jobs
    if len(files_to_index) > 1000 and not skip_confirm:
        console.print(f"[bold yellow]⚠️  Large indexing job ({len(files_to_index):,} files)[/bold yellow]")
        if not Confirm.ask(f"This will take approximately {est_time}. Continue?", default=False):
            console.print("[yellow]Indexing cancelled[/yellow]")
            return
        console.print("")
    
    files_indexed = 0
    total_chunks = 0
    start_time = time.time()
    errors = []
    
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        "•",
        "[cyan]{task.completed}/{task.total}",
        "•",
        "[green]{task.fields[chunks]} chunks",
        "•",
        "[yellow]{task.fields[speed]}/s",
        "•",
        TimeRemainingColumn(),
        console=console
    ) as progress:
        
        task = progress.add_task(
            "[bold blue]Indexing...", 
            total=len(files_to_index),
            chunks=0,
            speed="0.0"
        )
        
        def process_file_wrapper(filepath: str) -> Tuple[int, int, str]:
            """Process a single file and return (success, chunks, error)"""
            try:
                success, chunks, error = pipeline.process_file(filepath)
                return success, chunks, error or ""
            except Exception as e:
                return 0, 0, f"{filepath}: {str(e)}"
        
        # Process files in parallel
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_file_wrapper, fp): fp for fp in files_to_index}
            
            for future in as_completed(futures):
                success, chunks, error = future.result()
                files_indexed += success
                total_chunks += chunks
                if error:
                    errors.append(error)
                
                # Calculate speed
                elapsed = time.time() - start_time
                speed = files_indexed / max(0.1, elapsed)
                
                progress.update(
                    task, 
                    advance=1,
                    chunks=total_chunks,
                    speed=f"{speed:.1f}"
                )
    
    # Final statistics
    elapsed_total = time.time() - start_time
    
    # Get actual chunk count from database
    db = LanceDBManager()
    actual_chunks = db.table.count_rows()
    
    # Get cache stats
    cache_stats = pipeline.embeddings.get_cache_stats()
    
    console.print("")
    console.print("[bold green]✓ Indexing Complete![/bold green]")
    console.print("")
    
    # Statistics table
    stats_table = Table(show_header=False, box=None)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="green")
    
    stats_table.add_row("Files processed", f"{files_indexed:,}")
    stats_table.add_row("Files skipped (unchanged)", f"{skipped_files:,}")
    stats_table.add_row("Chunks created", f"{total_chunks:,}")
    stats_table.add_row("Total chunks in DB", f"{actual_chunks:,}")
    stats_table.add_row("Total time", format_time(elapsed_total))
    stats_table.add_row("Avg per file", f"{elapsed_total/max(1, files_indexed):.2f}s")
    stats_table.add_row("Throughput", f"{files_indexed/max(0.1, elapsed_total):.1f} files/sec")
    
    # Cache stats
    hit_rate = cache_stats.get('hit_rate', 0) * 100
    stats_table.add_row("Embedding cache hit rate", f"{hit_rate:.1f}%")
    
    console.print(stats_table)
    
    if errors:
        # Group errors by type
        error_500 = [e for e in errors if "500" in e]
        other_errors = [e for e in errors if "500" not in e]
        
        console.print(f"\n[yellow]⚠️  {len(errors)} files had errors[/yellow]")
        
        if error_500:
            console.print(f"  [dim]• {len(error_500)} files failed due to Ollama overload (500 errors) - these can be retried[/dim]")
        
        if other_errors:
            console.print(f"  [dim]• {len(other_errors)} files had other errors:[/dim]")
            for err in other_errors[:5]:
                console.print(f"    [red]{err}[/red]")
            if len(other_errors) > 5:
                console.print(f"    [dim]... and {len(other_errors) - 5} more[/dim]")
    
    console.print("")


@app.command()
def search(query: str, limit: int = 5):
    """Searches the codebase."""
    db = LanceDBManager()
    engine = EmbeddingEngine()
    
    start_time = time.time()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Embedding query...", total=None)
        query_vec = engine.embed_sync(query)
        
        progress.update(task, description="Searching vector DB...")
        results = db.search(query_vec, limit=limit)
    
    search_time = time.time() - start_time
    
    console.print(f"\n[bold]Results for '[cyan]{query}[/cyan]'[/bold] ({search_time:.2f}s)\n")
    
    for i, res in enumerate(results):
        distance = res.get('_distance', 0)
        filepath = res.get('filepath', 'unknown')
        filename = os.path.basename(filepath)
        
        # Format header
        arch_badge = " [yellow]⚡ARCH[/yellow]" if res.get('is_architecture_node') else ""
        console.print(f"[bold blue]#{i+1}[/bold blue] {res['context_header']}{arch_badge}")
        console.print(f"    [dim]{filename}[/dim] • [dim]distance: {distance:.4f}[/dim]")
        
        # Highlight code
        snippet = res['content'][:500] + "..." if len(res['content']) > 500 else res['content']
        syntax = Syntax(snippet, "csharp", theme="monokai", line_numbers=True)
        console.print(syntax)
        console.print("")


@app.command()
def watch(path: str = typer.Argument(None, help="Directory to watch (auto-detected if not specified)")):
    """Starts the file watcher."""
    
    # Auto-detect path if not provided
    if path is None:
        path = workspace.get_default_path()
        project_name = workspace.detect_project_name(path)
        console.print(f"[dim]💡 Auto-detected: {project_name} ({path})[/dim]\n")
    
    if not os.path.exists(path):
        console.print(f"[red]Path {path} does not exist.[/red]")
        return
    
    # Save for next time
    workspace.save_last_path(path)
    
    console.print(f"[bold yellow]Starting watcher on {path}...[/bold yellow]")
    start_watching(path)


@app.command()
def status(limit: int = 20):
    """Shows the indexing status of top-level directories."""
    try:
        db = LanceDBManager()
        console.print("\n[bold cyan]📊 Indexing Status[/bold cyan]")
        console.print("[dim]Analyzing indexed files...[/dim]\n")
        
        results = db.table.search().limit(100000).select(["filepath"]).to_list()
        
        if not results:
            console.print("[yellow]No files indexed.[/yellow]\n")
            return

        # Aggregate by top-level directory
        stats = {}
        total_chunks = len(results)
        
        for res in results:
            path = res.get('filepath', '')
            if not path:
                continue
            
            if path.startswith('/app/codebase/'):
                rel_path = path[len('/app/codebase/'):]
            else:
                rel_path = path
                
            parts = rel_path.split('/')
            if parts:
                top_dir = parts[0]
                stats[top_dir] = stats.get(top_dir, 0) + 1
        
        # Display results
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Directory", style="white")
        table.add_column("Chunks", style="green", justify="right")
        table.add_column("Coverage", style="yellow", justify="right")
        
        sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
        
        for dirname, count in sorted_stats[:limit]:
            percentage = (count / total_chunks) * 100
            table.add_row(dirname, f"{count:,}", f"{percentage:.1f}%")
            
        console.print(table)
        
        if len(sorted_stats) > limit:
            console.print(f"\n[dim]... and {len(sorted_stats) - limit} more directories[/dim]")
            
        console.print(f"\n[bold]Total Chunks:[/bold] [green]{total_chunks:,}[/green]\n")
        
    except Exception as e:
        console.print(f"[red]Error fetching status: {e}[/red]")


@app.command()
def cache_stats():
    """Shows cache statistics for embeddings and file hashes."""
    console.print("\n[bold cyan]📊 Cache Statistics[/bold cyan]\n")
    
    try:
        # Embedding cache stats
        embed_cache = EmbeddingCache()
        embed_stats = embed_cache.get_stats()
        
        console.print("[bold]Embedding Cache:[/bold]")
        console.print(f"  Entries: [green]{embed_stats['entries']:,}[/green]")
        console.print(f"  Size: [green]{embed_stats['size_mb']:.1f} MB[/green]")
        
        # File hash cache stats
        file_cache = FileHashCache()
        file_stats = file_cache.get_stats()
        
        console.print("\n[bold]File Hash Cache:[/bold]")
        console.print(f"  Indexed files: [green]{file_stats['indexed_files']:,}[/green]")
        console.print(f"  Total chunks tracked: [green]{file_stats['total_chunks']:,}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error getting cache stats: {e}[/red]")
    
    console.print("")


@app.command()
def clear_cache():
    """Clears all caches (embedding cache, file hash cache)."""
    if not Confirm.ask("[yellow]Clear all caches? This will cause full re-indexing on next run.[/yellow]"):
        console.print("[dim]Cancelled[/dim]")
        return
    
    try:
        embed_cache = EmbeddingCache()
        embed_cache.clear()
        
        file_cache = FileHashCache()
        file_cache.clear()
        
        console.print("[green]✓ All caches cleared[/green]")
    except Exception as e:
        console.print(f"[red]Error clearing caches: {e}[/red]")


@app.command()
def clear_database():
    """Clears the entire database (all indexed data)."""
    if not Confirm.ask("[bold red]Clear entire database? This will delete ALL indexed data![/bold red]", default=False):
        console.print("[dim]Cancelled[/dim]")
        return
    
    try:
        import shutil
        from src.librarian.consts import LANCEDB_PATH
        
        if os.path.exists(LANCEDB_PATH):
            shutil.rmtree(LANCEDB_PATH)
            console.print(f"[green]✓ Database deleted: {LANCEDB_PATH}[/green]")
        else:
            console.print(f"[yellow]No database found at: {LANCEDB_PATH}[/yellow]")
        
        # Also clear caches
        embed_cache = EmbeddingCache()
        embed_cache.clear()
        
        file_cache = FileHashCache()
        file_cache.clear()
        
        console.print("[green]✓ All caches cleared[/green]")
        console.print("[cyan]Database and caches cleared. Re-index to populate.[/cyan]")
    except Exception as e:
        console.print(f"[red]Error clearing database: {e}[/red]")


@app.command()
def optimize():
    """Optimizes the database (compacts files, creates indexes)."""
    console.print("[cyan]Optimizing database...[/cyan]")
    
    try:
        db = LanceDBManager()
        db.optimize()
        console.print("[green]✓ Database optimized[/green]")
    except Exception as e:
        console.print(f"[red]Error optimizing: {e}[/red]")


@app.command()
def services(
    path: str = typer.Argument(None, help="Root directory containing services"),
):
    """
    Discover and manage services in a codebase.
    
    Scans a directory for services/projects and allows selective indexing.
    """
    console.print("\n[bold cyan]🔍 Service Discovery[/bold cyan]\n")
    
    # Get path
    if path is None:
        path = workspace.get_default_path()
        console.print(f"[dim]Using: {path}[/dim]\n")
    
    if not os.path.exists(path):
        console.print(f"[red]Path does not exist: {path}[/red]")
        return
    
    # Discover services
    console.print("[yellow]Discovering services...[/yellow]")
    discovered = service_mgr.discover_services(path)
    
    if not discovered:
        console.print("[yellow]No services found in the directory.[/yellow]")
        console.print("[dim]Looking for: package.json, pyproject.toml, *.csproj, pom.xml, etc.[/dim]")
        return
    
    # Get indexed services info
    indexed_info = service_mgr.get_indexed_services()
    
    # Get previous selection
    previous_selection = service_mgr.get_service_selection(path)
    
    # Show discovered services
    console.print(f"\n[bold]Found {len(discovered)} services:[/bold]\n")
    
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Service", style="white")
    table.add_column("Files", style="cyan", justify="right")
    table.add_column("Indexed", style="green", justify="right")
    table.add_column("Status", style="yellow")
    
    for i, svc in enumerate(discovered, 1):
        idx_info = indexed_info.get(svc.name, {})
        idx_chunks = idx_info.get('chunks', 0)
        
        if idx_chunks > 0:
            status = "✓ Indexed"
        elif svc.name in previous_selection:
            status = "○ Selected"
        else:
            status = ""
        
        table.add_row(
            str(i),
            svc.name,
            str(svc.file_count),
            str(idx_chunks) if idx_chunks > 0 else "-",
            status
        )
    
    console.print(table)
    
    # Menu options
    console.print("\n[bold]Options:[/bold]")
    console.print("  [cyan]1-N[/cyan]  Toggle service selection")
    console.print("  [cyan]a[/cyan]    Select all")
    console.print("  [cyan]n[/cyan]    Select none")
    console.print("  [cyan]i[/cyan]    Index selected services")
    console.print("  [cyan]c[/cyan]    Clear index for selected services")
    console.print("  [cyan]q[/cyan]    Quit")
    
    selected = set(previous_selection)
    
    while True:
        console.print(f"\n[dim]Selected: {len(selected)} services[/dim]")
        choice = Prompt.ask("Choice", default="i" if selected else "a")
        
        if choice == 'q':
            break
        elif choice == 'a':
            selected = set(svc.name for svc in discovered)
            console.print(f"[green]Selected all {len(selected)} services[/green]")
        elif choice == 'n':
            selected = set()
            console.print("[yellow]Cleared selection[/yellow]")
        elif choice == 'i':
            if not selected:
                console.print("[yellow]No services selected[/yellow]")
                continue
            
            # Save selection
            service_mgr.save_service_selection(path, list(selected))
            
            # Index selected services
            console.print(f"\n[bold]Indexing {len(selected)} services...[/bold]\n")
            for svc in discovered:
                if svc.name in selected:
                    console.print(f"[cyan]Indexing {svc.name}...[/cyan]")
                    _do_index(svc.path, force=False, workers=8)
                    console.print()
            break
        elif choice == 'c':
            if not selected:
                console.print("[yellow]No services selected[/yellow]")
                continue
            
            if Confirm.ask(f"[yellow]Clear index for {len(selected)} services?[/yellow]", default=False):
                for svc in discovered:
                    if svc.name in selected:
                        count = service_mgr.clear_service_index(svc.path)
                        console.print(f"  [green]Cleared {svc.name}[/green]")
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(discovered):
                svc_name = discovered[idx].name
                if svc_name in selected:
                    selected.remove(svc_name)
                    console.print(f"[yellow]Deselected: {svc_name}[/yellow]")
                else:
                    selected.add(svc_name)
                    console.print(f"[green]Selected: {svc_name}[/green]")


@app.command()
def set_workspace(path: str = typer.Argument(..., help="Path to set as default workspace")):
    """
    Set a new default workspace path.
    
    This path will be remembered and used for all operations.
    """
    if not os.path.exists(path):
        console.print(f"[red]Path does not exist: {path}[/red]")
        return
    
    path = os.path.abspath(path)
    workspace.save_last_path(path)
    project_name = workspace.detect_project_name(path)
    
    console.print(f"[green]✓ Workspace set to: {project_name}[/green]")
    console.print(f"[dim]Path: {path}[/dim]")


@app.command()
def diff():
    """
    Show changes since last indexing.
    
    Compares current files against what's been indexed.
    """
    console.print("\n[bold cyan]📊 Changes Since Last Index[/bold cyan]\n")
    
    path = workspace.get_default_path()
    
    if not os.path.exists(path):
        console.print(f"[red]Workspace not found: {path}[/red]")
        return
    
    console.print(f"[dim]Scanning: {path}[/dim]\n")
    
    # Get current files
    from src.librarian.chunking import get_factory
    factory = get_factory()
    
    current_files = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['bin', 'obj', 'node_modules', '__pycache__', 'venv']]
        for file in files:
            filepath = os.path.join(root, file)
            if factory.get_chunker(filepath):
                current_files.append(filepath)
    
    # Get file cache to check what's indexed
    file_cache = FileHashCache()
    indexed_files = file_cache.get_indexed_files()

    new_files = []
    modified_files = []
    unchanged_files = []
    
    for filepath in current_files:
        if filepath not in indexed_files:
            new_files.append(filepath)
        elif file_cache.is_file_changed(filepath):
            modified_files.append(filepath)
        else:
            unchanged_files.append(filepath)
    
    # Display results
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Status", style="white")
    table.add_column("Count", style="green", justify="right")
    
    table.add_row("[green]✓ Unchanged[/green]", str(len(unchanged_files)))
    table.add_row("[yellow]~ Modified[/yellow]", str(len(modified_files)))
    table.add_row("[cyan]+ New[/cyan]", str(len(new_files)))
    
    console.print(table)
    
    # Show details if there are changes
    if modified_files:
        console.print(f"\n[bold yellow]Modified Files ({len(modified_files)}):[/bold yellow]")
        for f in modified_files[:10]:
            console.print(f"  [yellow]~[/yellow] {os.path.basename(f)}")
        if len(modified_files) > 10:
            console.print(f"  [dim]... and {len(modified_files) - 10} more[/dim]")
    
    if new_files:
        console.print(f"\n[bold cyan]New Files ({len(new_files)}):[/bold cyan]")
        for f in new_files[:10]:
            console.print(f"  [cyan]+[/cyan] {os.path.basename(f)}")
        if len(new_files) > 10:
            console.print(f"  [dim]... and {len(new_files) - 10} more[/dim]")
    
    total_changes = len(new_files) + len(modified_files)
    if total_changes > 0:
        console.print(f"\n[bold]Total changes: {total_changes} files[/bold]")
        console.print("[dim]Run 'index' to update the index[/dim]")
    else:
        console.print("\n[green]✓ Everything is up to date![/green]")


@app.command()
def info():
    """Shows workspace and system information."""
    console.print("\n[bold cyan]📋 Workspace Information[/bold cyan]\n")
    
    # Workspace info
    ws_info = workspace.get_workspace_info()
    default_path = ws_info['default_path']
    project_name = workspace.detect_project_name(default_path)
    
    console.print("[bold]Current Workspace:[/bold]")
    console.print(f"  Name: [cyan]{project_name}[/cyan]")
    console.print(f"  Path: [dim]{default_path}[/dim]")
    console.print(f"  Status: {'[green]✓ Exists[/green]' if ws_info['exists'] else '[red]✗ Not found[/red]'}")
    
    if 'file_count' in ws_info:
        console.print(f"  Files: [cyan]{ws_info['file_count']}[/cyan] supported files detected")
    
    if ws_info['last_used'] and ws_info['last_used'] != default_path:
        console.print(f"  Last used: [dim]{ws_info['last_used']}[/dim]")
    
    # Database info
    console.print("\n[bold]Database:[/bold]")
    try:
        db = LanceDBManager()
        chunk_count = db.table.count_rows()
        console.print(f"  Chunks: [green]{chunk_count:,}[/green]")
        
        # Get unique file count
        results = db.table.search().limit(10000).select(["filepath"]).to_list()
        unique_files = len(set(r.get('filepath', '') for r in results))
        console.print(f"  Files: [green]{unique_files:,}[/green] indexed")
    except Exception as e:
        console.print(f"  Status: [yellow]Not initialized[/yellow]")
    
    # Cache info
    console.print("\n[bold]Cache:[/bold]")
    try:
        embed_cache = EmbeddingCache()
        embed_stats = embed_cache.get_stats()
        console.print(f"  Embeddings: [cyan]{embed_stats['entries']:,}[/cyan] entries, [cyan]{embed_stats['size_mb']:.1f} MB[/cyan]")

        file_cache = FileHashCache()
        file_stats = file_cache.get_stats()
        console.print(f"  File hashes: [cyan]{file_stats['indexed_files']:,}[/cyan] files tracked")
    except Exception as e:
        console.print(f"  Status: [yellow]Error reading cache[/yellow]")

    # Environment
    console.print("\n[bold]Environment:[/bold]")
    console.print(f"  Docker: {'[green]Yes[/green]' if ws_info['is_docker'] else '[yellow]No[/yellow]'}")
    console.print(f"  Working dir: [dim]{os.getcwd()}[/dim]")

    console.print("\n[dim]💡 Tip: Run 'codebase-librarian index' without arguments to index the detected workspace[/dim]\n")


@app.command()
def menu():
    """
    Interactive menu for managing the Codebase Librarian.

    Provides an easy-to-use interface for all operations:
    - Index codebase
    - Search code
    - View status
    - Manage caches
    - Start file watcher
    """
    while True:
        console.clear()

        # Header
        console.print(Panel.fit(
            "[bold cyan]🔍 Codebase Librarian[/bold cyan]\n"
            "[dim]Semantic Code Search powered by Ollama + LanceDB[/dim]",
            border_style="cyan"
        ))
        console.print()

        # Get workspace info
        ws_info = workspace.get_workspace_info()
        default_path = ws_info['default_path']
        project_name = workspace.detect_project_name(default_path)

        # Show workspace status
        if ws_info['exists']:
            file_info = f"{ws_info.get('file_count', '?')} files" if 'file_count' in ws_info else ""
            console.print(f"  [bold]Workspace:[/bold] {project_name}")
            console.print(f"  [dim]Path: {default_path}[/dim]")
            if file_info:
                console.print(f"  [dim]{file_info} detected[/dim]")
        else:
            console.print(f"  [yellow]⚠ Workspace not found: {default_path}[/yellow]")

        # Get quick stats
        try:
            db = LanceDBManager()
            chunk_count = db.table.count_rows()
            console.print(f"  [bold]Database:[/bold] [green]{chunk_count:,} chunks indexed[/green]")
        except:
            console.print(f"  [bold]Database:[/bold] [yellow]Not initialized[/yellow]")

        console.print()

        # Menu options
        menu_options = [
            ("1", "📂 Index Codebase", "Scan and index current workspace"),
            ("2", "🔍 Search Code", "Search indexed codebase"),
            ("3", "📊 View Status", "Show indexing status by directory"),
            ("4", "🔄 View Changes", "Show files changed since last index"),
            ("5", "📦 Manage Services", "Select specific services to index"),
            ("6", "📁 Change Workspace", "Set a different workspace path"),
            ("7", "👁️  Start Watcher", "Watch directory for changes"),
            ("8", "ℹ️  System Info", "Show workspace and system details"),
            ("9", "🗑️  Clear Data", "Clear cache or database"),
            ("0", "⚡ Optimize DB", "Compact and optimize storage"),
            ("q", "🚪 Quit", "Exit the menu"),
        ]

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold cyan", width=3)
        table.add_column("Action", style="white", width=20)
        table.add_column("Description", style="dim")

        for key, action, desc in menu_options:
            table.add_row(f"[{key}]", action, desc)

        console.print(table)
        console.print()

        # Get choice
        choice = Prompt.ask(
            "[bold]Select option[/bold]",
            choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "q"],
            default="1"
        )

        console.print()

        if choice == "q":
            console.print("[cyan]Goodbye! 👋[/cyan]")
            break
        elif choice == "1":
            _menu_index()
        elif choice == "2":
            _menu_search()
        elif choice == "3":
            _menu_status()
        elif choice == "4":
            _menu_diff()
        elif choice == "5":
            _menu_services()
        elif choice == "6":
            _menu_set_workspace()
        elif choice == "7":
            _menu_watch()
        elif choice == "8":
            _menu_info()
        elif choice == "9":
            _menu_clear_data()
        elif choice == "0":
            _menu_optimize()

        # Pause before returning to menu
        if choice != "q":
            console.print()
            Prompt.ask("[dim]Press Enter to continue...[/dim]", default="")


def _menu_index():
    """Interactive indexing flow"""
    console.print("[bold]📂 Index Codebase[/bold]\n")
    
    # Get smart default path
    default_path = workspace.get_default_path()
    project_name = workspace.detect_project_name(default_path)
    
    console.print(f"[dim]Detected workspace: {project_name}[/dim]")
    
    # Ask if user wants to use detected path or choose different one
    use_default = Confirm.ask(
        f"Index {default_path}?",
        default=True
    )
    
    if use_default:
        path = default_path
    else:
        path = Prompt.ask("Enter directory path")
    
    if not os.path.exists(path):
        console.print(f"[red]Path does not exist: {path}[/red]")
        return
    
    # Save for next time
    workspace.save_last_path(path)
    
    force = Confirm.ask("Force re-index all files?", default=False)
    workers = IntPrompt.ask("Number of parallel workers", default=8)
    
    console.print()
    
    # Call the index function directly (inline to avoid typer issues)
    _do_index(path, force=force, workers=workers)


def _do_index(path: str, force: bool = False, workers: int = 8):
    """Core indexing logic extracted for menu use"""
    console.print(f"[bold green]Indexing {path}...[/bold green]")
    
    # Count total files
    console.print("[yellow]Scanning directory...[/yellow]")
    
    from src.librarian.chunking import get_factory
    factory = get_factory()
    
    all_files = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['bin', 'obj', 'node_modules']]
        for file in files:
            filepath = os.path.join(root, file)
            if factory.get_chunker(filepath):
                all_files.append(filepath)
    
    total_files = len(all_files)
    
    if total_files == 0:
        console.print("[yellow]No supported files found in the specified directory.[/yellow]")
        return
    
    # Initialize pipeline
    pipeline = IndexingPipeline(max_workers=workers)
    
    # Check for delta indexing
    files_to_index = all_files
    skipped_files = 0
    
    if not force:
        console.print("[cyan]Checking for changed files (delta indexing)...[/cyan]")
        files_to_index = pipeline.get_changed_files(all_files)
        skipped_files = total_files - len(files_to_index)
        
        if skipped_files > 0:
            console.print(f"[green]✓ Skipping {skipped_files:,} unchanged files[/green]")
    
    if len(files_to_index) == 0:
        console.print("[bold green]✓ All files already indexed and up-to-date![/bold green]")
        return
    
    est_rate = 10.0 if skipped_files > 0 else 5.0
    est_seconds = len(files_to_index) / est_rate
    
    console.print(f"[cyan]Files to index: {len(files_to_index):,} / {total_files:,}[/cyan]")
    console.print(f"[yellow]Estimated time: ~{format_time(est_seconds)}[/yellow]")
    console.print()
    
    files_indexed = 0
    total_chunks = 0
    start_time = time.time()
    errors = []
    
    with Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        "•",
        "[cyan]{task.completed}/{task.total}",
        "•",
        "[green]{task.fields[chunks]} chunks",
        "•",
        "[yellow]{task.fields[speed]}/s",
        "•",
        TimeRemainingColumn(),
        console=console
    ) as progress:
        
        task = progress.add_task(
            "[bold blue]Indexing...", 
            total=len(files_to_index),
            chunks=0,
            speed="0.0"
        )
        
        def process_file_wrapper(filepath: str) -> Tuple[int, int, str]:
            try:
                success, chunks, error = pipeline.process_file(filepath)
                return success, chunks, error or ""
            except Exception as e:
                return 0, 0, f"{filepath}: {str(e)}"
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {executor.submit(process_file_wrapper, fp): fp for fp in files_to_index}
            
            for future in as_completed(futures):
                success, chunks, error = future.result()
                files_indexed += success
                total_chunks += chunks
                if error:
                    errors.append(error)
                
                elapsed = time.time() - start_time
                speed = files_indexed / max(0.1, elapsed)
                
                progress.update(
                    task, 
                    advance=1,
                    chunks=total_chunks,
                    speed=f"{speed:.1f}"
                )
    
    elapsed_total = time.time() - start_time
    
    console.print()
    console.print("[bold green]✓ Indexing Complete![/bold green]")
    console.print()
    
    stats_table = Table(show_header=False, box=None)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", style="green")
    
    stats_table.add_row("Files processed", f"{files_indexed:,}")
    stats_table.add_row("Files skipped", f"{skipped_files:,}")
    stats_table.add_row("Chunks created", f"{total_chunks:,}")
    stats_table.add_row("Total time", format_time(elapsed_total))
    stats_table.add_row("Throughput", f"{files_indexed/max(0.1, elapsed_total):.1f} files/sec")
    
    console.print(stats_table)
    
    if errors:
        console.print(f"\n[yellow]⚠️  {len(errors)} files had errors[/yellow]")


def _menu_search():
    """Interactive search flow"""
    console.print("[bold]🔍 Search Code[/bold]\n")
    
    query = Prompt.ask("Search query")
    if not query.strip():
        console.print("[yellow]Empty query, cancelled.[/yellow]")
        return
    
    limit = IntPrompt.ask("Number of results", default=5)
    
    console.print()
    
    db = LanceDBManager()
    engine = EmbeddingEngine()
    
    start_time = time.time()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Embedding query...", total=None)
        query_vec = engine.embed_sync(query)
        
        progress.update(task, description="Searching vector DB...")
        results = db.search(query_vec, limit=limit)
    
    search_time = time.time() - start_time
    
    console.print(f"\n[bold]Results for '[cyan]{query}[/cyan]'[/bold] ({search_time:.2f}s)\n")
    
    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return
    
    for i, res in enumerate(results):
        distance = res.get('_distance', 0)
        filepath = res.get('filepath', 'unknown')
        filename = os.path.basename(filepath)
        
        arch_badge = " [yellow]⚡ARCH[/yellow]" if res.get('is_architecture_node') else ""
        console.print(f"[bold blue]#{i+1}[/bold blue] {res['context_header']}{arch_badge}")
        console.print(f"    [dim]{filename}[/dim] • [dim]distance: {distance:.4f}[/dim]")
        
        snippet = res['content'][:500] + "..." if len(res['content']) > 500 else res['content']
        syntax = Syntax(snippet, "csharp", theme="monokai", line_numbers=True)
        console.print(syntax)
        console.print()


def _menu_status():
    """Show indexing status"""
    console.print("[bold]📊 Indexing Status[/bold]\n")
    
    try:
        db = LanceDBManager()
        results = db.table.search().limit(100000).select(["filepath"]).to_list()
        
        if not results:
            console.print("[yellow]No files indexed.[/yellow]")
            return

        stats = {}
        total_chunks = len(results)
        
        for res in results:
            path = res.get('filepath', '')
            if not path:
                continue
            
            if path.startswith('/app/codebase/'):
                rel_path = path[len('/app/codebase/'):]
            else:
                rel_path = path
                
            parts = rel_path.split('/')
            if parts:
                top_dir = parts[0]
                stats[top_dir] = stats.get(top_dir, 0) + 1
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Directory", style="white")
        table.add_column("Chunks", style="green", justify="right")
        table.add_column("Coverage", style="yellow", justify="right")
        
        sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
        
        for dirname, count in sorted_stats[:20]:
            percentage = (count / total_chunks) * 100
            table.add_row(dirname, f"{count:,}", f"{percentage:.1f}%")
        
        console.print(table)
        console.print(f"\n[bold]Total Chunks:[/bold] [green]{total_chunks:,}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _menu_watch():
    """Start the file watcher"""
    console.print("[bold]👁️  Start Watcher[/bold]\n")
    
    # Get smart default path
    default_path = workspace.get_default_path()
    project_name = workspace.detect_project_name(default_path)
    
    console.print(f"[dim]Detected workspace: {project_name}[/dim]")
    
    # Ask if user wants to use detected path
    use_default = Confirm.ask(
        f"Watch {default_path}?",
        default=True
    )
    
    if use_default:
        path = default_path
    else:
        path = Prompt.ask("Enter directory path")
    
    if not os.path.exists(path):
        console.print(f"[red]Path does not exist: {path}[/red]")
        return
    
    # Save for next time
    workspace.save_last_path(path)
    
    console.print(f"\n[yellow]Starting watcher on {path}...[/yellow]")
    console.print("[dim]Press Ctrl+C to stop watching[/dim]\n")
    
    try:
        start_watching(path)
    except KeyboardInterrupt:
        console.print("\n[yellow]Watcher stopped.[/yellow]")


def _menu_cache_stats():
    """Show cache statistics"""
    console.print("[bold]📈 Cache Statistics[/bold]\n")
    
    try:
        embed_cache = EmbeddingCache()
        embed_stats = embed_cache.get_stats()
        
        console.print("[bold]Embedding Cache:[/bold]")
        console.print(f"  Entries: [green]{embed_stats['entries']:,}[/green]")
        console.print(f"  Size: [green]{embed_stats['size_mb']:.1f} MB[/green]")
        
        file_cache = FileHashCache()
        file_stats = file_cache.get_stats()
        
        console.print("\n[bold]File Hash Cache:[/bold]")
        console.print(f"  Indexed files: [green]{file_stats['indexed_files']:,}[/green]")
        console.print(f"  Total chunks: [green]{file_stats['total_chunks']:,}[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _menu_info():
    """Show workspace information"""
    console.print("[bold]ℹ️  Workspace Info[/bold]\n")
    
    # Workspace info
    ws_info = workspace.get_workspace_info()
    default_path = ws_info['default_path']
    project_name = workspace.detect_project_name(default_path)
    
    console.print("[bold]Current Workspace:[/bold]")
    console.print(f"  Name: [cyan]{project_name}[/cyan]")
    console.print(f"  Path: [dim]{default_path}[/dim]")
    console.print(f"  Status: {'[green]✓ Exists[/green]' if ws_info['exists'] else '[red]✗ Not found[/red]'}")
    
    if 'file_count' in ws_info:
        console.print(f"  Files: [cyan]{ws_info['file_count']}[/cyan] supported files detected")
    
    if ws_info['last_used'] and ws_info['last_used'] != default_path:
        console.print(f"  Last used: [dim]{ws_info['last_used']}[/dim]")
    
    # Database info
    console.print("\n[bold]Database:[/bold]")
    try:
        db = LanceDBManager()
        chunk_count = db.table.count_rows()
        console.print(f"  Chunks: [green]{chunk_count:,}[/green]")
        
        # Get sample to count unique files
        results = db.table.search().limit(10000).select(["filepath"]).to_list()
        unique_files = len(set(r.get('filepath', '') for r in results))
        console.print(f"  Files: [green]{unique_files:,}[/green] indexed")
    except Exception as e:
        console.print(f"  Status: [yellow]Not initialized[/yellow]")
    
    # Cache info
    console.print("\n[bold]Cache:[/bold]")
    try:
        embed_cache = EmbeddingCache()
        embed_stats = embed_cache.get_stats()
        console.print(f"  Embeddings: [cyan]{embed_stats['entries']:,}[/cyan] entries")
        
        file_cache = FileHashCache()
        file_stats = file_cache.get_stats()
        console.print(f"  File hashes: [cyan]{file_stats['indexed_files']:,}[/cyan] files")
    except Exception as e:
        console.print(f"  Status: [yellow]Error[/yellow]")
    
    console.print("\n[dim]💡 Auto-detected workspace will be used for all operations[/dim]")


def _menu_clear_cache():
    """Clear caches"""
    console.print("[bold]🗑️  Clear Cache[/bold]\n")
    
    if not Confirm.ask("[yellow]Clear all caches?[/yellow]", default=False):
        console.print("[dim]Cancelled[/dim]")
        return
    
    try:
        EmbeddingCache().clear()
        FileHashCache().clear()
        console.print("[green]✓ All caches cleared[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _menu_clear_database():
    """Clear the database"""
    console.print("[bold]💣 Clear Database[/bold]\n")
    
    if not Confirm.ask("[bold red]Delete ALL indexed data?[/bold red]", default=False):
        console.print("[dim]Cancelled[/dim]")
        return
    
    try:
        import shutil
        from src.librarian.consts import LANCEDB_PATH
        
        if os.path.exists(LANCEDB_PATH):
            shutil.rmtree(LANCEDB_PATH)
            console.print(f"[green]✓ Database deleted[/green]")
        else:
            console.print("[yellow]No database found[/yellow]")
        
        EmbeddingCache().clear()
        FileHashCache().clear()
        console.print("[green]✓ Caches cleared[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _menu_optimize():
    """Optimize the database"""
    console.print("[bold]⚡ Optimize Database[/bold]\n")
    
    try:
        db = LanceDBManager()
        db.optimize()
        console.print("[green]✓ Database optimized[/green]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def _menu_diff():
    """Show changes since last indexing"""
    console.print("[bold]🔄 View Changes[/bold]\n")
    
    path = workspace.get_default_path()
    
    if not os.path.exists(path):
        console.print(f"[red]Workspace not found: {path}[/red]")
        return
    
    console.print(f"[dim]Scanning: {path}[/dim]\n")
    
    # Get current files
    from src.librarian.chunking import get_factory
    factory = get_factory()
    
    current_files = []
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['bin', 'obj', 'node_modules', '__pycache__', 'venv']]
        for file in files:
            filepath = os.path.join(root, file)
            if factory.get_chunker(filepath):
                current_files.append(filepath)
    
    # Get file cache to check what's indexed
    file_cache = FileHashCache()
    indexed_files = file_cache.get_indexed_files()

    new_files = []
    modified_files = []
    unchanged_files = []
    
    for filepath in current_files:
        if filepath not in indexed_files:
            new_files.append(filepath)
        elif file_cache.is_file_changed(filepath):
            modified_files.append(filepath)
        else:
            unchanged_files.append(filepath)
    
    # Display results
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Status", style="white")
    table.add_column("Count", style="green", justify="right")
    
    table.add_row("[green]✓ Unchanged[/green]", str(len(unchanged_files)))
    table.add_row("[yellow]~ Modified[/yellow]", str(len(modified_files)))
    table.add_row("[cyan]+ New[/cyan]", str(len(new_files)))
    
    console.print(table)
    
    # Show details if there are changes
    if modified_files:
        console.print(f"\n[bold yellow]Modified Files:[/bold yellow]")
        for f in modified_files[:10]:
            console.print(f"  [yellow]~[/yellow] {os.path.basename(f)}")
        if len(modified_files) > 10:
            console.print(f"  [dim]... and {len(modified_files) - 10} more[/dim]")
    
    if new_files:
        console.print(f"\n[bold cyan]New Files:[/bold cyan]")
        for f in new_files[:10]:
            console.print(f"  [cyan]+[/cyan] {os.path.basename(f)}")
        if len(new_files) > 10:
            console.print(f"  [dim]... and {len(new_files) - 10} more[/dim]")
    
    total_changes = len(new_files) + len(modified_files)
    if total_changes > 0:
        console.print(f"\n[bold]Total changes: {total_changes} files[/bold]")
        console.print("[dim]Run 'Index Codebase' to update[/dim]")
    else:
        console.print("\n[green]✓ Everything is up to date![/green]")


def _menu_services():
    """Interactive service management"""
    console.print("[bold]📦 Manage Services[/bold]\n")
    
    path = workspace.get_default_path()
    
    if not os.path.exists(path):
        console.print(f"[red]Workspace not found: {path}[/red]")
        return
    
    console.print(f"[dim]Discovering services in: {path}[/dim]\n")
    console.print("[yellow]Scanning...[/yellow]")
    
    # Discover services
    discovered = service_mgr.discover_services(path)
    
    if not discovered:
        console.print("\n[yellow]No services found.[/yellow]")
        console.print("[dim]Looking for: package.json, pyproject.toml, *.csproj, pom.xml, etc.[/dim]")
        return
    
    # Get indexed services info
    indexed_info = service_mgr.get_indexed_services()
    
    # Get previous selection
    previous_selection = service_mgr.get_service_selection(path)
    
    # Show discovered services
    console.print(f"\n[bold]Found {len(discovered)} services:[/bold]\n")
    
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=3)
    table.add_column("Service", style="white")
    table.add_column("Files", style="cyan", justify="right")
    table.add_column("Indexed", style="green", justify="right")
    table.add_column("Status", style="yellow")
    
    for i, svc in enumerate(discovered, 1):
        idx_info = indexed_info.get(svc.name, {})
        idx_chunks = idx_info.get('chunks', 0)
        
        if idx_chunks > 0:
            status = "✓ Indexed"
        elif svc.name in previous_selection:
            status = "○ Selected"
        else:
            status = ""
        
        table.add_row(
            str(i),
            svc.name,
            str(svc.file_count) if svc.file_count <= 5000 else f"{svc.file_count}+",
            str(idx_chunks) if idx_chunks > 0 else "-",
            status
        )
    
    console.print(table)
    
    # Menu options
    console.print("\n[bold]Options:[/bold]")
    console.print("  [cyan]1-N[/cyan]  Toggle service selection")
    console.print("  [cyan]a[/cyan]    Select all")
    console.print("  [cyan]n[/cyan]    Select none")
    console.print("  [cyan]i[/cyan]    Index selected services")
    console.print("  [cyan]q[/cyan]    Back to main menu")
    
    selected = set(previous_selection)
    
    while True:
        console.print(f"\n[dim]Selected: {len(selected)} services[/dim]")
        choice = Prompt.ask("Choice", default="i" if selected else "a")
        
        if choice == 'q':
            break
        elif choice == 'a':
            selected = set(svc.name for svc in discovered)
            console.print(f"[green]✓ Selected all {len(selected)} services[/green]")
        elif choice == 'n':
            selected = set()
            console.print("[yellow]Cleared selection[/yellow]")
        elif choice == 'i':
            if not selected:
                console.print("[yellow]No services selected[/yellow]")
                continue
            
            # Save selection
            service_mgr.save_service_selection(path, list(selected))
            
            # Index selected services
            console.print(f"\n[bold]Indexing {len(selected)} services...[/bold]\n")
            for svc in discovered:
                if svc.name in selected:
                    console.print(f"[cyan]→ Indexing {svc.name}[/cyan]")
                    _do_index(svc.path, force=False, workers=8)
                    console.print()
            
            console.print("[green]✓ All selected services indexed![/green]")
            break
        elif choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(discovered):
                svc_name = discovered[idx].name
                if svc_name in selected:
                    selected.remove(svc_name)
                    console.print(f"[yellow]○ Deselected: {svc_name}[/yellow]")
                else:
                    selected.add(svc_name)
                    console.print(f"[green]✓ Selected: {svc_name}[/green]")


def _menu_set_workspace():
    """Change the default workspace"""
    console.print("[bold]📁 Change Workspace[/bold]\n")

    current = workspace.get_default_path()
    console.print(f"[dim]Current workspace: {current}[/dim]\n")

    new_path = Prompt.ask("Enter new workspace path", default=current)

    if not os.path.exists(new_path):
        console.print(f"[red]Path does not exist: {new_path}[/red]")
        return

    new_path = os.path.abspath(new_path)
    workspace.save_last_path(new_path)
    project_name = workspace.detect_project_name(new_path)

    console.print(f"\n[green]✓ Workspace changed to: {project_name}[/green]")
    console.print(f"[dim]Path: {new_path}[/dim]")


def _menu_clear_data():
    """Clear cache or database"""
    console.print("[bold]🗑️  Clear Data[/bold]\n")

    console.print("[bold]What would you like to clear?[/bold]")
    console.print("  [cyan]1[/cyan] Clear cache only (keeps indexed data)")
    console.print("  [cyan]2[/cyan] Clear database (deletes all indexed data)")
    console.print("  [cyan]3[/cyan] Clear both cache and database")
    console.print("  [cyan]q[/cyan] Cancel")

    choice = Prompt.ask("Choice", choices=["1", "2", "3", "q"], default="1")

    if choice == "q":
        console.print("[dim]Cancelled[/dim]")
        return

    console.print()
    
    if choice == "1":
        if Confirm.ask("[yellow]Clear all caches?[/yellow]", default=False):
            try:
                EmbeddingCache().clear()
                FileHashCache().clear()
                console.print("[green]✓ All caches cleared[/green]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

    elif choice == "2":
        if Confirm.ask("[bold red]Delete ALL indexed data?[/bold red]", default=False):
            try:
                import shutil
                from src.librarian.consts import LANCEDB_PATH

                if os.path.exists(LANCEDB_PATH):
                    shutil.rmtree(LANCEDB_PATH)
                    console.print("[green]✓ Database deleted[/green]")
                else:
                    console.print("[yellow]No database found[/yellow]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

    elif choice == "3":
        if Confirm.ask("[bold red]Delete ALL data (cache + database)?[/bold red]", default=False):
            try:
                import shutil
                from src.librarian.consts import LANCEDB_PATH

                if os.path.exists(LANCEDB_PATH):
                    shutil.rmtree(LANCEDB_PATH)
                    console.print("[green]✓ Database deleted[/green]")

                EmbeddingCache().clear()
                FileHashCache().clear()
                console.print("[green]✓ Caches cleared[/green]")
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")



if __name__ == "__main__":
    app()
