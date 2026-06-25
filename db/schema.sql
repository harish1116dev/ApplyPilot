-- ============================================================
-- Career Bot — Supabase Schema
-- Run these in Supabase SQL Editor in order
-- ============================================================

-- Table 1: All scraped jobs
CREATE TABLE IF NOT EXISTS jobs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  title TEXT NOT NULL,
  company TEXT NOT NULL,
  location TEXT,
  remote BOOLEAN DEFAULT FALSE,
  salary_min INTEGER,
  salary_max INTEGER,
  experience_required TEXT,
  skills_required JSONB DEFAULT '[]',
  description TEXT,
  apply_url TEXT,
  apply_method TEXT,
  platform TEXT,
  source_urls JSONB DEFAULT '[]',
  deadline DATE,
  hiring_manager TEXT,
  questions JSONB DEFAULT '[]',
  raw_jd TEXT,
  match_score INTEGER,
  match_reason TEXT,
  missing_skills JSONB DEFAULT '[]',
  decision TEXT,
  status TEXT DEFAULT 'found',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 2: Application tracking
CREATE TABLE IF NOT EXISTS applications (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  job_id UUID REFERENCES jobs(id),
  resume_variant TEXT,
  cover_letter_used BOOLEAN DEFAULT FALSE,
  applied_at TIMESTAMPTZ DEFAULT NOW(),
  apply_method TEXT,
  status TEXT DEFAULT 'applied',
  status_updated_at TIMESTAMPTZ,
  notes TEXT,
  interview_date TIMESTAMPTZ,
  offer_details TEXT
);

-- Table 3: Resume variants tracking
CREATE TABLE IF NOT EXISTS resumes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  variant TEXT NOT NULL,
  optimized_for_job UUID REFERENCES jobs(id),
  keywords_added JSONB DEFAULT '[]',
  generated_at TIMESTAMPTZ DEFAULT NOW(),
  file_path TEXT
);

-- Table 4: Telegram notification log
CREATE TABLE IF NOT EXISTS notifications (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  type TEXT,
  message TEXT,
  sent_at TIMESTAMPTZ DEFAULT NOW(),
  delivered BOOLEAN DEFAULT TRUE
);

-- Table 5: Manual tasks queue
CREATE TABLE IF NOT EXISTS manual_tasks (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  job_id UUID REFERENCES jobs(id),
  reason TEXT,
  apply_url TEXT,
  resume_path TEXT,
  prepared_answers JSONB DEFAULT '{}',
  status TEXT DEFAULT 'pending',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

-- Table 6: Outcome tracking (you update this)
CREATE TABLE IF NOT EXISTS outcomes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  application_id UUID REFERENCES applications(id),
  outcome TEXT,
  days_to_response INTEGER,
  feedback TEXT,
  recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 7: Learning log
CREATE TABLE IF NOT EXISTS learning_log (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  analysis_date DATE DEFAULT CURRENT_DATE,
  total_applications INTEGER,
  total_rejected INTEGER,
  total_interviews INTEGER,
  total_ghosted INTEGER,
  top_missing_skills JSONB DEFAULT '[]',
  top_companies_applied JSONB DEFAULT '[]',
  avg_match_score NUMERIC,
  recommendations JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_match_score ON jobs(match_score DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_manual_tasks_status ON manual_tasks(status);
