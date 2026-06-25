# Career Bot — Master Build Document
> Feed this to Cursor / Claude Code module by module. Every spec is complete and implementation-ready.

---

## 1. Folder Structure

```
career-bot/
│
├── .env                          # All secrets (never commit)
├── .env.example                  # Template (commit this)
├── .gitignore
├── requirements.txt
├── main.py                       # Orchestrator — runs full pipeline
│
├── config/
│   ├── profile.json              # Your single source of truth
│   ├── resumes/
│   │   ├── master_resume.pdf
│   │   ├── frontend_resume.pdf
│   │   ├── backend_resume.pdf
│   │   ├── fullstack_resume.pdf
│   │   ├── ai_resume.pdf
│   │   └── flutter_resume.pdf
│   └── settings.json             # Thresholds, schedules, preferences
│
├── modules/
│   ├── profile_brain.py          # Module 1 — loads + validates profile.json
│   ├── resume_library.py         # Module 2 — selects right resume per job
│   ├── job_scout/
│   │   ├── __init__.py
│   │   ├── scout.py              # Module 3 — orchestrates all scrapers
│   │   ├── naukri_scraper.py
│   │   ├── linkedin_scraper.py
│   │   ├── wellfound_scraper.py
│   │   ├── indeed_scraper.py
│   │   └── careers_scraper.py    # Company career pages
│   ├── duplicate_detector.py     # Module 4
│   ├── job_analyzer.py           # Module 5 — Gemini extracts structured JSON from JD
│   ├── match_engine.py           # Module 6 — Gemini compares profile vs job
│   ├── decision_engine.py        # Module 7 — threshold logic
│   ├── resume_optimizer.py       # Module 8 — Gemini tailors resume per job
│   ├── cover_letter_agent.py     # Module 9 — only when required
│   ├── qa_agent.py               # Module 10 — answers application questions
│   ├── platform_detector.py      # Module 11 — identifies form type from URL
│   ├── plugins/
│   │   ├── __init__.py
│   │   ├── email_plugin.py       # Module 12a
│   │   ├── google_form_plugin.py # Module 12b
│   │   ├── linkedin_plugin.py    # Module 12c
│   │   ├── lever_plugin.py       # Module 12d
│   │   ├── greenhouse_plugin.py  # Module 12e
│   │   ├── workday_plugin.py     # Module 12f
│   │   └── generic_plugin.py     # Module 12g — fallback
│   ├── human_assist.py           # Module 13 — CAPTCHA/OTP fallback
│   ├── learning_engine.py        # Module 14 — pattern detection from outcomes
│   ├── analytics.py              # Module 15 — stats aggregation
│   └── notification_agent.py     # Module 16 — Telegram notifications
│
├── db/
│   └── supabase_client.py        # Supabase connection + all DB operations
│
├── utils/
│   ├── gemini_client.py          # Gemini API wrapper with rate limiting + retry
│   ├── browser.py                # Playwright browser factory
│   ├── logger.py                 # Structured logging
│   └── helpers.py                # Shared utilities
│
├── tests/
│   ├── test_job_scout.py
│   ├── test_match_engine.py
│   └── test_plugins.py
│
└── .github/
    └── workflows/
        └── career_bot.yml        # GitHub Actions — 2x daily cron
```

---

## 2. Environment Variables

### `.env` (never commit)
```env
# Gemini
GEMINI_API_KEY=your_gemini_api_key

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# LinkedIn credentials (for scraping)
LINKEDIN_EMAIL=your_email
LINKEDIN_PASSWORD=your_password

# Naukri credentials
NAUKRI_EMAIL=your_email
NAUKRI_PASSWORD=your_password

# Email apply
GMAIL_ADDRESS=your_gmail
GMAIL_APP_PASSWORD=your_app_password  # Use Gmail App Password, not main password

# Optional: Proxy rotation (for scraping reliability)
PROXY_URL=
```

### `.env.example` (commit this)
```env
GEMINI_API_KEY=
SUPABASE_URL=
SUPABASE_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
LINKEDIN_EMAIL=
LINKEDIN_PASSWORD=
NAUKRI_EMAIL=
NAUKRI_PASSWORD=
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=
PROXY_URL=
```

### `.gitignore`
```
.env
config/resumes/
*.pdf
__pycache__/
*.pyc
.playwright/
logs/
*.log
```

---

## 3. Supabase Schema

Run these in Supabase SQL editor in order.

