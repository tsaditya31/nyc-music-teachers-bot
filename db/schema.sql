-- NYC Kids Activities Database Schema

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ZIP → neighborhood → borough reference
CREATE TABLE IF NOT EXISTS neighborhoods (
    zip_code    TEXT PRIMARY KEY,
    neighborhood TEXT NOT NULL,
    borough     TEXT NOT NULL
);

-- Tracked crawl target URLs
CREATE TABLE IF NOT EXISTS sources (
    id              SERIAL PRIMARY KEY,
    url             TEXT NOT NULL UNIQUE,
    name            TEXT,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'active', 'paused', 'failed', 'rejected', 'blocked', 'error', 'inactive')),
    reliability_score REAL DEFAULT 0.5,
    discovered_by   TEXT NOT NULL DEFAULT 'seed'
                    CHECK (discovered_by IN ('seed', 'agent')),
    category        TEXT,
    notes           TEXT,
    last_crawled_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Main activities table
CREATE TABLE IF NOT EXISTS activities (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    category        TEXT,
    subcategory     TEXT,
    age_range       TEXT,
    location_name   TEXT,
    address         TEXT,
    zip_code        TEXT REFERENCES neighborhoods(zip_code) ON DELETE SET NULL,
    neighborhood    TEXT,
    borough         TEXT,
    price           TEXT,
    schedule        TEXT,
    source_url      TEXT,
    source_id       INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    contact_email   TEXT,
    contact_phone   TEXT,
    website         TEXT,
    tags            TEXT[] DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'expired', 'pending_review')),
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(name, address, source_url)
);

-- Full-text search indexes
CREATE INDEX IF NOT EXISTS idx_activities_name_trgm
    ON activities USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_activities_description_trgm
    ON activities USING gin (description gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_activities_category
    ON activities (category);
CREATE INDEX IF NOT EXISTS idx_activities_borough
    ON activities (borough);
CREATE INDEX IF NOT EXISTS idx_activities_zip
    ON activities (zip_code);
CREATE INDEX IF NOT EXISTS idx_activities_status
    ON activities (status);
CREATE INDEX IF NOT EXISTS idx_activities_source_id
    ON activities (source_id);

CREATE INDEX IF NOT EXISTS idx_sources_status
    ON sources (status);
CREATE INDEX IF NOT EXISTS idx_sources_last_crawled
    ON sources (last_crawled_at);

-- Crawl session history
CREATE TABLE IF NOT EXISTS crawl_log (
    id              SERIAL PRIMARY KEY,
    source_id       INTEGER REFERENCES sources(id) ON DELETE CASCADE,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    status          TEXT NOT NULL DEFAULT 'running'
                    CHECK (status IN ('running', 'success', 'error')),
    pages_crawled   INTEGER DEFAULT 0,
    activities_found INTEGER DEFAULT 0,
    activities_new  INTEGER DEFAULT 0,
    activities_updated INTEGER DEFAULT 0,
    tokens_used     INTEGER DEFAULT 0,
    error_message   TEXT
);
