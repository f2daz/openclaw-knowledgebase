-- OpenClaw Knowledgebase Schema
-- Requires: pgvector extension

-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Sources table: tracks ingested URLs/documents
CREATE TABLE IF NOT EXISTS kb_sources (
    id SERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    title TEXT,
    source_type TEXT DEFAULT 'web',  -- web, pdf, docx, markdown, etc.
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Chunks table: text chunks with embeddings
CREATE TABLE IF NOT EXISTS kb_chunks (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES kb_sources(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    chunk_number INTEGER NOT NULL,
    title TEXT,
    summary TEXT,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding vector(768),  -- nomic-embed-text dimensions
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(url, chunk_number)
);

-- Index for fast vector similarity search
CREATE INDEX IF NOT EXISTS kb_chunks_embedding_idx 
ON kb_chunks 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for keyword search
CREATE INDEX IF NOT EXISTS kb_chunks_content_idx 
ON kb_chunks 
USING gin (to_tsvector('english', content));

-- Semantic search function
CREATE OR REPLACE FUNCTION kb_search_semantic(
    query_embedding vector(768),
    match_count INT DEFAULT 10,
    similarity_threshold FLOAT DEFAULT 0.5
)
RETURNS TABLE (
    id INT,
    url TEXT,
    title TEXT,
    content TEXT,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        c.id,
        c.url,
        c.title,
        c.content,
        1 - (c.embedding <=> query_embedding) AS similarity
    FROM kb_chunks c
    WHERE c.embedding IS NOT NULL
      AND 1 - (c.embedding <=> query_embedding) > similarity_threshold
    ORDER BY c.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Hybrid search function (semantic + keyword)
CREATE OR REPLACE FUNCTION kb_search_hybrid(
    query_embedding vector(768),
    query_text TEXT,
    match_count INT DEFAULT 10,
    semantic_weight FLOAT DEFAULT 0.7
)
RETURNS TABLE (
    id INT,
    url TEXT,
    title TEXT,
    content TEXT,
    semantic_score FLOAT,
    keyword_score FLOAT,
    combined_score FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH semantic AS (
        SELECT 
            c.id,
            c.url,
            c.title,
            c.content,
            1 - (c.embedding <=> query_embedding) AS score
        FROM kb_chunks c
        WHERE c.embedding IS NOT NULL
    ),
    keyword AS (
        SELECT 
            c.id,
            ts_rank(to_tsvector('english', c.content), plainto_tsquery('english', query_text)) AS score
        FROM kb_chunks c
        WHERE to_tsvector('english', c.content) @@ plainto_tsquery('english', query_text)
    )
    SELECT 
        s.id,
        s.url,
        s.title,
        s.content,
        s.score AS semantic_score,
        COALESCE(k.score, 0) AS keyword_score,
        (s.score * semantic_weight + COALESCE(k.score, 0) * (1 - semantic_weight)) AS combined_score
    FROM semantic s
    LEFT JOIN keyword k ON s.id = k.id
    ORDER BY combined_score DESC
    LIMIT match_count;
END;
$$;

-- Function to get embedding stats
CREATE OR REPLACE FUNCTION kb_stats()
RETURNS TABLE (
    total_sources BIGINT,
    total_chunks BIGINT,
    chunks_with_embeddings BIGINT,
    chunks_without_embeddings BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        (SELECT COUNT(*) FROM kb_sources),
        (SELECT COUNT(*) FROM kb_chunks),
        (SELECT COUNT(*) FROM kb_chunks WHERE embedding IS NOT NULL),
        (SELECT COUNT(*) FROM kb_chunks WHERE embedding IS NULL);
END;
$$;