```sql
-- Table 1: All scraped jobs
CREATE TABLE jobs (
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
  apply_method TEXT,             -- 'email' | 'linkedin' | 'lever' | 'greenhouse' | 'workday' | 'google_form' | 'generic'
  platform TEXT,                 -- 'naukri' | 'linkedin' | 'wellfound' | 'indeed' | 'careers_page'
  source_urls JSONB DEFAULT '[]', -- all sources listing same job (for dedup)
  deadline DATE,
  hiring_manager TEXT,
  questions JSONB DEFAULT '[]',  -- application questions extracted from JD
  raw_jd TEXT,                   -- full job description text
  match_score INTEGER,
  match_reason TEXT,
  missing_skills JSONB DEFAULT '[]',
  decision TEXT,                 -- 'auto_apply' | 'manual_review' | 'ignore'
  status TEXT DEFAULT 'found',   -- 'found' | 'analyzed' | 'applied' | 'skipped' | 'manual'
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 2: Application tracking
CREATE TABLE applications (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  job_id UUID REFERENCES jobs(id),
  resume_variant TEXT,           -- 'frontend' | 'backend' | 'ai' | 'fullstack' | 'flutter'
  cover_letter_used BOOLEAN DEFAULT FALSE,
  applied_at TIMESTAMPTZ DEFAULT NOW(),
  apply_method TEXT,
  status TEXT DEFAULT 'applied', -- 'applied' | 'rejected' | 'interview' | 'ghosted' | 'offer'
  status_updated_at TIMESTAMPTZ,
  notes TEXT,
  interview_date TIMESTAMPTZ,
  offer_details TEXT
);

-- Table 3: Resume variants tracking
CREATE TABLE resumes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  variant TEXT NOT NULL,         -- 'master' | 'frontend' | 'backend' | 'ai' | 'fullstack' | 'flutter'
  optimized_for_job UUID REFERENCES jobs(id),
  keywords_added JSONB DEFAULT '[]',
  generated_at TIMESTAMPTZ DEFAULT NOW(),
  file_path TEXT
);

-- Table 4: Telegram notification log
CREATE TABLE notifications (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  type TEXT,                     -- 'morning_summary' | 'applied' | 'manual_action' | 'weekly_report'
  message TEXT,
  sent_at TIMESTAMPTZ DEFAULT NOW(),
  delivered BOOLEAN DEFAULT TRUE
);

-- Table 5: Manual tasks queue
CREATE TABLE manual_tasks (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  job_id UUID REFERENCES jobs(id),
  reason TEXT,                   -- 'captcha' | 'otp' | 'account_creation' | 'unknown_platform'
  apply_url TEXT,
  resume_path TEXT,
  prepared_answers JSONB DEFAULT '{}',
  status TEXT DEFAULT 'pending', -- 'pending' | 'completed' | 'skipped'
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

-- Table 6: Outcome tracking (you update this)
CREATE TABLE outcomes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  application_id UUID REFERENCES applications(id),
  outcome TEXT,                  -- 'rejected' | 'interview_r1' | 'interview_r2' | 'offer' | 'ghosted'
  days_to_response INTEGER,
  feedback TEXT,
  recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- Table 7: Learning log
CREATE TABLE learning_log (
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
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_match_score ON jobs(match_score DESC);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX idx_applications_status ON applications(status);
CREATE INDEX idx_manual_tasks_status ON manual_tasks(status);
```

---

## 4. `config/profile.json`

