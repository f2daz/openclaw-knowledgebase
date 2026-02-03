"""FastAPI web application for OpenClaw Knowledgebase."""

import asyncio
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, Query, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from knowledgebase.client import KnowledgeBase
from knowledgebase.config import get_config
from knowledgebase.embeddings import test_ollama_connection, get_embedding
from knowledgebase.search import search, search_hybrid

# Job tracking (in-memory, resets on restart)
_jobs: dict[str, dict] = {}

# Paths
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="OpenClaw Knowledgebase",
        description="Self-hosted RAG with Ollama + Supabase",
        version="0.1.0",
    )
    
    # Mount static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    
    # Templates
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    
    # Add custom template functions
    def format_similarity(value: float) -> str:
        return f"{value:.0%}" if value else "N/A"
    
    templates.env.filters["similarity"] = format_similarity
    
    # --- Routes ---
    
    @app.get("/", response_class=HTMLResponse)
    async def dashboard(request: Request):
        """Dashboard with stats and quick search."""
        kb = KnowledgeBase()
        stats = kb.stats()
        sources = kb.list_sources(limit=10)
        
        # Check connections
        ollama_ok, ollama_msg = test_ollama_connection()
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "stats": stats,
            "sources": sources,
            "ollama_ok": ollama_ok,
            "ollama_msg": ollama_msg,
        })
    
    @app.get("/search", response_class=HTMLResponse)
    async def search_page(
        request: Request,
        q: str = Query(default=""),
        hybrid: bool = Query(default=False),
        limit: int = Query(default=10),
    ):
        """Search page with results."""
        results = []
        
        if q:
            if hybrid:
                results = search_hybrid(q, limit=limit)
            else:
                results = search(q, limit=limit)
        
        return templates.TemplateResponse("search.html", {
            "request": request,
            "query": q,
            "hybrid": hybrid,
            "limit": limit,
            "results": results,
        })
    
    @app.post("/search", response_class=HTMLResponse)
    async def search_post(
        request: Request,
        q: str = Form(...),
        hybrid: bool = Form(default=False),
        limit: int = Form(default=10),
    ):
        """Handle search form submission."""
        return RedirectResponse(
            url=f"/search?q={q}&hybrid={hybrid}&limit={limit}",
            status_code=303,
        )
    
    @app.get("/htmx/search-results", response_class=HTMLResponse)
    async def htmx_search_results(
        request: Request,
        q: str = Query(default=""),
        hybrid: bool = Query(default=False),
        limit: int = Query(default=10),
        threshold: float = Query(default=0.5),
    ):
        """HTMX endpoint for live search results."""
        results = []
        
        if q and len(q) >= 2:
            if hybrid:
                results = search_hybrid(q, limit=limit)
            else:
                results = search(q, limit=limit, threshold=threshold)
        
        return templates.TemplateResponse("partials/search_results.html", {
            "request": request,
            "results": results,
            "query": q,
        })
    
    @app.get("/sources", response_class=HTMLResponse)
    async def sources_page(request: Request):
        """Sources management page."""
        kb = KnowledgeBase()
        sources = kb.list_sources(limit=100)
        
        # Get chunk counts for each source
        for source in sources:
            resp = kb._request("GET", kb._chunks_table, params={
                "source_id": f"eq.{source.id}",
                "select": "id",
            })
            source.chunk_count = len(resp.json()) if resp.status_code == 200 else 0
        
        return templates.TemplateResponse("sources.html", {
            "request": request,
            "sources": sources,
        })
    
    @app.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request):
        """Settings page."""
        config = get_config()
        ollama_ok, ollama_msg = test_ollama_connection()
        
        return templates.TemplateResponse("settings.html", {
            "request": request,
            "config": config,
            "ollama_ok": ollama_ok,
            "ollama_msg": ollama_msg,
        })
    
    @app.get("/sources/{source_id}", response_class=HTMLResponse)
    async def source_detail_page(request: Request, source_id: str):
        """Source detail page with all chunks."""
        kb = KnowledgeBase()
        
        # Get source
        resp = kb._request("GET", kb._sources_table, params={"id": f"eq.{source_id}"})
        if resp.status_code != 200 or not resp.json():
            raise HTTPException(status_code=404, detail="Source not found")
        
        source_data = resp.json()[0]
        
        # Get chunks for this source
        chunks_resp = kb._request("GET", kb._chunks_table, params={
            "source_id": f"eq.{source_id}",
            "select": "id,chunk_index,content,metadata,embedding",
            "order": "chunk_index.asc",
            "limit": "100",
        })
        
        chunks = []
        if chunks_resp.status_code == 200:
            for c in chunks_resp.json():
                chunks.append({
                    "id": c["id"],
                    "chunk_index": c.get("chunk_index", 0),
                    "content": c["content"],
                    "has_embedding": c.get("embedding") is not None,
                    "char_count": len(c["content"]),
                })
        
        return templates.TemplateResponse("source_detail.html", {
            "request": request,
            "source": source_data,
            "chunks": chunks,
            "chunk_count": len(chunks),
        })
    
    # --- API Endpoints ---
    
    @app.get("/api/stats")
    async def api_stats():
        """Get knowledge base statistics."""
        kb = KnowledgeBase()
        return kb.stats()
    
    @app.get("/api/search")
    async def api_search(
        q: str = Query(...),
        hybrid: bool = Query(default=False),
        limit: int = Query(default=10),
        threshold: float = Query(default=0.5),
    ):
        """Search API endpoint."""
        if hybrid:
            return search_hybrid(q, limit=limit)
        return search(q, limit=limit, threshold=threshold)
    
    @app.get("/api/sources")
    async def api_sources(limit: int = Query(default=100)):
        """List sources."""
        kb = KnowledgeBase()
        sources = kb.list_sources(limit=limit)
        return [
            {
                "id": s.id,
                "url": s.url,
                "title": s.title,
                "source_type": s.source_type,
            }
            for s in sources
        ]
    
    @app.get("/api/health")
    async def api_health():
        """Health check endpoint."""
        ollama_ok, ollama_msg = test_ollama_connection()
        return {
            "status": "ok" if ollama_ok else "degraded",
            "ollama": {"ok": ollama_ok, "message": ollama_msg},
        }
    
    @app.put("/api/settings")
    async def api_save_settings(request: Request):
        """Save runtime settings (session-only, not persisted to .env)."""
        import os
        data = await request.json()
        
        # Update environment variables for this process
        if "embedding_model" in data:
            os.environ["EMBEDDING_MODEL"] = data["embedding_model"]
        if "chunk_size" in data:
            os.environ["CHUNK_SIZE"] = str(data["chunk_size"])
        if "chunk_overlap" in data:
            os.environ["CHUNK_OVERLAP"] = str(data["chunk_overlap"])
        if "debug" in data:
            os.environ["DEBUG"] = "1" if data["debug"] else "0"
        
        # Reload config
        from knowledgebase.config import reload_config
        reload_config()
        
        return {"status": "ok", "message": "Settings saved for this session"}
    
    @app.get("/api/export/search")
    async def api_export_search(
        q: str = Query(...),
        format: str = Query(default="json"),
        hybrid: bool = Query(default=False),
        limit: int = Query(default=50),
        threshold: float = Query(default=0.5),
    ):
        """Export search results in various formats."""
        from fastapi.responses import PlainTextResponse
        
        if hybrid:
            results = search_hybrid(q, limit=limit)
        else:
            results = search(q, limit=limit, threshold=threshold)
        
        if format == "json":
            return results
        
        elif format == "markdown":
            lines = [f"# Search Results: {q}", "", f"Found {len(results)} results", ""]
            for i, r in enumerate(results, 1):
                sim = r.get("similarity", 0)
                title = r.get("title") or "Untitled"
                lines.append(f"## {i}. [{sim:.0%}] {title}")
                if r.get("url"):
                    lines.append(f"URL: {r['url']}")
                lines.append("")
                lines.append(r.get("content", "")[:500])
                lines.append("")
                lines.append("---")
                lines.append("")
            
            return PlainTextResponse(
                "\n".join(lines),
                media_type="text/markdown",
                headers={"Content-Disposition": f"attachment; filename=search-{q[:20]}.md"}
            )
        
        elif format == "csv":
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["rank", "similarity", "title", "url", "content_preview"])
            
            for i, r in enumerate(results, 1):
                writer.writerow([
                    i,
                    f"{r.get('similarity', 0):.2f}",
                    r.get("title") or "",
                    r.get("url") or "",
                    r.get("content", "")[:200].replace("\n", " ")
                ])
            
            return PlainTextResponse(
                output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": f"attachment; filename=search-{q[:20]}.csv"}
            )
        
        return {"error": "Unknown format. Use: json, markdown, csv"}
    
    # --- Ingestion Endpoints ---
    
    @app.post("/api/crawl")
    async def api_crawl(
        background_tasks: BackgroundTasks,
        url: str = Form(...),
        max_depth: int = Form(default=2),
        title: str = Form(default=None),
        tags: str = Form(default=""),
    ):
        """Start crawling a URL."""
        from knowledgebase.ingest.crawler import check_crawler_deps
        
        # Check dependencies
        ok, msg = check_crawler_deps()
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        
        # Parse tags
        tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()] if tags else []
        
        # Create job
        job_id = str(uuid.uuid4())[:8]
        _jobs[job_id] = {
            "id": job_id,
            "type": "crawl",
            "url": url,
            "status": "pending",
            "progress": 0,
            "total": 0,
            "current": "",
            "started_at": datetime.now().isoformat(),
            "error": None,
        }
        
        # Start background task
        background_tasks.add_task(run_crawl_job, job_id, url, max_depth, title, tag_list)
        
        return {"job_id": job_id, "status": "started"}
    
    @app.post("/api/upload")
    async def api_upload(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        title: str = Form(default=None),
        tags: str = Form(default=""),
    ):
        """Upload and process a document."""
        # Save to temp file
        suffix = Path(file.filename).suffix if file.filename else ".txt"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        
        # Parse tags
        tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()] if tags else []
        
        # Create job
        job_id = str(uuid.uuid4())[:8]
        _jobs[job_id] = {
            "id": job_id,
            "type": "upload",
            "filename": file.filename,
            "status": "pending",
            "progress": 0,
            "total": 1,
            "started_at": datetime.now().isoformat(),
            "error": None,
        }
        
        # Start background task
        background_tasks.add_task(run_upload_job, job_id, tmp_path, title or file.filename, tag_list)
        
        return {"job_id": job_id, "status": "started"}
    
    @app.get("/api/jobs/{job_id}")
    async def api_job_status(job_id: str):
        """Get job status."""
        if job_id not in _jobs:
            raise HTTPException(status_code=404, detail="Job not found")
        return _jobs[job_id]
    
    @app.get("/api/jobs")
    async def api_jobs():
        """List all jobs."""
        return list(_jobs.values())
    
    @app.post("/api/embed")
    async def api_embed_pending(background_tasks: BackgroundTasks):
        """Embed all pending chunks."""
        job_id = str(uuid.uuid4())[:8]
        _jobs[job_id] = {
            "id": job_id,
            "type": "embed",
            "status": "pending",
            "progress": 0,
            "total": 0,
            "started_at": datetime.now().isoformat(),
            "error": None,
        }
        
        background_tasks.add_task(run_embed_job, job_id)
        return {"job_id": job_id, "status": "started"}
    
    @app.delete("/api/sources/{source_id}")
    async def api_delete_source(source_id: str):
        """Delete a source and its chunks."""
        kb = KnowledgeBase()
        # Delete chunks first
        kb._request("DELETE", kb._chunks_table, params={"source_id": f"eq.{source_id}"})
        # Delete source
        resp = kb._request("DELETE", kb._sources_table, params={"id": f"eq.{source_id}"})
        if resp.status_code in (200, 204):
            return {"status": "deleted", "source_id": source_id}
        raise HTTPException(status_code=500, detail="Failed to delete source")
    
    @app.post("/api/sources/{source_id}/refresh")
    async def api_refresh_source(source_id: str, background_tasks: BackgroundTasks):
        """Refresh a source by re-crawling/re-processing."""
        kb = KnowledgeBase()
        
        # Get source info
        resp = kb._request("GET", kb._sources_table, params={"id": f"eq.{source_id}"})
        if resp.status_code != 200 or not resp.json():
            raise HTTPException(status_code=404, detail="Source not found")
        
        source_data = resp.json()[0]
        url = source_data.get("url", "")
        title = source_data.get("title")
        source_type = source_data.get("source_type", "web")
        
        # Only web sources can be refreshed
        if source_type != "web" or not url.startswith("http"):
            raise HTTPException(status_code=400, detail="Only web sources can be refreshed")
        
        # Create job
        job_id = str(uuid.uuid4())[:8]
        _jobs[job_id] = {
            "id": job_id,
            "type": "refresh",
            "source_id": source_id,
            "url": url,
            "status": "pending",
            "progress": 0,
            "total": 0,
            "current": "",
            "started_at": datetime.now().isoformat(),
            "error": None,
        }
        
        # Start background task
        background_tasks.add_task(run_refresh_job, job_id, source_id, url, title)
        
        return {"job_id": job_id, "status": "started"}
    
    # --- Tags API ---
    
    @app.get("/api/sources/{source_id}/tags")
    async def api_get_tags(source_id: str):
        """Get tags for a source."""
        kb = KnowledgeBase()
        resp = kb._request("GET", kb._sources_table, params={
            "id": f"eq.{source_id}",
            "select": "metadata"
        })
        if resp.status_code != 200 or not resp.json():
            raise HTTPException(status_code=404, detail="Source not found")
        
        metadata = resp.json()[0].get("metadata", {}) or {}
        return {"tags": metadata.get("tags", [])}
    
    @app.put("/api/sources/{source_id}/tags")
    async def api_set_tags(source_id: str, tags: list[str] = Form(...)):
        """Set tags for a source (replaces existing)."""
        kb = KnowledgeBase()
        
        # Get current metadata
        resp = kb._request("GET", kb._sources_table, params={
            "id": f"eq.{source_id}",
            "select": "metadata"
        })
        if resp.status_code != 200 or not resp.json():
            raise HTTPException(status_code=404, detail="Source not found")
        
        metadata = resp.json()[0].get("metadata", {}) or {}
        metadata["tags"] = tags
        
        # Update
        kb._request("PATCH", kb._sources_table, 
            data={"metadata": metadata},
            params={"id": f"eq.{source_id}"}
        )
        
        return {"tags": tags}
    
    @app.post("/api/sources/{source_id}/tags")
    async def api_add_tag(source_id: str, tag: str = Form(...)):
        """Add a single tag to a source."""
        kb = KnowledgeBase()
        
        # Get current metadata
        resp = kb._request("GET", kb._sources_table, params={
            "id": f"eq.{source_id}",
            "select": "metadata"
        })
        if resp.status_code != 200 or not resp.json():
            raise HTTPException(status_code=404, detail="Source not found")
        
        metadata = resp.json()[0].get("metadata", {}) or {}
        tags = metadata.get("tags", [])
        
        if tag not in tags:
            tags.append(tag)
            metadata["tags"] = tags
            
            kb._request("PATCH", kb._sources_table,
                data={"metadata": metadata},
                params={"id": f"eq.{source_id}"}
            )
        
        return {"tags": tags}
    
    @app.delete("/api/sources/{source_id}/tags/{tag}")
    async def api_remove_tag(source_id: str, tag: str):
        """Remove a tag from a source."""
        kb = KnowledgeBase()
        
        # Get current metadata
        resp = kb._request("GET", kb._sources_table, params={
            "id": f"eq.{source_id}",
            "select": "metadata"
        })
        if resp.status_code != 200 or not resp.json():
            raise HTTPException(status_code=404, detail="Source not found")
        
        metadata = resp.json()[0].get("metadata", {}) or {}
        tags = metadata.get("tags", [])
        
        if tag in tags:
            tags.remove(tag)
            metadata["tags"] = tags
            
            kb._request("PATCH", kb._sources_table,
                data={"metadata": metadata},
                params={"id": f"eq.{source_id}"}
            )
        
        return {"tags": tags}
    
    @app.get("/api/tags")
    async def api_list_all_tags():
        """List all unique tags across all sources."""
        kb = KnowledgeBase()
        sources = kb.list_sources(limit=500)
        
        all_tags = set()
        for s in sources:
            if s.metadata and isinstance(s.metadata, dict):
                tags = s.metadata.get("tags", [])
                if isinstance(tags, list):
                    all_tags.update(tags)
        
        return {"tags": sorted(all_tags)}
    
    # --- HTMX Partials ---
    
    @app.get("/htmx/add-modal", response_class=HTMLResponse)
    async def htmx_add_modal(request: Request):
        """Return the Add Source modal."""
        return templates.TemplateResponse("partials/add_modal.html", {
            "request": request,
        })
    
    @app.get("/htmx/job-progress/{job_id}", response_class=HTMLResponse)
    async def htmx_job_progress(request: Request, job_id: str):
        """Return job progress HTML."""
        job = _jobs.get(job_id, {})
        return templates.TemplateResponse("partials/job_progress.html", {
            "request": request,
            "job": job,
        })
    
    @app.get("/htmx/sources-list", response_class=HTMLResponse)
    async def htmx_sources_list(request: Request):
        """Return sources list for refresh."""
        kb = KnowledgeBase()
        sources = kb.list_sources(limit=100)
        return templates.TemplateResponse("partials/sources_list.html", {
            "request": request,
            "sources": sources,
        })
    
    return app


