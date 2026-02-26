"""Command-line interface for OpenClaw Knowledgebase."""

import sys
import time
import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from knowledgebase.config import get_config
from knowledgebase.client import KnowledgeBase
from knowledgebase.embeddings import get_embedding, test_ollama_connection
from knowledgebase.embeddings_optimized import embed_chunks_parallel
from knowledgebase.search import search, search_hybrid, format_results

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """OpenClaw Knowledgebase - Self-hosted RAG with Ollama + Supabase."""
    pass


@main.command()
def status():
    """Check connection status and show statistics."""
    config = get_config()
    
    console.print("\n[bold]OpenClaw Knowledgebase Status[/bold]\n")
    
    # Check Ollama
    ok, msg = test_ollama_connection()
    if ok:
        console.print(f"  ✅ Ollama: {msg}")
    else:
        console.print(f"  ❌ Ollama: {msg}")
    
    # Check Supabase
    try:
        kb = KnowledgeBase()
        stats = kb.stats()
        console.print(f"  ✅ Supabase: Connected")
        console.print()
        
        table = Table(title="Knowledge Base Stats")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green", justify="right")
        
        table.add_row("Sources", str(stats.get("total_sources", 0)))
        table.add_row("Total Chunks", str(stats.get("total_chunks", 0)))
        table.add_row("With Embeddings", str(stats.get("chunks_with_embeddings", 0)))
        table.add_row("Without Embeddings", str(stats.get("chunks_without_embeddings", 0)))
        
        console.print(table)
    except Exception as e:
        console.print(f"  ❌ Supabase: {e}")
    
    console.print()


@main.command()
@click.argument("query")
@click.option("-n", "--limit", default=5, help="Number of results")
@click.option("-t", "--threshold", default=0.5, help="Similarity threshold")
@click.option("--hybrid", is_flag=True, help="Use hybrid search")
def find(query: str, limit: int, threshold: float, hybrid: bool):
    """Search the knowledge base."""
    console.print(f"\n🔍 Searching: [cyan]{query}[/cyan]\n")
    
    if hybrid:
        results = search_hybrid(query, limit=limit)
    else:
        results = search(query, limit=limit, threshold=threshold)
    
    if not results:
        console.print("[yellow]No results found.[/yellow]")
        return
    
    for i, r in enumerate(results, 1):
        sim = r.get("similarity", 0)
        title = r.get("title") or "Untitled"
        url = r.get("url", "")
        content = r.get("content", "")[:300]
        
        console.print(f"[bold]{i}.[/bold] [{sim:.2f}] [cyan]{title}[/cyan]")
        console.print(f"   [dim]{url}[/dim]")
        console.print(f"   {content}...")
        console.print()


@main.command()
@click.option("--batch-size", default=50, help="Chunks per batch")
@click.option("--workers", "-w", default=4, help="Parallel workers (default: 4)")
@click.option("--sequential", is_flag=True, help="Use sequential processing (slower)")
def embed(batch_size: int, workers: int, sequential: bool):
    """Generate embeddings for chunks that don't have them."""
    config = get_config()
    kb = KnowledgeBase()
    
    # Check Ollama first
    ok, msg = test_ollama_connection()
    if not ok:
        console.print(f"[red]❌ {msg}[/red]")
        sys.exit(1)
    
    total_without = kb.count_chunks(with_embeddings=False)
    if total_without == 0:
        console.print("[green]✅ All chunks have embeddings![/green]")
        return
    
    mode = "sequential" if sequential else f"parallel ({workers} workers)"
    console.print(f"\n🧠 Generating embeddings for {total_without} chunks... [{mode}]\n")
    
    total_done = 0
    total_errors = 0
    start_time = time.time()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Embedding...", total=total_without)
        
        while True:
            chunks = kb.get_chunks_without_embeddings(limit=batch_size)
            if not chunks:
                break
            
            if sequential:
                # Original sequential processing
                for chunk in chunks:
                    embedding = get_embedding(chunk.content)
                    if embedding:
                        kb.update_chunk_embedding(chunk.id, embedding)
                        total_done += 1
                    else:
                        total_errors += 1
                    progress.update(task, advance=1)
            else:
                # Parallel processing
                chunk_dicts = [{'id': c.id, 'content': c.content} for c in chunks]
                
                def update_callback(chunk_id, embedding):
                    kb.update_chunk_embedding(chunk_id, embedding)
                
                def progress_callback(done, total, text):
                    progress.update(task, advance=1)
                    elapsed = time.time() - start_time
                    rate = (total_done + done) / elapsed if elapsed > 0 else 0
                    progress.update(task, description=f"Embedding... ({rate:.1f}/s)")
                
                success, errors = embed_chunks_parallel(
                    chunk_dicts,
                    update_callback,
                    max_workers=workers,
                    on_progress=progress_callback,
                )
                total_done += success
                total_errors += errors
            
            # Update rate display
            elapsed = time.time() - start_time
            rate = total_done / elapsed if elapsed > 0 else 0
            progress.update(task, description=f"Embedding... ({rate:.1f}/s)")
    
    elapsed = time.time() - start_time
    console.print(f"\n[green]✅ Done![/green] {total_done} embeddings in {elapsed:.0f}s ({total_done/elapsed:.1f}/s)")
    if total_errors:
        console.print(f"[yellow]⚠️ {total_errors} chunks failed[/yellow]")