```json
{
  "personal": {
    "name": "Harish S",
    "email": "harish1116.dev@gmail.com",
    "phone": "7010308345",
    "location": "Chennai, Poonamallee, Tamil Nadu",
    "linkedin": "https://linkedin.com/in/harish-s-916b24299/",
    "github": "https://github.com/harish1116dev",
    "portfolio": "https://portfolio-tau-blush-68.vercel.app"
  },
  "target": {
    "roles": [
      "Full Stack Developer",
      "Frontend Developer",
      "Backend Developer",
      "Software Engineer",
      "Node.js Developer",
      "React Developer",
      "AI/ML Engineer",
      "Flutter Developer"
    ],
    "experience_level": "Fresher",
    "preferred_cities": ["Chennai", "Bengaluru", "Coimbatore", "Hyderabad", "Remote"],
    "salary_expectation_lpa": {
      "min": 4,
      "max": 8
    },
    "notice_period_days": 0,
    "work_type": ["full-time", "remote", "hybrid"]
  },
  "education": [
    {
      "degree": "B.Tech",
      "field": "Artificial Intelligence and Data Science",
      "institution": "S.A. Engineering College",
      "year": 2024,
      "cgpa": null
    },
    {
      "degree": "Class 12",
      "institution": "Holy Angel Higher Secondary School, Rettanai, Vilupuram",
      "year": null
    },
    {
      "degree": "Class 10",
      "institution": "Sri Raja Rajeshwari Matric High School, Pelakuppam, Tindivanam",
      "year": null
    }
  ],
  "skills": {
    "languages": ["Python", "JavaScript", "SQL", "HTML", "CSS"],
    "frontend": ["React.js", "HTML5", "CSS3", "Tailwind CSS", "Responsive Design"],
    "backend": ["Node.js", "Express.js", "REST APIs", "Authentication Systems"],
    "databases": ["Supabase", "SQLite", "PostgreSQL"],
    "tools": ["Git", "GitHub", "CLI", "Postman", "Gen AI Tools"],
    "ai_ml": ["Machine Learning", "Deep Learning", "TensorFlow", "scikit-learn", "AI/LLM Tools"],
    "other": ["Network Basics", "OS Fundamentals", "IoT", "GitHub Actions"]
  },
  "projects": [
    {
      "name": "Twitter Backend with Express",
      "description": "Built a Twitter clone backend server with RESTful APIs using Node.js and Express.js, implementing user authentication, tweet management, and follower relationships.",
      "tech_stack": ["Node.js", "Express.js", "REST APIs", "JavaScript", "SQLite"],
      "github": "https://github.com/harish1116dev",
      "live": null,
      "highlight": true,
      "category": "backend"
    },
    {
      "name": "Compass",
      "description": "AI-powered personalized daily news briefing app using Gemini API, featuring conversational onboarding, proactive profile evolution, and zero-backend architecture with React and LocalStorage.",
      "tech_stack": ["React.js", "Gemini API", "JavaScript", "LocalStorage"],
      "github": "https://github.com/harish1116dev",
      "live": null,
      "highlight": true,
      "category": "ai"
    },
    {
      "name": "ML & DL Models — Fake Healthcare News Detector",
      "description": "Built ML and DL models using synthetic medical datasets to detect fake healthcare news, combining NLP techniques with classification algorithms.",
      "tech_stack": ["Python", "TensorFlow", "scikit-learn", "NLP", "pandas"],
      "github": "https://github.com/harish1116dev",
      "live": null,
      "highlight": true,
      "category": "ai"
    },
    {
      "name": "Watt Wise",
      "description": "Designed an IoT-powered electricity monitoring platform with real-time dashboards, data storage, and energy usage prediction using ML models.",
      "tech_stack": ["IoT", "Python", "Machine Learning", "Real-time Dashboard", "Data Storage"],
      "github": "https://github.com/harish1116dev",
      "live": null,
      "highlight": true,
      "category": "fullstack"
    },
    {
      "name": "Dealzy",
      "description": "Building a geo-based local deals and offers discovery platform connecting customers with nearby shops and businesses. Features GPS-based shop registration and a hybrid map strategy.",
      "tech_stack": ["React.js", "Node.js", "Supabase", "Leaflet", "OpenStreetMap", "Google OAuth"],
      "github": "https://github.com/harish1116dev",
      "live": null,
      "highlight": true,
      "category": "fullstack",
      "status": "Under Development"
    }
  ],
  "certifications": [
    "XPM 4.0 Fundamentals",
    "LLMs & Agentic AI Masterclass",
    "Ethical Hacking Workshop",
    "AWS Workshop",
    "Gen AI Tools Workshop",
    "Data Visualization – Empowering Business with Effective Insights"
  ],
  "soft_skills": [
    "Problem Solving",
    "Time Management",
    "Fast Learner",
    "Team Collaboration",
    "Leadership"
  ],
  "languages_spoken": ["Tamil", "English"],
  "resume_variants": {
    "fullstack": ["React.js", "Node.js", "Express.js", "JavaScript", "Supabase", "REST APIs"],
    "frontend": ["React.js", "HTML5", "CSS3", "JavaScript", "Tailwind CSS", "Responsive Design"],
    "backend": ["Node.js", "Express.js", "Python", "SQL", "Supabase", "REST APIs", "Authentication"],
    "ai": ["Python", "TensorFlow", "scikit-learn", "Gemini API", "NLP", "ML/DL Models", "LLMs"],
    "flutter": ["Flutter", "Dart", "Supabase", "Firebase", "Mobile Development"]
  },
  "current_training": "NxtWave Full Stack Development (React, Node.js, Express.js, Git)"
}
```

---

## 5. `config/settings.json`

```json
{
  "match_thresholds": {
    "auto_apply": 90,
    "apply": 80,
    "manual_review": 70,
    "ignore_below": 70
  },
  "scraping": {
    "delay_between_requests_seconds": 3,
    "max_jobs_per_source": 50,
    "max_pages_per_source": 5,
    "headless": true
  },
  "gemini": {
    "model": "gemini-2.0-flash",
    "max_retries": 3,
    "retry_delay_seconds": 5,
    "rate_limit_rpm": 14
  },
  "filters": {
    "exclude_experience_above_years": 2,
    "exclude_companies": [],
    "exclude_keywords": ["senior", "lead", "manager", "10+ years", "5+ years"],
    "include_keywords": ["fresher", "0-2 years", "entry level", "junior", "graduate"]
  },
  "telegram": {
    "morning_report_hour": 9,
    "evening_report_hour": 18
  }
}
```

---

## 6. Module Specifications

### Module 1 — `profile_brain.py`
```
Input:  config/profile.json
Output: dict (profile data)

Functions:
- load_profile() → dict
- validate_profile(profile) → bool, list[errors]
- get_skills_flat(profile) → list[str]  # all skills in one flat list
- get_resume_variant_for_role(profile, role_keywords) → str  # 'frontend'|'backend'|'ai'|'fullstack'|'flutter'
```

### Module 2 — `resume_library.py`
```
Input:  role keywords from job analysis
Output: path to best matching resume PDF

Functions:
- select_resume(job_analysis: dict, profile: dict) → str (file path)
  Logic: match job's required_skills against profile.resume_variants
         return path to config/resumes/{variant}_resume.pdf
```

### Module 3 — `job_scout/scout.py`
```
Orchestrates all scrapers. Runs them in sequence with delay.

Input:  profile (for search query construction), settings
Output: list[dict] raw job listings

Functions:
- run_all_scrapers(profile, settings) → list[dict]
- build_search_query(profile) → str
  Example: '"fresher" OR "0-2 years" "software engineer" OR "full stack" Chennai OR Bengaluru'
```

