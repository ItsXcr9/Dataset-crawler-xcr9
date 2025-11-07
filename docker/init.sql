-- Database initialization for crawler dataset system

-- Create extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Jobs table for tracking crawler and processing jobs
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'queued',
    progress REAL DEFAULT 0.0,
    message TEXT,
    parameters JSONB,
    result JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Documents table for tracking crawled documents
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(100) PRIMARY KEY,
    url TEXT NOT NULL,
    domain VARCHAR(255),
    title TEXT,
    content_hash VARCHAR(64),
    duplicate_hash VARCHAR(64),
    language VARCHAR(10),
    language_confidence REAL,
    quality_score REAL,
    content_length INTEGER,
    token_estimate INTEGER,
    crawl_depth INTEGER,
    status_code INTEGER,
    crawled_at TIMESTAMP WITH TIME ZONE,
    processed_at TIMESTAMP WITH TIME ZONE,
    job_id UUID REFERENCES jobs(id)
);

-- Dataset versions table
CREATE TABLE IF NOT EXISTS dataset_versions (
    version VARCHAR(20) PRIMARY KEY,
    description TEXT,
    statistics JSONB,
    quality_metrics JSONB,
    provenance JSONB,
    checksum VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    file_count INTEGER,
    total_size_bytes BIGINT
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_type ON jobs(job_type);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain);
CREATE INDEX IF NOT EXISTS idx_documents_language ON documents(language);
CREATE INDEX IF NOT EXISTS idx_documents_quality ON documents(quality_score);
CREATE INDEX IF NOT EXISTS idx_documents_crawled_at ON documents(crawled_at);
CREATE INDEX IF NOT EXISTS idx_documents_job_id ON documents(job_id);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for jobs table
CREATE TRIGGER update_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert initial data
INSERT INTO dataset_versions (version, description, statistics, quality_metrics, provenance)
VALUES (
    '1.0',
    'Initial dataset version',
    '{"total_docs": 0, "total_tokens": 0}',
    '{"avg_quality": 0.0}',
    '{"source": "initial_setup"}'
) ON CONFLICT (version) DO NOTHING;
