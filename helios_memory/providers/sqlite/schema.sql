-- Helios Memory SQLite schema (idempotent)

CREATE TABLE IF NOT EXISTS cache_entries (
    key TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    ttl INTEGER,
    recency REAL NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 1.0,
    tags TEXT NOT NULL DEFAULT '[]',
    source TEXT,
    created_at TEXT NOT NULL,
    expires_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_cache_entries_expires_at ON cache_entries(expires_at);
CREATE INDEX IF NOT EXISTS idx_cache_entries_created_at ON cache_entries(created_at);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    tier TEXT NOT NULL CHECK (tier IN ('holographic', 'mnemosyne', 'archive')),
    content TEXT NOT NULL,
    memory_type TEXT NOT NULL DEFAULT 'general',
    confidence REAL NOT NULL DEFAULT 1.0,
    tags TEXT NOT NULL DEFAULT '[]',
    source TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    decay_factor REAL NOT NULL DEFAULT 1.0,
    superseded_by TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_tier ON memories(tier);
CREATE INDEX IF NOT EXISTS idx_memories_memory_type ON memories(memory_type);
CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_superseded_by ON memories(superseded_by);

CREATE TABLE IF NOT EXISTS memory_events (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    actor TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(id)
);

CREATE INDEX IF NOT EXISTS idx_memory_events_memory_id ON memory_events(memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_events_created_at ON memory_events(created_at);
CREATE INDEX IF NOT EXISTS idx_memory_events_event_type ON memory_events(event_type);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    level INTEGER NOT NULL CHECK (level IN (0, 1, 2)),
    content TEXT NOT NULL,
    embedding BLOB,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_level ON document_chunks(level);
CREATE INDEX IF NOT EXISTS idx_document_chunks_created_at ON document_chunks(created_at);

CREATE TABLE IF NOT EXISTS conflicts (
    id TEXT PRIMARY KEY,
    memory_id_a TEXT NOT NULL,
    memory_id_b TEXT NOT NULL,
    conflict_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    resolution TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (memory_id_a) REFERENCES memories(id),
    FOREIGN KEY (memory_id_b) REFERENCES memories(id)
);

CREATE INDEX IF NOT EXISTS idx_conflicts_memory_id_a ON conflicts(memory_id_a);
CREATE INDEX IF NOT EXISTS idx_conflicts_memory_id_b ON conflicts(memory_id_b);
CREATE INDEX IF NOT EXISTS idx_conflicts_status ON conflicts(status);
CREATE INDEX IF NOT EXISTS idx_conflicts_created_at ON conflicts(created_at);
