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
def embed(batch_size: int):
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
    
    console.print(f"\n🧠 Generating embeddings for {total_without} chunks...\n")
    
    total_done = 0
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
            
            for chunk in chunks:
                embedding = get_embedding(chunk.content)
                if embedding:
                    kb.update_chunk_embedding(chunk.id, embedding)
                    total_done += 1
                
                progress.update(task, advance=1)
                
                # Show rate
                elapsed = time.time() - start_time
                rate = total_done / elapsed if elapsed > 0 else 0
                progress.update(task, description=f"Embedding... ({rate:.1f}/s)")
    
    elapsed = time.time() - start_time
    console.print(f"\n[green]✅ Done![/green] {total_done} embeddings in {elapsed:.0f}s")


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


if __name__ == "__main__":
    main()