@main.command()
def sources():
    """List all sources in the knowledge base."""
    kb = KnowledgeBase()
    sources = kb.list_sources()
    
    if not sources:
        console.print("[yellow]No sources found.[/yellow]")
        return
    
    table = Table(title="Knowledge Base Sources")
    table.add_column("ID", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Title")
    table.add_column("URL", style="dim", max_width=50)
    
    for s in sources:
        table.add_row(
            str(s.id),
            s.source_type,
            s.title or "-",
            s.url[:50] + "..." if len(s.url) > 50 else s.url,
        )
    
    console.print(table)


@main.command("watch")
@click.option("--inbox", default=None, help="Inbox folder path (default: ~/clawd/kb-inbox)")
@click.option("--once", is_flag=True, help="Index once and exit (no watching)")
def watch_inbox(inbox: str, once: bool):
    """Watch a folder for new documents and auto-index them."""
    try:
        from knowledgebase.auto_index import watch_inbox as do_watch, index_inbox_once, DEFAULT_INBOX
    except ImportError as e:
        console.print(f"[red]❌ Auto-index dependencies missing: {e}[/red]")
        console.print("Install with: [cyan]uv pip install watchdog[/cyan]")
        sys.exit(1)
    
    from pathlib import Path
    inbox_path = Path(inbox) if inbox else DEFAULT_INBOX
    
    def on_indexed(path, chunks):
        console.print(f"[green]✅[/green] Indexed: [cyan]{path.name}[/cyan] ({chunks} chunks)")
    
    def on_error(path, e):
        console.print(f"[red]❌[/red] Error: [yellow]{path.name}[/yellow]: {e}")
    
    if once:
        console.print(f"\n📂 Indexing files in [cyan]{inbox_path}[/cyan]...\n")
        indexed, failed = index_inbox_once(inbox_path, on_indexed, on_error)
        console.print(f"\n[green]✅ Done![/green] {indexed} indexed, {failed} failed")
    else:
        console.print(f"\n👀 Watching [cyan]{inbox_path}[/cyan] for new documents...")
        console.print("   Supported: PDF, DOCX, TXT, MD, HTML, EPUB")
        console.print("   Press Ctrl+C to stop\n")
        
        observer = do_watch(inbox_path, on_indexed, on_error)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            observer.join()
            console.print("\n[yellow]Stopped.[/yellow]")


@main.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=8080, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload (dev)")
def serve(host: str, port: int, reload: bool):
    """Start the web UI server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]❌ Web dependencies not installed.[/red]")
        console.print("Install with: [cyan]pip install openclaw-knowledgebase[web][/cyan]")
        sys.exit(1)
    
    console.print(f"\n🚀 Starting web UI at [cyan]http://{host}:{port}[/cyan]\n")
    
    uvicorn.run(
        "knowledgebase.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


if __name__ == "__main__":
    main()
