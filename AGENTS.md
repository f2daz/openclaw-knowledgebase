# AGENTS.md - OpenClaw Knowledgebase

## Project Overview
RAG-based knowledge base for OpenClaw agents. Crawls websites, processes documents, creates embeddings, enables semantic search.

## Tech Stack
- **Backend:** Python 3.11+, FastAPI, Supabase (pgvector)
- **Frontend:** Jinja2 Templates, HTMX, Alpine.js, Tailwind CSS
- **Embeddings:** OpenAI text-embedding-3-small (or Ollama local)
- **Document Parsing:** Docling (PDF, Word, Excel), BeautifulSoup (HTML)

## IMPORTANT
Prefer retrieval-led reasoning over pre-training-led reasoning. Read the actual source files before making changes.

## Code Index
[KB Code Index]|root:./src/knowledgebase
|core:{cli.py,client.py,config.py,embeddings.py,search.py}
|ingest:{chunker.py,crawler.py,docling_parser.py}
|web:{app.py}
|web/templates:{base.html,dashboard.html,search.html,settings.html,source_detail.html,sources.html}
|web/templates/partials:{add_modal.html,job_toast.html,search_results.html}

## Key Files

### Backend
- `client.py` - Supabase client, CRUD operations for sources/chunks
- `crawler.py` - Web crawler with domain normalization, depth control
- `chunker.py` - Text splitting with overlap
- `embeddings.py` - OpenAI/Ollama embedding generation
- `search.py` - Semantic + keyword hybrid search
- `app.py` - FastAPI routes, job queue, API endpoints

### Frontend
- `base.html` - Layout, sidebar, CSS (glow effects), Alpine.js globals
- `sources.html` - Source list, filters, delete/refresh modals
- `add_modal.html` - Add source modal (crawl/upload, tags, knowledge type)
- `dashboard.html` - Stats, recent sources, embedding progress

## Patterns

### API Routes (app.py)
```python
@app.post("/api/crawl")
async def api_crawl(request: Request, background_tasks: BackgroundTasks):
    # Start background job, return job_id
```

### Alpine.js State (templates)
```html
<div x-data="{ modalState: { show: false, data: null } }">
  <button @click="modalState.show = true">Open</button>
  <div x-show="modalState.show">...</div>
</div>
```

### Glow CSS Classes
- `glow-card`, `glow-card-cyan`, `glow-card-purple` - Card borders
- `glow-btn`, `glow-btn-purple`, `glow-btn-red` - Button effects
- `glow-modal` - Modal frame glow

## Database Schema (Supabase)
- `sources` - id, url, title, source_type, metadata (tags, knowledge_type, max_depth)
- `chunks` - id, source_id, content, embedding, metadata
