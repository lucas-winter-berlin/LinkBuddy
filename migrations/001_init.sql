-- LinkBuddy Schema (PostgreSQL / Supabase)
-- Wird vom Bot beim Start auch automatisch via SQLAlchemy angelegt.
-- Dieses SQL ist als Referenz / manueller Setup-Pfad gedacht.

CREATE TABLE IF NOT EXISTS resources (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  url TEXT NOT NULL,
  url_hash VARCHAR(64) NOT NULL,
  title TEXT,
  tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  tags_text TEXT NOT NULL DEFAULT '||',
  notes TEXT,
  source VARCHAR(32) NOT NULL DEFAULT 'website',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at TIMESTAMPTZ,
  status VARCHAR(16) NOT NULL DEFAULT 'active',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS ix_resources_user_id ON resources (user_id);
CREATE INDEX IF NOT EXISTS ix_resources_url_hash ON resources (url_hash);
CREATE INDEX IF NOT EXISTS ix_resources_user_status_created
  ON resources (user_id, status, created_at);
CREATE INDEX IF NOT EXISTS ix_resources_user_hash
  ON resources (user_id, url_hash);

CREATE TABLE IF NOT EXISTS resource_duplicates (
  original_id BIGINT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
  duplicate_id BIGINT NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
  merged_at TIMESTAMPTZ,
  PRIMARY KEY (original_id, duplicate_id)
);

CREATE TABLE IF NOT EXISTS tag_stats (
  user_id BIGINT NOT NULL,
  tag VARCHAR(128) NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  last_used TIMESTAMPTZ,
  co_occurrences JSONB NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (user_id, tag)
);

CREATE TABLE IF NOT EXISTS export_logs (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL,
  export_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  link_count INTEGER NOT NULL DEFAULT 0,
  file_path TEXT,
  status VARCHAR(16) NOT NULL DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS ix_export_logs_user_id ON export_logs (user_id);
