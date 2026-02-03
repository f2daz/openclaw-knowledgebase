# 🦞 OpenClaw Knowledgebase

A simple, self-hosted RAG (Retrieval-Augmented Generation) system using **Ollama** for local embeddings and **Supabase/pgvector** for vector storage.

**100% local. 100% free. No OpenAI API needed.**

## ✨ Features

- 🔒 **Fully Local** - Embeddings via Ollama, self-hosted Supabase
- 💸 **Zero Cost** - No API fees, runs on your hardware
- 📄 **Multi-Format Ingestion** - PDFs, DOCX, URLs, Markdown (via Docling)
- 🔍 **Hybrid Search** - Semantic + keyword search combined
- ⚡ **Fast** - ~4 embeddings/second on Apple Silicon
- 🧩 **OpenClaw Ready** - Designed for [OpenClaw](https://github.com/openclaw/openclaw) AI agents

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

# Install dependencies (using uv - recommended)
uv sync

# Or with pip
pip install -e .
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

### Usage

**Crawl a website:**
```bash
uv run python -m knowledgebase.cli crawl https://docs.home-assistant.io
```

**Ingest local documents (PDF, DOCX, etc.):**
```bash
uv run python -m knowledgebase.cli ingest ./documents/
```

**Search the knowledge base:**
```bash
uv run python -m knowledgebase.cli search "How do I set up automations?"
```

**Generate embeddings for new content:**
```bash
uv run python -m knowledgebase.cli embed
```

## 📐 Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Sources   │────▶│   Docling   │────▶│   Chunks    │
│ PDF/URL/... │     │   Parser    │     │  Markdown   │
└─────────────┘     └─────────────┘     └─────────────┘
                                               │
                                               ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Search    │◀────│  Supabase   │◀────│   Ollama    │
│   Results   │     │  pgvector   │     │  Embeddings │
└─────────────┘     └─────────────┘     └─────────────┘
```

## 🗄️ Database Schema

Two main tables:
- `kb_sources` - Tracked URLs/documents with metadata
- `kb_chunks` - Text chunks with 768-dim embeddings

Search functions:
- `kb_search_semantic()` - Pure vector similarity search
- `kb_search_hybrid()` - Combined semantic + keyword search

## ⚙️ Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `SUPABASE_URL` | Supabase REST API URL | - |
| `SUPABASE_KEY` | Supabase service key | - |
| `TABLE_PREFIX` | Prefix for table names (`kb` → `kb_sources`, `kb_chunks`) | `kb` |
| `OLLAMA_URL` | Ollama API URL | `http://localhost:11434` |
| `EMBEDDING_MODEL` | Ollama model for embeddings | `nomic-embed-text` |
| `CHUNK_SIZE` | Characters per chunk | `1000` |
| `CHUNK_OVERLAP` | Overlap between chunks | `200` |

> **Tip:** Use `TABLE_PREFIX=jarvis` if you have existing `jarvis_sources`/`jarvis_chunks` tables.

## 🔌 OpenClaw Integration

Add to your agent's skill or use directly:

```python
from knowledgebase import search

# Semantic search
results = search("home assistant automation", limit=5)

for chunk in results:
    print(f"[{chunk['similarity']:.2f}] {chunk['content'][:200]}...")
```

## 📊 Embedding Models

| Model | Dimensions | Speed | Quality |
|-------|-----------|-------|---------|
| `nomic-embed-text` | 768 | ⚡⚡⚡ | ⭐⭐⭐ |
| `mxbai-embed-large` | 1024 | ⚡⚡ | ⭐⭐⭐⭐ |
| `all-minilm` | 384 | ⚡⚡⚡⚡ | ⭐⭐ |

Default: `nomic-embed-text` - best balance of speed and quality.

## 🤝 Contributing

PRs welcome! Please open an issue first to discuss larger changes.

## 📄 License

MIT License - see [LICENSE](LICENSE)

## 🙏 Credits

- [Ollama](https://ollama.ai) - Local LLM inference
- [Supabase](https://supabase.com) - Postgres + pgvector
- [Docling](https://github.com/docling-project/docling) - Document parsing
- [OpenClaw](https://github.com/openclaw/openclaw) - AI agent framework

---

Built with 🦞 by the OpenClaw community
