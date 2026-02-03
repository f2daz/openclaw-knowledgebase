# Changelog

All notable changes to OpenClaw Knowledgebase.

## [0.1.0] - 2026-02-03

### Added

#### Core
- Initial release with Ollama + Supabase/pgvector
- Semantic search with 768-dim embeddings (nomic-embed-text)
- Hybrid search combining semantic + keyword matching
- Configurable table prefix for existing schemas

#### Ingestion
- **Chunker** - Text splitting with overlap, markdown-aware
- **Web Crawler** - Single page or recursive with depth control
- **Document Parser** - Native + Docling support

#### Native Format Support
- Plain text (`.txt`)
- Markdown (`.md`, `.markdown`)
- reStructuredText (`.rst`)
- JSON (`.json`) - formatted as code block
- YAML (`.yaml`, `.yml`)
- CSV (`.csv`) - converted to markdown table
- TSV (`.tsv`)

#### Docling Format Support (optional)
- PDF (`.pdf`)
- Word (`.docx`, `.doc`)
- PowerPoint (`.pptx`, `.ppt`)
- Excel (`.xlsx`, `.xls`)
- HTML (`.html`, `.htm`)

#### CLI
- `kb status` - Connection check and stats
- `kb find` - Semantic/hybrid search
- `kb sources` - List sources
- `kb embed` - Generate embeddings
- `kb serve` - Start web UI

#### Web UI
- **Dashboard** - Stats, connections, recent sources
- **Search** - Live search with HTMX
- **Sources** - Browse and delete
- **Add Modal** - URL crawling and file upload
- **Settings** - Config overview

#### API
- REST endpoints for search, sources, stats
- Background job system for crawling/uploading
- Health check endpoint

### Technical
- FastAPI + Jinja2 + HTMX + Tailwind CSS
- Alpine.js for modal interactions
- Glassmorphism design
- Client-side vector search fallback

---

## Roadmap

### [0.2.0] - Planned
- [ ] Source refresh/re-crawl
- [ ] Batch operations
- [ ] Export functionality
- [ ] Search history
- [ ] Tags for sources

### [0.3.0] - Planned
- [ ] Multiple embedding models
- [ ] Re-embedding with different model
- [ ] Chunk size tuning per source
- [ ] Better progress tracking