### Module 3a — `job_scout/naukri_scraper.py`
```
Uses Playwright (headless Chromium).
URL: https://www.naukri.com/software-engineer-jobs-in-chennai?experience=0

Steps:
1. Launch browser with realistic user agent
2. Navigate to search results
3. Scroll to load all results
4. Extract: title, company, location, salary, experience, apply_url
5. Add 3-5 second random delay between pages
6. Return list[dict]

Anti-bot measures:
- Randomize user agent per session
- Random delays (2-5 seconds between pages)
- Realistic mouse movements via Playwright
- Max 50 results per run (don't be greedy)
```

### Module 3b — `job_scout/linkedin_scraper.py`
```
Uses LinkedIn job search API (via httpx, not browser — faster).
Endpoint: https://www.linkedin.com/jobs/search/?keywords=software+engineer+fresher&location=Chennai

Steps:
1. Login with credentials from .env
2. Search with role + location keywords
3. Extract job cards from response
4. For 90+ potential matches only: fetch full JD
5. Return list[dict]

Note: LinkedIn aggressively blocks scrapers.
Fallback: Use their public jobs RSS if blocked.
Public RSS: https://www.linkedin.com/jobs/search/?keywords=...&f_E=1 (Entry level filter)
```

### Module 3c — `job_scout/wellfound_scraper.py`
```
Wellfound (AngelList) — better for startups, less anti-bot protection.
URL: https://wellfound.com/jobs?roles[]=software-engineer&locations[]=chennai

Uses httpx + BeautifulSoup (no JS needed for initial results).
Steps:
1. GET search results page
2. Parse job cards
3. Extract: title, company, location, salary, equity, apply_url
4. Return list[dict]
```

### Module 3d — `job_scout/indeed_scraper.py`
```
URL: https://in.indeed.com/jobs?q=software+engineer+fresher&l=Chennai

Uses Playwright (Indeed is JS-heavy).
Steps:
1. Navigate search URL
2. Extract job cards
3. Paginate up to max_pages
4. Return list[dict]
```

### Module 3e — `job_scout/careers_scraper.py`
```
Targets known company career pages directly.
Maintains a list of target company career URLs.

Target companies for fresher roles:
- Zoho: https://careers.zohocorp.com/
- TCS: https://ibegin.tcs.com/iBegin/
- Infosys: https://career.infosys.com/
- Freshworks: https://www.freshworks.com/company/careers/
- Chargebee: https://www.chargebee.com/careers/
- Postman: https://www.postman.com/company/careers/
- Razorpay: https://razorpay.com/jobs/

For each URL:
1. Fetch careers page
2. Look for job listings matching target roles
3. Extract apply URLs
4. Return list[dict]
```

### Module 4 — `duplicate_detector.py`
```
Input:  list[dict] raw jobs from all scrapers
Output: list[dict] deduplicated jobs, each with source_urls list

Dedup logic:
- Normalize: lowercase title + company name
- Fuzzy match: if title similarity > 85% AND same company → same job
- Merge source_urls into one record
- Keep earliest created_at

Use: rapidfuzz library for fuzzy matching
pip install rapidfuzz
```

### Module 5 — `job_analyzer.py`
```
Input:  raw job dict (title, company, description text)
Output: structured job JSON

Gemini prompt:
"""
You are a job description parser. Extract structured data from this job description.
Return ONLY valid JSON, no markdown, no explanation.

Job Description:
{raw_jd}

Return this exact JSON structure:
{
  "title": "",
  "company": "",
  "location": "",
  "remote": false,
  "salary_min": null,
  "salary_max": null,
  "experience_required": "",
  "skills_required": [],
  "deadline": null,
  "hiring_manager": null,
  "apply_method": "",
  "questions": [],
  "cover_letter_required": false,
  "summary": ""
}
"""

Rate limiting: max 14 requests/minute (Gemini Flash free tier)
Retry: exponential backoff on 429 errors
```

### Module 6 — `match_engine.py`
```
Input:  profile dict, analyzed job dict
Output: {match: int, reason: str, missing: list[str]}

Gemini prompt:
"""
You are a recruitment AI. Compare this candidate profile against this job requirement.
Return ONLY valid JSON, no markdown.

Candidate Profile:
{profile_summary}

Job Requirements:
{job_analysis}

Return:
{
  "match": <integer 0-100>,
  "reason": "<one line explanation>",
  "missing_skills": ["skill1", "skill2"],
  "strong_matches": ["skill1", "skill2"],
  "recommendation": "auto_apply|apply|manual_review|ignore"
}

Scoring guide:
- 95-100: Perfect fit, all required skills match
- 80-94: Strong fit, minor gaps
- 70-79: Moderate fit, some important gaps
- Below 70: Poor fit, significant gaps
"""
```

### Module 7 — `decision_engine.py`
```
Input:  match result dict, settings.json thresholds
Output: decision string + action

Logic:
def decide(match_score, settings):
    thresholds = settings['match_thresholds']
    if match_score >= thresholds['auto_apply']:
        return 'auto_apply'
    elif match_score >= thresholds['apply']:
        return 'apply'          # notify you, you confirm
    elif match_score >= thresholds['manual_review']:
        return 'manual_review'  # notify you to review
    else:
        return 'ignore'
```

