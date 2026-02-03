# 🦞 OpenClaw Knowledgebase

A self-hosted RAG (Retrieval-Augmented Generation) system using **Ollama** for local embeddings and **Supabase/pgvector** for vector storage.

**100% local. 100% free. No OpenAI API needed.**

## ✨ Features

- 🔒 **Fully Local** - Embeddings via Ollama, self-hosted Supabase
- 💸 **Zero Cost** - No API fees, runs on your hardware
- 🔍 **Hybrid Search** - Semantic + keyword search combined
- 🌐 **Web UI** - Beautiful dashboard with live search
- 📄 **Multi-Format** - PDF, Word, Excel, PowerPoint, CSV, JSON, Markdown...
- ⚡ **Fast** - ~4 embeddings/second on Apple Silicon
- 🧩 **OpenClaw Ready** - Designed for [OpenClaw](https://github.com/openclaw/openclaw) AI agents

## 📸 Screenshots

<details>
<summary>Dashboard</summary>

The dashboard shows stats, connection status, and recent sources at a glance.
</details>

<details>
<summary>Search</summary>

Live semantic search with hybrid mode option. Results show similarity scores and content previews.
</details>

<details>
<summary>Add Knowledge</summary>

Add sources by crawling URLs or uploading documents. Supports depth control for web crawling.
</details>

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- [Ollama](https://ollama.ai) running locally or on your network
- [Supabase](https://supabase.com) (self-hosted or cloud) with pgvector

### Installation

```bash
# Clone the repo
git clone https://github.com/f2daz/openclaw-knowledgebase.git
cd openclaw-knowledgebase

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .

# For web UI
pip install -e ".[web]"

# For document parsing (PDF, DOCX, etc.)
pip install -e ".[docling]"

# For web crawling
pip install -e ".[crawl]"

# Everything
pip install -e ".[all]"
```

### Setup

1. **Pull the embedding model:**
```bash
ollama pull nomic-embed-text
```

2. **Create the database schema:**
```bash
# Run schema.sql in your Supabase SQL editor
# Or via psql:
psql $DATABASE_URL -f schema.sql
```

3. **Configure environment:**
```bash
cp .env.example .env
# Edit .env with your Supabase URL, key, and Ollama URL
```

### First Run

```bash
# Check everything is connected
kb status

# Start the web UI
kb serve

# Open http://localhost:8080
```

## 📖 CLI Reference

```bash
# Status & Health
kb status              # Check connections, show stats

# Search
kb find "query"        # Semantic search
kb find "query" --hybrid   # Hybrid search (semantic + keyword)
kb find "query" -n 20  # More results
kb find "query" -t 0.3 # Lower similarity threshold

# Sources
kb sources             # List all sources

# Embeddings
kb embed               # Generate embeddings for new chunks
kb embed --batch-size 100  # Larger batches

# Web UI
kb serve               # Start on port 8080
kb serve -p 3000       # Custom port
kb serve --reload      # Dev mode with auto-reload
```

## 📄 Supported Formats

### Native (no dependencies)
| Format | Extensions | Notes |
|--------|------------|-------|
| Plain Text | `.txt` | As-is |
| Markdown | `.md`, `.markdown` | Header-aware chunking |
| reStructuredText | `.rst` | Python docs format |
| JSON | `.json` | Formatted code block |
| YAML | `.yaml`, `.yml` | Formatted code block |
| CSV | `.csv` | Converted to Markdown table |
| TSV | `.tsv` | Converted to Markdown table |

### With Docling (`pip install .[docling]`)
| Format | Extensions | Notes |
|--------|------------|-------|
| PDF | `.pdf` | Full text extraction, tables, images |
| Word | `.docx`, `.doc` | Preserves structure |
| PowerPoint | `.pptx`, `.ppt` | Slide content |
| Excel | `.xlsx`, `.xls` | Sheet content |
| HTML | `.html`, `.htm` | Cleaned content |

### Web Crawling (`pip install .[crawl]`)
- Single page or recursive crawling
- Configurable depth (0-3 levels)
- Same-domain restriction
- Rate limiting
- Sitemap support

## 🌐 Web UI

Start the web interface:

```bash
kb serve
```

Open http://localhost:8080

### Features

- **Dashboard** - Stats overview, connection status, recent sources
- **Search** - Live semantic search with HTMX, hybrid mode toggle
- **Sources** - Browse, delete sources
- **Add Knowledge** - Crawl URLs or upload documents
- **Settings** - View configuration, CLI reference

### API Endpoints

```bash
# Health check
GET /api/health

# Search
GET /api/search?q=query&hybrid=false&limit=10

# Stats
GET /api/stats

# Sources
GET /api/sources
DELETE /api/sources/{id}

# Ingestion
POST /api/crawl    # Form: url, max_depth, title
POST /api/upload   # Form: file, title

# Jobs
GET /api/jobs
GET /api/jobs/{id}
```

## 🔌 Python API

```python
from knowledgebase import search, search_hybrid, KnowledgeBase

# Quick semantic search
results = search("home assistant automation", limit=5)
for r in results:
    print(f"[{r['similarity']:.2f}] {r['title']}")
    print(f"  {r['content'][:200]}...")

# Hybrid search (better for specific terms)
results = search_hybrid("zigbee pairing mode", limit=5)

# Full client access
kb = KnowledgeBase()
stats = kb.stats()
sources = kb.list_sources()

# Add content programmatically
source = kb.add_source(
    url="https://docs.example.com",
    title="Example Docs",
    source_type="web"
)

kb.add_chunk(
    source_id=source.id,
    content="Your text content here...",
    chunk_index=0,
    metadata={"section": "intro"}
)
```

## ⚙️ Configuration

Environment variables (`.env`):

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase REST API URL | Required |
| `SUPABASE_KEY` | Supabase service key | Required |
| `TABLE_PREFIX` | Table name prefix | `kb` |
| `OLLAMA_URL` | Ollama API URL | `http://localhost:11434` |
| `EMBEDDING_MODEL` | Ollama model | `nomic-embed-text` |
| `EMBEDDING_DIM` | Vector dimensions | `768` |
| `CHUNK_SIZE` | Characters per chunk | `1000` |
| `CHUNK_OVERLAP` | Overlap between chunks | `200` |

> **Tip:** Use `TABLE_PREFIX=jarvis` if you have existing `jarvis_sources`/`jarvis_chunks` tables from Archon.

## 🗄️ Database Schema

Two main tables (with configurable prefix):

```sql
-- Sources: tracked URLs/documents
{prefix}_sources (
    id UUID PRIMARY KEY,
    url TEXT UNIQUE,
    title TEXT,
    source_type TEXT,  -- 'web', 'document'
    metadata JSONB,
    created_at TIMESTAMP
)

-- Chunks: text segments with embeddings
{prefix}_chunks (
    id SERIAL PRIMARY KEY,
    source_id UUID REFERENCES {prefix}_sources,
    chunk_index INTEGER,
    content TEXT,
    metadata JSONB,
    embedding vector(768),
    created_at TIMESTAMP
)
```

Search functions (if using provided schema):
- `{prefix}_search_semantic()` - Vector similarity search
- `{prefix}_search_hybrid()` - Combined semantic + keyword

## 🧩 OpenClaw Integration

### As a Skill

Copy the skill to your OpenClaw workspace:

```bash
cp -r skills/knowledgebase ~/clawd/skills/
```

The agent can then search your knowledge base before answering questions.

### Direct Integration

```python
# In your agent code
from knowledgebase import search

def answer_with_context(question: str) -> str:
    # Search knowledge base
    results = search(question, limit=3)
    
    # Build context from results
    context = "\n\n".join([
        f"Source: {r['title']}\n{r['content']}"
        for r in results
    ])
    
    # Use context in your prompt
    return f"Based on:\n{context}\n\nAnswer: {question}"
```

## 📊 Embedding Models

| Model | Dimensions | Speed | Quality | Notes |
|-------|-----------|-------|---------|-------|
| `nomic-embed-text` | 768 | ⚡⚡⚡ | ⭐⭐⭐ | **Default**, best balance |
| `mxbai-embed-large` | 1024 | ⚡⚡ | ⭐⭐⭐⭐ | Higher quality |
| `all-minilm` | 384 | ⚡⚡⚡⚡ | ⭐⭐ | Fastest, lower quality |
| `snowflake-arctic-embed` | 1024 | ⚡⚡ | ⭐⭐⭐⭐ | Good for technical docs |

To change models, update `EMBEDDING_MODEL` and `EMBEDDING_DIM` in `.env`, then re-embed your content.

## 🔧 Troubleshooting

### "No results found"
- Check if embeddings exist: `kb status`
- Lower the threshold: `kb find "query" -t 0.3`
- Try hybrid search: `kb find "query" --hybrid`

### "Ollama connection failed"
- Ensure Ollama is running: `ollama serve`
- Check the URL in `.env`
- Pull the model: `ollama pull nomic-embed-text`

### "Supabase connection failed"
- Verify `SUPABASE_URL` and `SUPABASE_KEY`
- Ensure pgvector extension is enabled
- Check if tables exist (run `schema.sql`)

### Slow PDF processing
- First PDF triggers Docling model download (~500MB)
- Subsequent PDFs are faster
- Large PDFs may take 30-60 seconds

## 🤝 Contributing

PRs welcome! Please:
1. Open an issue first for larger changes
2. Follow existing code style
3. Add tests for new features
4. Update docs as needed

## 📄 License

MIT License - see [LICENSE](LICENSE)

## 🙏 Credits

- [Ollama](https://ollama.ai) - Local LLM inference
- [Supabase](https://supabase.com) - Postgres + pgvector
- [Docling](https://github.com/DS4SD/docling) - Document parsing (IBM)
- [OpenClaw](https://github.com/openclaw/openclaw) - AI agent framework
- [HTMX](https://htmx.org) - Web UI interactions
- [Tailwind CSS](https://tailwindcss.com) - Styling

---

Built with 🦞 by the OpenClaw community
