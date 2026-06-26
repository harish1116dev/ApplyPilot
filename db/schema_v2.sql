-- ============================================================
-- CareerOS v2 — Additional Tables
-- Run these AFTER schema.sql (they extend it)
-- ============================================================

-- Company Memory: stores learned info about each company
CREATE TABLE IF NOT EXISTS companies (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  company_name TEXT UNIQUE NOT NULL,
  platform TEXT,                          -- detected apply platform
  typical_questions JSONB DEFAULT '[]',   -- questions they usually ask
  required_docs JSONB DEFAULT '[]',       -- cover letter, portfolio, etc.
  avg_match_score NUMERIC DEFAULT 0,
  total_applications INTEGER DEFAULT 0,
  last_applied_at TIMESTAMPTZ,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Skill Gaps: periodic analysis snapshots
CREATE TABLE IF NOT EXISTS skill_gaps (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  gaps JSONB DEFAULT '[]',               -- [{skill, frequency, impact, resources}]
  summary TEXT,
  total_jobs_analyzed INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Failure Log: full context of every plugin failure
CREATE TABLE IF NOT EXISTS failure_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  job_id UUID REFERENCES jobs(id) ON DELETE SET NULL,
  company TEXT,
  title TEXT,
  apply_url TEXT,
  stage TEXT,                            -- 'analyze' | 'match' | 'apply' | 'scrape'
  error TEXT,
  traceback TEXT,
  screenshot_path TEXT,
  html_path TEXT,
  extra JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add file_hash to resumes for versioning
ALTER TABLE resumes ADD COLUMN IF NOT EXISTS file_hash TEXT;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_companies_name ON companies(company_name);
CREATE INDEX IF NOT EXISTS idx_skill_gaps_date ON skill_gaps(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_failure_log_date ON failure_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_failure_log_stage ON failure_log(stage);