# --- Background Jobs ---

def run_crawl_job(job_id: str, url: str, max_depth: int, title: str | None, tags: list[str] | None = None):
    """Background task to crawl a URL."""
    from knowledgebase.ingest.crawler import crawl_website, crawl_url
    from knowledgebase.ingest.chunker import chunk_markdown
    
    job = _jobs[job_id]
    job["status"] = "running"
    tags = tags or []
    
    try:
        kb = KnowledgeBase()
        config = get_config()
        
        # Check if URL already exists
        existing = kb.get_source(url)
        if existing:
            job["status"] = "error"
            job["error"] = f"URL already exists (source_id: {existing.id})"
            return
        
        total_chunks = 0
        pages_crawled = 0
        
        def progress_callback(crawled: int, total: int, current_url: str):
            nonlocal pages_crawled
            pages_crawled = crawled
            job["progress"] = crawled
            job["total"] = total
            job["current"] = current_url
        
        if max_depth == 0:
            # Single page
            page = crawl_url(url)
            if page:
                pages = [page]
            else:
                pages = []
        else:
            # Recursive crawl
            pages = list(crawl_website(
                url,
                max_depth=max_depth,
                max_pages=50,
                progress_callback=progress_callback,
            ))
        
        if not pages:
            job["status"] = "error"
            job["error"] = "No pages crawled (check URL)"
            return
        
        # Create source
        source = kb.add_source(
            url=url,
            title=title or pages[0].title or url,
            source_type="web",
            metadata={"pages_crawled": len(pages), "max_depth": max_depth, "tags": tags},
        )
        
        if not source:
            job["status"] = "error"
            job["error"] = "Failed to create source"
            return
        
        # Chunk and add content
        for page in pages:
            chunks = chunk_markdown(page.content)
            
            for chunk in chunks:
                kb.add_chunk(
                    source_id=source.id,
                    content=chunk.content,
                    chunk_index=chunk.chunk_number,
                    metadata={"url": page.url, "title": page.title},
                )
                total_chunks += 1
        
        # Generate embeddings
        job["current"] = "Generating embeddings..."
        chunks_to_embed = kb.get_chunks_without_embeddings(limit=500)
        embedded = 0
        
        for chunk in chunks_to_embed:
            # Compare as strings to handle UUID vs int
            if str(chunk.source_id) == str(source.id):
                embedding = get_embedding(chunk.content)
                if embedding:
                    kb.update_chunk_embedding(chunk.id, embedding)
                    embedded += 1
        
        job["status"] = "completed"
        job["result"] = {
            "source_id": source.id,
            "pages_crawled": len(pages),
            "chunks_created": total_chunks,
            "embeddings_generated": embedded,
        }
        
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)


