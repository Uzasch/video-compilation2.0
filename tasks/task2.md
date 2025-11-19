# Task 2: Supabase Database Setup

## Objective
Create and configure all Supabase tables, enable real-time subscriptions, and set up row-level security.

**Note**: We use Supabase Auth (`auth.users`) + custom `profiles` table for future-proofing. Authentication can be enabled/enhanced later.

---

## 1. Create Supabase Project

1. Go to https://supabase.com
2. Create new project: `ybh-video-compilation`
3. **Disable email confirmation** (for simple login now):
   - Go to Authentication → Settings
   - Uncheck "Enable email confirmations"
4. Note down:
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
-- PROFILES TABLE (Links to auth.users)
-- ============================================================================
CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  username TEXT UNIQUE NOT NULL,
  display_name TEXT,
  role TEXT DEFAULT 'user' CHECK (role IN ('user', 'admin')),
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Auto-create profile when auth user is created
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO profiles (id, username, display_name, role)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'username', split_part(NEW.email, '@', 1)),
    COALESCE(NEW.raw_user_meta_data->>'display_name', split_part(NEW.email, '@', 1)),
    COALESCE(NEW.raw_user_meta_data->>'role', 'user')
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- ============================================================================
-- JOBS TABLE
-- ============================================================================
CREATE TABLE jobs (
  job_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  user_id UUID REFERENCES profiles(id),
  channel_name TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued', 'processing', 'completed', 'failed', 'cancelled')),
  progress INTEGER DEFAULT 0 CHECK (progress >= 0 AND progress <= 100),
  progress_message TEXT,   -- Current processing step (e.g., "Copying files (3/10)", "Processing video: 2m 15s / 10m 30s")

  -- Default logo (from channel, used to populate all videos initially)
  default_logo_path TEXT,

  -- Features
  enable_4k BOOLEAN DEFAULT false,

  -- Results
  output_path TEXT,
  final_duration FLOAT,
  error_message TEXT,

  -- Production move
  production_path TEXT,
  moved_to_production BOOLEAN DEFAULT false,
  production_moved_at TIMESTAMPTZ,

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
-- JOB ITEMS TABLE (Unified: intro, videos, transitions, outro, images)
-- ============================================================================
CREATE TABLE job_items (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID REFERENCES jobs(job_id) ON DELETE CASCADE,

  -- Position in sequence (determines order: 1, 2, 3...)
  position INTEGER NOT NULL,

  -- Item type
  item_type TEXT NOT NULL CHECK (item_type IN ('intro', 'video', 'transition', 'outro', 'image')),

  -- For videos
  video_id TEXT,           -- YouTube ID or BigQuery ID
  title TEXT,              -- Fetched from BigQuery video_title column OR user-provided for images

  -- Path (for all types)
  path TEXT,
  path_available BOOLEAN DEFAULT false,  -- True if file exists and verified

  -- Per-video logo (each video can have different logo)
  logo_path TEXT,

  -- Metadata
  duration FLOAT,          -- Video duration OR user-specified display time for images
  resolution TEXT,
  is_4k BOOLEAN DEFAULT false,

  -- Per-video text animation
  text_animation_words TEXT[],  -- Only for videos, can be different per video

  -- Processing
  filters TEXT,

  created_at TIMESTAMPTZ DEFAULT NOW(),

  UNIQUE(job_id, position)
);

-- Indexes for job_items
CREATE INDEX idx_job_items_job_id ON job_items(job_id);
CREATE INDEX idx_job_items_position ON job_items(job_id, position);
CREATE INDEX idx_job_items_type ON job_items(job_id, item_type);

-- ============================================================================
-- COMPILATION HISTORY TABLE
-- ============================================================================
CREATE TABLE compilation_history (
  id BIGSERIAL PRIMARY KEY,
  job_id UUID REFERENCES jobs(job_id),
  user_id UUID REFERENCES profiles(id),
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
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE compilation_history ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- PROFILES TABLE POLICIES
-- ============================================================================

-- Users can read all profiles (for user dropdown)
CREATE POLICY "Users can view all profiles"
  ON profiles FOR SELECT
  USING (true);

-- Only admins can update user roles
CREATE POLICY "Admins can update profiles"
  ON profiles FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM profiles
      WHERE profiles.id = auth.uid()
      AND profiles.role = 'admin'
    )
  );

-- ============================================================================
-- JOBS TABLE POLICIES
-- ============================================================================

-- Users can view their own jobs
CREATE POLICY "Users can view own jobs"
  ON jobs FOR SELECT
  USING (user_id = auth.uid() OR
         EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'));

-- Users can create jobs
CREATE POLICY "Users can create jobs"
  ON jobs FOR INSERT
  WITH CHECK (user_id = auth.uid());

-- Users can update their own jobs (for cancellation)
CREATE POLICY "Users can update own jobs"
  ON jobs FOR UPDATE
  USING (user_id = auth.uid() OR
         EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'));

-- Service role can update any job (for workers)
-- This will be handled via service_role key from backend

-- ============================================================================
-- JOB ITEMS POLICIES
-- ============================================================================

CREATE POLICY "Users can view job items for their jobs"
  ON job_items FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.job_id = job_items.job_id
      AND (jobs.user_id = auth.uid() OR
           EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'))
    )
  );

CREATE POLICY "Users can insert job items for their jobs"
  ON job_items FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.job_id = job_items.job_id
      AND jobs.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can update job items for their jobs"
  ON job_items FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.job_id = job_items.job_id
      AND jobs.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete job items for their jobs"
  ON job_items FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM jobs
      WHERE jobs.job_id = job_items.job_id
      AND jobs.user_id = auth.uid()
    )
  );

-- ============================================================================
-- COMPILATION HISTORY POLICIES
-- ============================================================================

CREATE POLICY "Users can view own history"
  ON compilation_history FOR SELECT
  USING (user_id = auth.uid() OR
         EXISTS (SELECT 1 FROM profiles WHERE profiles.id = auth.uid() AND profiles.role = 'admin'));

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

## 5. Create Initial Users (Via Supabase Auth)

**Option A: Via Supabase Dashboard**
1. Go to Authentication → Users → Add User
2. Email: `admin@local.dev`
3. Password: `admin123`
4. Auto Confirm User: ✅ (check this)
5. User Metadata (click "Add field"):
```json
{
  "username": "admin",
  "display_name": "Administrator",
  "role": "admin"
}
```

**Option B: Via SQL (using admin API)**
```sql
-- Note: This requires service_role key in backend
-- Create admin user programmatically from backend later
```

**Verify profile was created:**
```sql
SELECT * FROM profiles;
-- Should see profile auto-created by trigger
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

-- Check profiles
SELECT * FROM profiles;

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