### Module 8 — `resume_optimizer.py`
```
Input:  profile dict, analyzed job dict, resume variant path
Output: optimized resume text (for cover letter context) + keyword list

Gemini prompt:
"""
You are an ATS resume optimizer. Given this candidate profile and job description,
suggest how to reorder/emphasize existing experience for maximum ATS score.
DO NOT add skills the candidate doesn't have. Only reorder and emphasize.
Return ONLY valid JSON.

Profile: {profile}
Job: {job_analysis}

Return:
{
  "recommended_variant": "frontend|backend|ai|fullstack|flutter",
  "keywords_to_emphasize": [],
  "project_order": [],
  "skills_to_highlight": [],
  "summary_rewrite": ""
}
"""
```

### Module 9 — `cover_letter_agent.py`
```
Runs ONLY when job analysis shows cover_letter_required: true

Input:  profile dict, analyzed job dict
Output: cover letter text (string)

Gemini prompt:
"""
Write a concise, genuine cover letter for this fresher applying to this role.
Max 200 words. No generic filler. Focus on specific skills that match.
Sound human, not robotic.

Candidate: {profile_summary}
Job: {job_title} at {company}
Why they match: {strong_matches}

Return only the cover letter text, no subject line, no formatting.
"""
```

### Module 10 — `qa_agent.py`
```
Input:  list of application questions, profile dict, job dict
Output: dict {question: answer}

Gemini prompt for each question:
"""
You are helping a fresher answer this job application question honestly.
Answer in first person. Be specific, genuine, concise (max 100 words per answer).

Candidate profile: {profile_summary}
Job: {job_title} at {company}
Question: {question}

Return only the answer text.
"""

Handle common question types:
- "Tell us about yourself" → structured intro
- "Why this company?" → research company + match reasons
- "Expected CTC?" → use profile salary range
- "Notice period?" → profile notice_period_days
- "Strengths?" → top 3 matching skills
- "Weaknesses?" → honest but growth-framed
```

### Module 11 — `platform_detector.py`
```
Input:  apply_url (string)
Output: platform string

Logic (URL pattern matching first, then HTML inspection):
def detect_platform(url):
    patterns = {
        'linkedin': ['linkedin.com/jobs', 'linkedin.com/easy-apply'],
        'lever': ['jobs.lever.co', 'lever.co'],
        'greenhouse': ['greenhouse.io', 'boards.greenhouse.io'],
        'workday': ['workday.com', 'myworkdayjobs.com'],
        'google_form': ['docs.google.com/forms', 'forms.google.com'],
        'email': [],  # detected from JD parsing, not URL
    }
    
    for platform, url_patterns in patterns.items():
        if any(p in url for p in url_patterns):
            return platform
    
    # Fallback: fetch page HTML and check for known form libraries
    return inspect_html(url)  # returns 'generic' if unknown
```

### Module 12 — Plugins

#### `plugins/email_plugin.py`
```
Input:  job dict, resume path, cover letter text, qa answers
Output: bool (success)

Steps:
1. Extract hiring email from job dict or JD text
2. Compose email with:
   Subject: "Application for {title} - {name} | Fresher | B.Tech AI & DS"
   Body: Brief intro + why interested + key skills
   Attachment: resume PDF
3. Send via Gmail SMTP (smtplib)
4. Log to applications table
```

#### `plugins/google_form_plugin.py`
```
Input:  form URL, qa answers, profile dict
Output: bool (success)

Uses Playwright:
1. Navigate to form URL
2. Identify all input fields
3. Match fields to profile/qa answers using field labels
4. Fill: name, email, phone, resume upload, text answers
5. Submit
6. Screenshot confirmation page
7. Log result

Fallback to human_assist if CAPTCHA detected
```

#### `plugins/linkedin_plugin.py`
```
Input:  job URL, profile dict, resume path
Output: bool (success)

Uses Playwright + LinkedIn session:
1. Login (or use existing session cookie)
2. Navigate to job page
3. Click "Easy Apply"
4. Fill multi-step form:
   - Contact info (from profile)
   - Resume upload
   - Screening questions (from qa_agent)
5. Submit
6. Log result

Note: LinkedIn Easy Apply varies by job — some are 1 step, some are 5.
Handle both with dynamic step detection.
```

#### `plugins/lever_plugin.py`
```
Uses Playwright:
1. Navigate to jobs.lever.co/{company}/{job_id}
2. Fill standard Lever form:
   - Name, Email, Phone
   - LinkedIn URL, GitHub URL, Portfolio URL
   - Resume upload
   - Cover letter (if required)
   - Custom questions
3. Submit
4. Log result
```

#### `plugins/greenhouse_plugin.py`
```
Uses Playwright:
1. Navigate to boards.greenhouse.io/{company}/jobs/{job_id}
2. Fill standard Greenhouse form (similar to Lever)
3. Handle file uploads
4. Submit
5. Log result
```

#### `plugins/workday_plugin.py`
```
Workday is the hardest — highly dynamic, varies by company.

Strategy:
1. Navigate to Workday job page
2. Detect form type (Apply with LinkedIn / Manual)
3. If "Apply with LinkedIn" available → use that flow
4. Else: fill manually step by step
5. On any CAPTCHA/unexpected element → trigger human_assist
6. Log result

Note: Workday often requires account creation.
If account creation detected → human_assist immediately.
```

