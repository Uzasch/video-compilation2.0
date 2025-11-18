# Task 2: Supabase Database Setup

## Objective
Create and configure all Supabase tables, enable real-time subscriptions, and set up row-level security.

---

## 1. Create Supabase Project

1. Go to https://supabase.com
2. Create new project: `ybh-video-compilation`
3. Note down:
   - Project URL
   - Anon/Public key
   - Service role key (for backend)

---

## 2. Create Database Tables

Go to Supabase Dashboard → SQL Editor → New Query

### Execute this SQL:

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- USERS TABLE
-- ============================================================================
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  username TEXT UNIQUE NOT NULL,
  display_name TEXT,
  role TEXT DEFAULT 'user' CHECK (role IN ('user', 'admin')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default admin user
INSERT INTO users (username, display_name, role) VALUES
  ('admin', 'Administrator', 'admin');

-- ============================================================================
-- JOBS TABLE
-- ============================================================================
CREATE TABLE jobs (
  job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES users(id),
  channel_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled')),
  progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),

  -- Job configuration
  has_intro BOOLEAN DEFAULT false,
  has_end_packaging BOOLEAN DEFAULT false,
  has_logo BOOLEAN DEFAULT false,

  -- Features
  enable_4k BOOLEAN DEFAULT false,
  text_animation_enabled BOOLEAN DEFAULT false,
  text_animation_words TEXT[], -- Array of words for animation

  -- Results
  output_path TEXT,
  final_duration FLOAT,
  error_message TEXT,

  -- Worker info
  worker_id TEXT,
  queue_name TEXT,

  -- Timestamps
  created_at TIMESTAMPTZ DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,

  -- Metadata (for extensibility)
  metadata JSONB DEFAULT '{}'::jsonb
);

-- Indexes for jobs table
CREATE INDEX idx_jobs_user_id ON jobs(user_id);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX idx_jobs_channel_name ON jobs(channel_name);

-- ============================================================================
-- JOB VIDEOS TABLE
-- ============================================================================
CREATE TABLE job_videos (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID REFERENCES jobs(job_id) ON DELETE CASCADE,

  -- Video identification
  video_id TEXT,
  video_path TEXT,

  -- Position in compilation
  position INTEGER NOT NULL,

  -- Video metadata
  duration FLOAT,
  resolution TEXT,
  is_4k BOOLEAN DEFAULT false,

  -- Processing
  filters TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(job_id, position)
);

-- Indexes for job_videos
CREATE INDEX idx_job_videos_job_id ON job_videos(job_id);
CREATE INDEX idx_job_videos_position ON job_videos(job_id, position);

-- ============================================================================
-- JOB PACKAGING INSERTS TABLE
-- ============================================================================
CREATE TABLE job_packaging_inserts (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID REFERENCES jobs(job_id) ON DELETE CASCADE,

  -- Insert position (after which video position)
  insert_after_position INTEGER NOT NULL,

  -- Packaging video
  packaging_video_id TEXT,
  packaging_video_path TEXT,
  packaging_name TEXT,

  duration FLOAT,

  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for packaging inserts
CREATE INDEX idx_packaging_job_id ON job_packaging_inserts(job_id);

-- ============================================================================
-- COMPILATION HISTORY TABLE
-- ============================================================================
CREATE TABLE compilation_history (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID REFERENCES jobs(job_id),
  user_id UUID REFERENCES users(id),
  channel_name TEXT,

  video_count INTEGER,
  total_duration FLOAT,
  output_filename TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for compilation_history
CREATE INDEX idx_history_user_channel ON compilation_history(user_id, channel_name);
CREATE INDEX idx_history_created_at ON compilation_history(created_at DESC);
CREATE INDEX idx_history_user_id ON compilation_history(user_id);

-- ============================================================================
-- ENABLE REAL-TIME FOR JOBS TABLE
-- ============================================================================
ALTER PUBLICATION supabase_realtime ADD TABLE jobs;
```

---

## 3. Set Up Row-Level Security (RLS)

```sql
-- Enable RLS on all tables
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_videos ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_packaging_inserts ENABLE ROW LEVEL SECURITY;
ALTER TABLE compilation_history ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- USERS TABLE POLICIES
-- ============================================================================

-- Users can read their own data
CREATE POLICY "Users can view own data"
  ON users FOR SELECT
  USING (true);  -- Allow all authenticated users to view

-- Only admins can update user roles
CREATE POLICY "Admins can update users"
  ON users FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM users
      WHERE users.id = auth.uid()
      AND users.role = 'admin'
    )
  );

-- ============================================================================
-- JOBS TABLE POLICIES
-- ============================================================================