def run_upload_job(job_id: str, file_path: str, title: str, tags: list[str] | None = None):
    """Background task to process an uploaded document."""
    from knowledgebase.ingest.docling_parser import parse_document
    from knowledgebase.ingest.chunker import chunk_markdown
    
    job = _jobs[job_id]
    job["status"] = "running"
    tags = tags or []
    
    try:
        kb = KnowledgeBase()
        
        # Parse document
        job["current"] = "Parsing document..."
        doc = parse_document(file_path)
        
        if not doc:
            job["status"] = "error"
            job["error"] = "Failed to parse document"
            return
        
        # Create source
        source = kb.add_source(
            url=f"file://{file_path}",
            title=title or doc.title,
            source_type="document",
            metadata={"format": doc.format, "original_path": file_path, "tags": tags},
        )
        
        if not source:
            job["status"] = "error"
            job["error"] = "Failed to create source"
            return
        
        # Chunk and add
        job["current"] = "Chunking content..."
        chunks = chunk_markdown(doc.content)
        
        for chunk in chunks:
            kb.add_chunk(
                source_id=source.id,
                content=chunk.content,
                chunk_index=chunk.chunk_number,
                metadata={"title": doc.title, "path": file_path},
            )
        
        # Generate embeddings
        job["current"] = "Generating embeddings..."
        chunks_to_embed = kb.get_chunks_without_embeddings(limit=500)
        embedded = 0
        
        for chunk in chunks_to_embed:
            if str(chunk.source_id) == str(source.id):
                embedding = get_embedding(chunk.content)
                if embedding:
                    kb.update_chunk_embedding(chunk.id, embedding)
                    embedded += 1
        
        job["status"] = "completed"
        job["result"] = {
            "source_id": source.id,
            "chunks_created": len(chunks),
            "embeddings_generated": embedded,
        }
        
        # Cleanup temp file
        try:
            os.unlink(file_path)
        except:
            pass
        
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)