#### `plugins/generic_plugin.py`
```
Last resort for unknown platforms.

Steps:
1. Navigate to URL
2. Try to identify: name, email, phone, resume upload fields
3. Fill what's identifiable
4. If stuck → human_assist

Returns: 'partial' | 'success' | 'human_needed'
```

### Module 13 — `human_assist.py`
```
Triggered when:
- CAPTCHA detected
- OTP required
- Account creation needed
- Plugin returns 'human_needed'
- Unknown platform

Actions:
1. Generate all materials (resume selected, answers prepared)
2. Save to manual_tasks table
3. Open URL in default browser (webbrowser.open)
4. Send Telegram notification:
   "🔴 Manual Action Needed
   Company: {company}
   Role: {title}
   Match: {score}%
   URL: {url}
   Resume: {variant} variant
   Reason: {reason}
   I've prepared all answers — open link and paste them."
5. Also send prepared answers as separate Telegram message
```

### Module 14 — `learning_engine.py`
```
Runs weekly (or manually triggered).

Input:  outcomes table, applications table, jobs table
Output: learning_log entry + Telegram report

Analysis:
1. Fetch last 30/60/100 applications
2. Group by outcome
3. Find patterns in rejected applications:
   - What skills appear most in rejected job requirements?
   - Which companies respond fastest/slowest?
   - Which platforms have best response rates?
   - Average match score of interviews vs rejections
4. Generate recommendations
5. Insert into learning_log table
6. Send Telegram weekly digest

Gemini prompt for pattern analysis:
"""
Analyze these job application outcomes and identify actionable patterns.
Return JSON with specific, actionable recommendations.

Applications data: {applications_summary}
Outcomes data: {outcomes_summary}

Return:
{
  "top_missing_skills": [],
  "best_performing_companies": [],
  "worst_performing_platforms": [],
  "avg_match_score_interviews": 0,
  "avg_match_score_rejections": 0,
  "recommendations": [
    {"priority": "high", "action": "Learn Docker", "reason": "Appears in 60% of rejections"}
  ]
}
"""
```

### Module 15 — `analytics.py`
```
Functions:
- get_summary_stats() → dict
  Returns: total_found, applied, manual_pending, rejected, interviews, offers, avg_match
- get_top_missing_skills(limit=10) → list
- get_company_stats() → list[dict]
- get_weekly_trend() → list[dict]

All queries hit Supabase directly.
```

### Module 16 — `notification_agent.py`
```
Telegram Bot API (no library needed, just httpx POST requests).

Functions:
- send_message(text) → None
- send_morning_report(stats) → None
- send_application_update(job, result) → None
- send_manual_alert(job, answers) → None
- send_weekly_digest(learning_data) → None

Morning report format:
"🌅 Good morning, Harish!
📊 Last night's run:
• Jobs found: {found}
• Auto-applied: {applied}
• Manual needed: {manual}
• Top match: {top_company} ({top_score}%)

🎯 Today's queue: {pending} jobs to review"

Application update format:
"✅ Applied!
Company: {company}
Role: {title}
Match: {score}%
Platform: {platform}
Resume: {variant}"

Weekly digest format:
"📈 Weekly Summary
Applications: {total}
Interviews: {interviews}
Response rate: {rate}%
Top missing skill: {skill}
Recommendation: {top_recommendation}"
```

---

## 7. `db/supabase_client.py`

```python
from supabase import create_client
import os

supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

# Jobs
def insert_job(job_data): ...
def get_job_by_id(job_id): ...
def update_job_status(job_id, status): ...
def get_jobs_by_decision(decision): ...
def job_exists(title, company): ...  # for deduplication

# Applications
def insert_application(app_data): ...
def update_application_status(app_id, status): ...
def get_applications_summary(): ...

# Manual tasks
def insert_manual_task(task_data): ...
def get_pending_manual_tasks(): ...
def complete_manual_task(task_id): ...

# Learning
def insert_learning_log(log_data): ...
def get_outcomes_for_analysis(limit=100): ...
```

---

## 8. `utils/gemini_client.py`

```python
import google.generativeai as genai
import time, json, os

genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-2.0-flash')

# Rate limiter state
_last_call_time = 0
_MIN_INTERVAL = 60 / 14  # 14 RPM = 4.3 seconds between calls

def call_gemini(prompt: str, retries=3) -> str:
    global _last_call_time
    
    # Rate limiting
    elapsed = time.time() - _last_call_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    
    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            _last_call_time = time.time()
            return response.text
        except Exception as e:
            if '429' in str(e):
                wait = (2 ** attempt) * 5  # exponential backoff: 5s, 10s, 20s
                time.sleep(wait)
            else:
                raise e
    raise Exception("Gemini API failed after retries")

def call_gemini_json(prompt: str) -> dict:
    raw = call_gemini(prompt)
    # Strip markdown if Gemini wraps in ```json
    clean = raw.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    return json.loads(clean)
```

---

## 9. `main.py` — Full Orchestration

```python
"""
Career Bot — Main Orchestrator
Run locally: python main.py
GitHub Actions runs this on schedule.
"""

import logging
from dotenv import load_dotenv
load_dotenv()