-- Users can view their own jobs
CREATE POLICY "Users can view own jobs"
  ON jobs FOR SELECT
  USING (user_id = auth.uid() OR
         EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.role = 'admin'));

-- Users can create jobs
CREATE POLICY "Users can create jobs"
  ON jobs FOR INSERT
  WITH CHECK (user_id = auth.uid());

-- Users can update their own jobs (for cancellation)
CREATE POLICY "Users can update own jobs"
  ON jobs FOR UPDATE
  USING (user_id = auth.uid() OR
         EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.role = 'admin'));

-- Service role can update any job (for workers)
-- This will be handled via service_role key from backend

-- ============================================================================
-- JOB VIDEOS POLICIES
-- ============================================================================

CREATE POLICY "Users can view job videos for their jobs"
  ON job_videos FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.job_id = job_videos.job_id
      AND (jobs.user_id = auth.uid() OR
           EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.role = 'admin'))
    )
  );

CREATE POLICY "Users can insert job videos for their jobs"
  ON job_videos FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.job_id = job_videos.job_id
      AND jobs.user_id = auth.uid()
    )
  );

-- ============================================================================
-- PACKAGING INSERTS POLICIES
-- ============================================================================

CREATE POLICY "Users can view packaging for their jobs"
  ON job_packaging_inserts FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.job_id = job_packaging_inserts.job_id
      AND (jobs.user_id = auth.uid() OR
           EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.role = 'admin'))
    )
  );

CREATE POLICY "Users can insert packaging for their jobs"
  ON job_packaging_inserts FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.job_id = job_packaging_inserts.job_id
      AND jobs.user_id = auth.uid()
    )
  );

-- ============================================================================
-- COMPILATION HISTORY POLICIES
-- ============================================================================

CREATE POLICY "Users can view own history"
  ON compilation_history FOR SELECT
  USING (user_id = auth.uid() OR
         EXISTS (SELECT 1 FROM users WHERE users.id = auth.uid() AND users.role = 'admin'));

CREATE POLICY "Users can insert own history"
  ON compilation_history FOR INSERT
  WITH CHECK (user_id = auth.uid());
```

---

## 4. Create Helper Functions

```sql
-- Function to automatically insert into compilation_history when job completes
CREATE OR REPLACE FUNCTION insert_compilation_history()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
    INSERT INTO compilation_history (
      job_id,
      user_id,
      channel_name,
      video_count,
      total_duration,
      output_filename
    )
    SELECT
      NEW.job_id,
      NEW.user_id,
      NEW.channel_name,
      (SELECT COUNT(*) FROM job_videos WHERE job_id = NEW.job_id),
      NEW.final_duration,
      substring(NEW.output_path from '[^/\\]+$')  -- Extract filename from path
    WHERE NOT EXISTS (
      SELECT 1 FROM compilation_history WHERE job_id = NEW.job_id
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-insert into history
CREATE TRIGGER trigger_insert_compilation_history
  AFTER UPDATE ON jobs
  FOR EACH ROW
  EXECUTE FUNCTION insert_compilation_history();
```

---

## 5. Test Data (Optional)

```sql
-- Insert test user
INSERT INTO users (username, display_name, role) VALUES
  ('uzair', 'Uzair', 'admin'),
  ('testuser', 'Test User', 'user');

-- Insert test job
INSERT INTO jobs (user_id, channel_name, status, progress)
SELECT id, 'TestChannel', 'queued', 0
FROM users WHERE username = 'uzair'
LIMIT 1;
```

---

## 6. Verify Setup

Run these queries to verify:

```sql
-- Check tables exist
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Check users
SELECT * FROM users;

-- Check RLS is enabled
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public';

-- Test real-time is enabled
SELECT schemaname, tablename
FROM pg_publication_tables
WHERE pubname = 'supabase_realtime';
```

---

## 7. Get Connection Details

1. Go to Supabase Dashboard → Settings → API
2. Copy:
   - **Project URL**: `https://xxxxx.supabase.co`
   - **anon public key**: For frontend
   - **service_role key**: For backend (keep secret!)

3. Update your `.env` files:

**Backend `.env`:**
```env
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=your-service-role-key
```

**Frontend `.env`:**
```env
VITE_SUPABASE_URL=https://xxxxx.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

---

## Checklist

- [ ] Supabase project created
- [ ] All tables created successfully
- [ ] Indexes created
- [ ] Real-time enabled for jobs table
- [ ] RLS policies set up
- [ ] Helper functions and triggers created
- [ ] Test data inserted (optional)
- [ ] Connection details noted and added to `.env`
- [ ] Verified tables exist with SQL query
- [ ] Verified RLS is enabled

---

## Next: Task 3
Build FastAPI backend structure and authentication endpoints.