def run_refresh_job(job_id: str, source_id: str, url: str, title: str | None):
    """Background task to refresh a source by re-crawling."""
    from knowledgebase.ingest.crawler import crawl_url
    from knowledgebase.ingest.chunker import chunk_markdown
    
    job = _jobs[job_id]
    job["status"] = "running"
    
    try:
        kb = KnowledgeBase()
        
        # Delete old chunks
        job["current"] = "Deleting old chunks..."
        kb._request("DELETE", kb._chunks_table, params={"source_id": f"eq.{source_id}"})
        
        # Re-crawl
        job["current"] = f"Crawling {url}..."
        page = crawl_url(url)
        
        if not page:
            job["status"] = "error"
            job["error"] = "Failed to crawl URL"
            return
        
        # Update source metadata
        kb._request(
            "PATCH",
            kb._sources_table,
            data={
                "title": title or page.title,
                "metadata": {"refreshed_at": datetime.now().isoformat()},
            },
            params={"id": f"eq.{source_id}"},
        )
        
        # Chunk and add content
        job["current"] = "Creating chunks..."
        chunks = chunk_markdown(page.content)
        total_chunks = 0
        
        for chunk in chunks:
            kb.add_chunk(
                source_id=source_id,
                content=chunk.content,
                chunk_index=chunk.chunk_number,
                metadata={"url": page.url, "title": page.title},
            )
            total_chunks += 1
        
        # Generate embeddings
        job["current"] = "Generating embeddings..."
        chunks_to_embed = kb.get_chunks_without_embeddings(limit=500)
        embedded = 0
        
        for chunk in chunks_to_embed:
            if str(chunk.source_id) == str(source_id):
                embedding = get_embedding(chunk.content)
                if embedding:
                    kb.update_chunk_embedding(chunk.id, embedding)
                    embedded += 1
        
        job["status"] = "completed"
        job["result"] = {
            "source_id": source_id,
            "chunks_created": total_chunks,
            "embeddings_generated": embedded,
        }
        
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)


def run_embed_job(job_id: str):
    """Background task to embed all pending chunks."""
    job = _jobs[job_id]
    job["status"] = "running"
    
    try:
        kb = KnowledgeBase()
        
        # Get pending chunks
        chunks = kb.get_chunks_without_embeddings(limit=500)
        job["total"] = len(chunks)
        job["progress"] = 0
        
        if not chunks:
            job["status"] = "completed"
            job["result"] = {"embedded": 0, "message": "No pending chunks"}
            return
        
        embedded = 0
        for i, chunk in enumerate(chunks):
            job["progress"] = i + 1
            job["current"] = f"Chunk {i + 1}/{len(chunks)}"
            
            embedding = get_embedding(chunk.content)
            if embedding:
                kb.update_chunk_embedding(chunk.id, embedding)
                embedded += 1
        
        job["status"] = "completed"
        job["result"] = {"embedded": embedded, "total": len(chunks)}
        
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)


# Create app instance for uvicorn
app = create_app()