from modules.profile_brain import load_profile, validate_profile
from modules.job_scout.scout import run_all_scrapers
from modules.duplicate_detector import deduplicate
from modules.job_analyzer import analyze_job
from modules.match_engine import calculate_match
from modules.decision_engine import decide
from modules.resume_library import select_resume
from modules.resume_optimizer import optimize_resume
from modules.cover_letter_agent import generate_cover_letter
from modules.qa_agent import generate_answers
from modules.platform_detector import detect_platform
from modules.plugins import get_plugin
from modules.human_assist import trigger_human_assist
from modules.notification_agent import (
    send_morning_report, send_application_update, send_manual_alert
)
from modules.analytics import get_summary_stats
from db.supabase_client import insert_job, update_job_status, insert_application, job_exists
from utils.logger import setup_logger

logger = setup_logger()

def run_pipeline():
    logger.info("=== Career Bot Pipeline Starting ===")
    
    # Step 1: Load profile
    profile = load_profile()
    valid, errors = validate_profile(profile)
    if not valid:
        logger.error(f"Profile validation failed: {errors}")
        return
    
    # Step 2: Scrape jobs
    logger.info("Scraping jobs...")
    raw_jobs = run_all_scrapers(profile)
    logger.info(f"Found {len(raw_jobs)} raw jobs")
    
    # Step 3: Deduplicate
    jobs = deduplicate(raw_jobs)
    logger.info(f"After dedup: {len(jobs)} unique jobs")
    
    stats = {'found': len(jobs), 'applied': 0, 'manual': 0, 'skipped': 0}
    
    for job in jobs:
        try:
            # Skip if already in DB
            if job_exists(job['title'], job['company']):
                continue
            
            # Step 4: Analyze JD
            job_analysis = analyze_job(job)
            
            # Step 5: Match
            match_result = calculate_match(profile, job_analysis)
            job['match_score'] = match_result['match']
            job['match_reason'] = match_result['reason']
            job['missing_skills'] = match_result['missing_skills']
            
            # Step 6: Decide
            decision = decide(match_result['match'], load_settings())
            job['decision'] = decision
            
            # Save to DB
            job_id = insert_job(job)
            
            if decision == 'ignore':
                stats['skipped'] += 1
                continue
            
            if decision == 'manual_review':
                # Just notify, don't apply
                send_manual_alert(job, answers={})
                stats['manual'] += 1
                continue
            
            # Step 7: Prepare application (auto_apply or apply)
            resume_path = select_resume(job_analysis, profile)
            optimized = optimize_resume(profile, job_analysis, resume_path)
            
            cover_letter = None
            if job_analysis.get('cover_letter_required'):
                cover_letter = generate_cover_letter(profile, job_analysis)
            
            answers = {}
            if job_analysis.get('questions'):
                answers = generate_answers(job_analysis['questions'], profile, job_analysis)
            
            # Step 8: Detect platform
            platform = detect_platform(job['apply_url'])
            
            # Step 9: Apply via plugin
            plugin = get_plugin(platform)
            result = plugin.apply(job, resume_path, cover_letter, answers, profile)
            
            if result == 'success':
                insert_application({
                    'job_id': job_id,
                    'resume_variant': optimized['recommended_variant'],
                    'cover_letter_used': cover_letter is not None,
                    'apply_method': platform
                })
                update_job_status(job_id, 'applied')
                send_application_update(job, result)
                stats['applied'] += 1
                
            elif result in ('captcha', 'human_needed', 'partial'):
                trigger_human_assist(job, resume_path, answers, reason=result)
                stats['manual'] += 1
                
        except Exception as e:
            logger.error(f"Error processing job {job.get('title')} at {job.get('company')}: {e}")
            continue
    
    # Step 10: Send morning/evening report
    send_morning_report(stats)
    logger.info(f"=== Pipeline Complete: {stats} ===")


def load_settings():
    import json
    with open('config/settings.json') as f:
        return json.load(f)


if __name__ == '__main__':
    run_pipeline()
```

---

## 10. `requirements.txt`

```
# Core
python-dotenv==1.0.0
httpx==0.27.0
playwright==1.44.0
beautifulsoup4==4.12.3
lxml==5.2.2

# AI
google-generativeai==0.7.2

# Database
supabase==2.5.0

# Utilities
rapidfuzz==3.9.3
python-dateutil==2.9.0
Pillow==10.3.0

# Notifications (Telegram via httpx — no extra library needed)

# PDF handling
PyMuPDF==1.24.4

# Email
# smtplib is built-in
```

---

## 11. GitHub Actions — `.github/workflows/career_bot.yml`

```yaml
name: Career Bot Pipeline

on:
  schedule:
    # Run at 9:00 AM IST (3:30 AM UTC)
    - cron: '30 3 * * *'
    # Run at 3:00 PM IST (9:30 AM UTC)
    - cron: '30 9 * * *'
  workflow_dispatch:  # Manual trigger from GitHub UI

jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    timeout-minutes: 60

    steps:
      - name: Checkout repo
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Cache pip packages
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('requirements.txt') }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          playwright install chromium
          playwright install-deps chromium

      - name: Run Career Bot
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          TELEGRAM_BOT_TOKEN: ${{ secrets.TELEGRAM_BOT_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          LINKEDIN_EMAIL: ${{ secrets.LINKEDIN_EMAIL }}
          LINKEDIN_PASSWORD: ${{ secrets.LINKEDIN_PASSWORD }}
          NAUKRI_EMAIL: ${{ secrets.NAUKRI_EMAIL }}
          NAUKRI_PASSWORD: ${{ secrets.NAUKRI_PASSWORD }}
          GMAIL_ADDRESS: ${{ secrets.GMAIL_ADDRESS }}
          GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
        run: python main.py

      - name: Upload logs on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: career-bot-logs
          path: logs/
          retention-days: 7
```

---

## 12. Telegram Bot Setup (10 minutes)

```
Step 1: Open Telegram → search @BotFather
Step 2: Send /newbot
Step 3: Give it a name: "My Career Bot"
Step 4: Give it a username: "mycareer_harish_bot"
Step 5: Copy the token → add to .env as TELEGRAM_BOT_TOKEN

Step 6: Get your Chat ID:
  - Send any message to your new bot
  - Open: https://api.telegram.org/bot{YOUR_TOKEN}/getUpdates
  - Find "chat":{"id": XXXXXXXX} → that's your TELEGRAM_CHAT_ID

Step 7: Test it:
curl "https://api.telegram.org/bot{TOKEN}/sendMessage?chat_id={CHAT_ID}&text=Career+Bot+is+alive!"
```

---

## 13. GitHub Secrets Setup

```
Go to: GitHub repo → Settings → Secrets and variables → Actions → New repository secret

Add all secrets from your .env:
GEMINI_API_KEY
SUPABASE_URL
SUPABASE_KEY
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
LINKEDIN_EMAIL
LINKEDIN_PASSWORD
NAUKRI_EMAIL
NAUKRI_PASSWORD
GMAIL_ADDRESS
GMAIL_APP_PASSWORD
```

---

## 14. Local Testing (2-Day Plan)

### Day 1 — Core Pipeline Test
```bash
# Setup
git clone your-repo
cd career-bot
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
# Fill in .env values

# Test modules individually
python -c "from modules.profile_brain import load_profile; print(load_profile())"
python -c "from modules.job_scout.wellfound_scraper import scrape; print(scrape('software engineer', 'chennai'))"
python -c "from modules.job_analyzer import analyze_job; ..."
python -c "from modules.match_engine import calculate_match; ..."

# Run full pipeline once
python main.py
```

### Day 2 — Apply + Notify Test
```bash
# Test with a real low-stakes job posting
# Test Telegram notifications are arriving
# Test one plugin (email first — simplest)
# Test human_assist flow
# Verify Supabase tables are being populated correctly

# Once everything works locally → push to GitHub
# GitHub Actions will auto-run at 9:00 AM IST next day
```

---

## 15. Build Order for AI Coding Tools

Feed these to Cursor / Claude Code in this exact order:

```
1.  utils/logger.py              — setup first, everything logs
2.  utils/gemini_client.py       — needed by 5+ modules
3.  db/supabase_client.py        — needed by all modules
4.  config/profile.json          — fill your real data
5.  modules/profile_brain.py     — loads config
6.  modules/job_scout/wellfound_scraper.py  — easiest scraper, start here
7.  modules/job_scout/naukri_scraper.py
8.  modules/job_scout/linkedin_scraper.py
9.  modules/job_scout/indeed_scraper.py
10. modules/job_scout/careers_scraper.py
11. modules/job_scout/scout.py   — orchestrates scrapers
12. modules/duplicate_detector.py
13. modules/job_analyzer.py
14. modules/match_engine.py
15. modules/decision_engine.py
16. modules/resume_library.py
17. modules/resume_optimizer.py
18. modules/cover_letter_agent.py
19. modules/qa_agent.py
20. modules/platform_detector.py
21. modules/plugins/email_plugin.py      — easiest plugin
22. modules/plugins/google_form_plugin.py
23. modules/plugins/linkedin_plugin.py
24. modules/plugins/lever_plugin.py
25. modules/plugins/greenhouse_plugin.py
26. modules/plugins/workday_plugin.py    — hardest, do last
27. modules/plugins/generic_plugin.py
28. modules/plugins/__init__.py          — plugin registry/router
29. modules/human_assist.py
30. modules/notification_agent.py
31. modules/analytics.py
32. modules/learning_engine.py
33. main.py                              — wire everything together
34. .github/workflows/career_bot.yml    — deploy to Actions
```

---

## 16. Key Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| LinkedIn/Naukri blocks scraper | High | Random delays + realistic user agents + rotate sessions |
| Gemini rate limit (14 RPM free tier) | Medium | Built-in rate limiter in gemini_client.py |
| Workday CAPTCHA | High | Auto-trigger human_assist, don't fight it |
| GitHub Actions timeout (60 min) | Low | Set per-source job limits in settings.json |
| Supabase free tier (500MB) | Low | Only store structured data, not raw JD text for old jobs |
| Applying to same job twice | High | job_exists() check before every application |
| Wrong resume sent | Medium | Log every application with resume_variant to Supabase |

---

*End of Master Build Document*
*Version 1.0 — Local test first, GitHub Actions after 2-day validation*
