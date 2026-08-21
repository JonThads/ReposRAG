-- pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Chunks: text + metadata + vector
CREATE TABLE IF NOT EXISTS chunks (
    id                  SERIAL PRIMARY KEY,
    repo                TEXT NOT NULL,
    file_path           TEXT NOT NULL,
    chunk_index         INTEGER NOT NULL,
    heading_context     TEXT,
    content             TEXT NOT NULL,
    token_count         INTEGER NOT NULL,
    embedding           vector(384),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (repo, file_path, chunk_index)
);

-- IVFFlat Search Index
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS chunks_repo_idx ON chunks (repo);