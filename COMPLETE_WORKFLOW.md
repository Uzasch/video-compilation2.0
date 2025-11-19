# Complete Workflow: Video Compilation System

This document shows the complete user journey from start to finish.

---

## 3-Step Workflow Overview

### **Step 1: Build Initial Sequence from Video IDs**
User enters video IDs → Backend fetches from BigQuery → Returns sequence

### **Step 2: Edit & Verify Paths**
User edits sequence → Adds transitions/images → Verifies all paths exist

### **Step 3: Submit Job**
All paths available → Submit to queue → Worker processes

---

## Detailed Workflow

### Step 1: Build Initial Sequence

**User Actions:**
1. Selects channel: "YBH"
2. Pastes video IDs (one per line):
   ```
   TJU5wYdTG4c
   ABC123XYZ
   DEF456GHI
   ```
3. Clicks **"Verify & Build Sequence"**

**Backend Process (`POST /api/jobs/verify`):**
1. Fetch channel branding from BigQuery `branding_assets`:
   - intro_path
   - outro_path
   - logo_path
2. For each video_id, fetch from BigQuery `path` table:
   - video_path
   - video_title
3. Check if files exist (preliminary check)
4. Build sequence: intro → videos → outro

**Response:**
```json
{
  "default_logo_path": "\\SERVER\\branding\\ybh\\logo.png",
  "total_duration": 625.3,
  "items": [
    {
      "position": 1,
      "item_type": "intro",
      "title": "Intro",
      "path": "\\SERVER\\branding\\ybh\\intro.mp4",
      "path_available": true,
      "duration": 5.2
    },
    {
      "position": 2,
      "item_type": "video",
      "video_id": "TJU5wYdTG4c",
      "title": "How to Code Python",
      "path": "\\SERVER\\videos\\TJU5wYdTG4c.mp4",
      "path_available": true,
      "logo_path": "\\SERVER\\branding\\ybh\\logo.png",
      "duration": 180.5
    },
    // ... more videos
  ]
}
```

**Frontend Display:**
- Shows sequence editor
- Each item has status badge (✓ Available or ✗ Not Found)

---

### Step 2: Edit Sequence & Verify Paths

**User Actions (Optional):**

#### 2a. Insert Transition
1. Clicks "Insert Transition" after position 2
2. Enters manual path: `\\SERVER\transitions\subscribe.mp4`
3. Positions 3-5 shift to 4-6

#### 2b. Upload Image
1. Clicks "Insert Image" after position 4
2. Uploads `promo.png`
3. Sets duration: 7.5 seconds
4. Sets title: "Special Promo"
5. Image inserted at position 5

#### 2c. Fix Missing Path
1. Video at position 3 shows "✗ Not Found"
2. User enters manual path: `\\CUSTOM\backup\video.mp4`
3. Status changes to "⚠ Not Verified"

#### 2d. Change Logo
1. Expands video at position 2
2. Changes logo to custom: `\\CUSTOM\my_logo.png`
3. Clicks "Apply to All Videos" (or not)

#### 2e. Add Text Animation
1. Expands video at position 4
2. Enters words: "Subscribe, Now, Click, Bell"

**Updated Sequence:**
```
Position 1: Intro
Position 2: Video (TJU5wYdTG4c) - custom logo
Position 3: Video (ABC123XYZ) - fixed path
Position 4: Transition (manual path)
Position 5: Image (uploaded) - 7.5s
Position 6: Video (DEF456GHI) - text animation
Position 7: Outro
```

**User Clicks: "Verify & Process"**

**Backend Process (`POST /api/jobs/verify-paths`):**
1. For each item in sequence:
   - Check if path exists on server
   - Get duration (for videos/transitions/intro/outro)
   - Set path_available: true or false
2. Return updated items with durations

**Response:**
```json
{
  "items": [
    {
      "position": 1,
      "item_type": "intro",
      "path": "\\SERVER\\branding\\ybh\\intro.mp4",
      "path_available": true,
      "duration": 5.2
    },
    {
      "position": 2,
      "item_type": "video",
      "video_id": "TJU5wYdTG4c",
      "path": "\\SERVER\\videos\\TJU5wYdTG4c.mp4",
      "path_available": true,
      "logo_path": "\\CUSTOM\\my_logo.png",
      "duration": 180.5
    },
    {
      "position": 3,
      "item_type": "video",
      "video_id": "ABC123XYZ",
      "path": "\\CUSTOM\\backup\\video.mp4",
      "path_available": true,  // ✓ Now verified!
      "duration": 240.3
    },
    {
      "position": 4,
      "item_type": "transition",
      "path": "\\SERVER\\transitions\\subscribe.mp4",
      "path_available": true,
      "duration": 10.0
    },
    {
      "position": 5,
      "item_type": "image",
      "path": "C:\\uploads\\images\\promo.png",
      "path_available": true,
      "duration": 7.5  // User-specified
    },
    {
      "position": 6,
      "item_type": "video",
      "video_id": "DEF456GHI",
      "path": "\\SERVER\\videos\\DEF456GHI.mp4",
      "path_available": true,
      "text_animation_words": ["Subscribe", "Now", "Click", "Bell"],
      "duration": 191.2
    },
    {
      "position": 7,
      "item_type": "outro",
      "path": "\\SERVER\\branding\\ybh\\outro.mp4",
      "path_available": true,
      "duration": 8.1
    }
  ],
  "all_valid": true,
  "missing_count": 0,
  "total_duration": 642.8
}
```

**Frontend Updates:**
- All items show "✓ Available" badge
- Total duration updated: 642.8 seconds (10m 42s)
- Green message: "✓ All paths verified and available!"
- "Submit Compilation" button enabled

---

### Step 3: Submit Job

**User Clicks: "Submit Compilation"**

**Backend Process (`POST /api/jobs/submit`):**

1. **Validate all paths:**
   ```python
   if any(not item.path_available for item in items):
       raise HTTPException(400, "Cannot submit. Fix missing paths first")
   ```

2. **Insert into `jobs` table:**
   ```sql
   INSERT INTO jobs (
     job_id, user_id, channel_name, status, progress,
     enable_4k, default_logo_path, final_duration,
     moved_to_production
   ) VALUES (
     'xyz-789-abc',
     '550e8400...',
     'YBH',
     'queued',
     0,
     false,
     '\\SERVER\\branding\\ybh\\logo.png',
     642.8,
     false
   );
   ```

3. **Insert into `job_items` table (7 rows):**
   ```sql
   INSERT INTO job_items (
     job_id, position, item_type, video_id, title,
     path, logo_path, duration, text_animation_words
   ) VALUES
     ('xyz-789-abc', 1, 'intro', NULL, 'Intro', '\\SERVER\\branding\\ybh\\intro.mp4', NULL, 5.2, NULL),
     ('xyz-789-abc', 2, 'video', 'TJU5wYdTG4c', 'How to Code Python', '\\SERVER\\videos\\TJU5wYdTG4c.mp4', '\\CUSTOM\\my_logo.png', 180.5, []),
     ('xyz-789-abc', 3, 'video', 'ABC123XYZ', 'JavaScript Tutorial', '\\CUSTOM\\backup\\video.mp4', '\\SERVER\\branding\\ybh\\logo.png', 240.3, []),
     ('xyz-789-abc', 4, 'transition', NULL, NULL, '\\SERVER\\transitions\\subscribe.mp4', NULL, 10.0, NULL),
     ('xyz-789-abc', 5, 'image', NULL, 'Special Promo', 'C:\\uploads\\images\\promo.png', NULL, 7.5, NULL),
     ('xyz-789-abc', 6, 'video', 'DEF456GHI', 'React Basics', '\\SERVER\\videos\\DEF456GHI.mp4', '\\SERVER\\branding\\ybh\\logo.png', 191.2, ['Subscribe','Now','Click','Bell']),
     ('xyz-789-abc', 7, 'outro', NULL, 'Outro', '\\SERVER\\branding\\ybh\\outro.mp4', NULL, 8.1, NULL);
   ```

4. **Queue Celery task:**
   ```python
   from workers.tasks import process_compilation
   queue = '4k_queue' if enable_4k else 'default_queue'
   process_compilation.apply_async(args=['xyz-789-abc'], queue=queue)
   ```

**Response:**
```json
{
  "job_id": "xyz-789-abc",
  "status": "queued"
}
```

**Frontend:**
- Redirects to `/compilation/xyz-789-abc`
- Shows job details page with real-time progress

---

## Worker Processing

### Stage 1: Copy Source Files (0-20%)

```python
# Worker fetches items from database
items = supabase.table('job_items').select('*').eq('job_id', job_id).order('position').execute()

# Copy each file to temp
for i, item in enumerate(items.data):
    local_path = copy_from_smb(item['path'])

    # Update progress
    progress = int((i + 1) / len(items.data) * 20)
    supabase.table('jobs').update({
        'progress': progress,
        'progress_message': f'Copying source files ({i+1}/{len(items.data)})'
    }).eq('job_id', job_id).execute()
```

### Stage 2: Build FFmpeg Command (20-25%)

```python
supabase.table('jobs').update({
    'progress': 20,
    'progress_message': 'Building FFmpeg command'
}).eq('job_id', job_id).execute()

# Build command with all items
ffmpeg_cmd = build_unified_compilation_command(
    job_items=items.data,
    output_path=temp_output,
    enable_4k=job['enable_4k']
)
```

### Stage 3: Process with FFmpeg (25-95%)

```python
supabase.table('jobs').update({
    'progress': 25,
    'progress_message': 'Processing video compilation'
}).eq('job_id', job_id).execute()

# Run FFmpeg with progress parsing
run_ffmpeg_with_progress(
    cmd=ffmpeg_cmd,
    job_id=job_id,
    total_duration=642.8,
    progress_offset=25,
    progress_range=70
)
```

**FFmpeg processes:**
- Intro (5.2s)
- Video 1 with custom logo overlay (180.5s)
- Video 2 with default logo (240.3s)
- Transition (10.0s)
- Image converted to 7.5s video segment with silent audio
- Video 3 with logo + text animation (191.2s)
- Outro (8.1s)

**Real-time updates:**
```
progress: 25, message: "Processing video: 0m 0s / 10m 42s"
progress: 30, message: "Processing video: 0m 30s / 10m 42s"
progress: 50, message: "Processing video: 3m 15s / 10m 42s"
progress: 70, message: "Processing video: 6m 30s / 10m 42s"
progress: 90, message: "Processing video: 9m 45s / 10m 42s"
```

### Stage 4: Copy Output (95-100%)

```python
supabase.table('jobs').update({
    'progress': 95,
    'progress_message': 'Copying output file to server'
}).eq('job_id', job_id).execute()

final_path = copy_to_output_location(temp_output)

# Job complete
supabase.table('jobs').update({
    'status': 'completed',
    'progress': 100,
    'progress_message': 'Compilation complete',
    'output_path': final_path,
    'completed_at': datetime.utcnow().isoformat()
}).eq('job_id', job_id).execute()
```

**Auto-insert into `compilation_history`:**
```sql
INSERT INTO compilation_history (
  job_id, user_id, channel_name,
  video_count, total_duration, output_filename
) VALUES (
  'xyz-789-abc',
  '550e8400...',
  'YBH',
  3,  -- Only count actual videos (not intro/outro/transitions/images)
  642.8,
  'ybh_temp_output.mp4'
);
```

---

## Move to Production (Optional)

**User Reviews Completed Video**

**User Clicks: "Move to Production"**

**Optional: Enter custom filename**
```
Input: "My Awesome Compilation"
```

**Backend (`POST /api/jobs/xyz-789-abc/move-to-production`):**

1. **Sanitize filename:**
   ```
   "My Awesome Compilation" → "my_awesome_compilation"
   ```

2. **Generate production filename:**
   ```
   ybh_2025-01-18_143022.mp4
   ```

3. **Copy file:**
   ```
   FROM: C:\temp\xyz-789-abc_output.mp4
   TO:   \\SERVER\production\ybh\my_awesome_compilation.mp4
   ```

4. **Update database:**
   ```sql
   UPDATE jobs
   SET
     production_path = '\\SERVER\production\ybh\my_awesome_compilation.mp4',
     moved_to_production = true,
     production_moved_at = '2025-01-18 14:30:22'
   WHERE job_id = 'xyz-789-abc';
   ```

**Response:**
```json
{
  "success": true,
  "production_path": "\\\\SERVER\\production\\ybh\\my_awesome_compilation.mp4",
  "filename": "my_awesome_compilation.mp4"
}
```

---

## Final Database State

### `jobs` Table

| job_id | user_id | channel_name | status | progress | progress_message | enable_4k | output_path | final_duration | production_path | moved_to_production |
|--------|---------|--------------|--------|----------|------------------|-----------|-------------|----------------|-----------------|---------------------|
| xyz-789-abc | 550e8400... | YBH | completed | 100 | Compilation complete | false | C:\temp\xyz-789-abc_output.mp4 | 642.8 | \\\\SERVER\\production\\ybh\\my_awesome_compilation.mp4 | **true** |

### `job_items` Table (7 rows)

| id | job_id | position | item_type | video_id | path | logo_path | duration | text_animation_words |
|----|--------|----------|-----------|----------|------|-----------|----------|---------------------|
| 1 | xyz-789-abc | 1 | intro | NULL | \\\\SERVER\\branding\\ybh\\intro.mp4 | NULL | 5.2 | NULL |
| 2 | xyz-789-abc | 2 | video | TJU5wYdTG4c | \\\\SERVER\\videos\\TJU5wYdTG4c.mp4 | \\\\CUSTOM\\my_logo.png | 180.5 | [] |
| 3 | xyz-789-abc | 3 | video | ABC123XYZ | \\\\CUSTOM\\backup\\video.mp4 | \\\\SERVER\\branding\\ybh\\logo.png | 240.3 | [] |
| 4 | xyz-789-abc | 4 | transition | NULL | \\\\SERVER\\transitions\\subscribe.mp4 | NULL | 10.0 | NULL |
| 5 | xyz-789-abc | 5 | image | NULL | C:\\uploads\\images\\promo.png | NULL | 7.5 | NULL |
| 6 | xyz-789-abc | 6 | video | DEF456GHI | \\\\SERVER\\videos\\DEF456GHI.mp4 | \\\\SERVER\\branding\\ybh\\logo.png | 191.2 | ["Subscribe","Now","Click","Bell"] |
| 7 | xyz-789-abc | 7 | outro | NULL | \\\\SERVER\\branding\\ybh\\outro.mp4 | NULL | 8.1 | NULL |

### `compilation_history` Table

| id | job_id | user_id | channel_name | video_count | total_duration | output_filename | created_at |
|----|--------|---------|--------------|-------------|----------------|----------------|------------|
| 1 | xyz-789-abc | 550e8400... | YBH | 3 | 642.8 | my_awesome_compilation.mp4 | 2025-01-18 14:30:22 |

---

## Summary: Path Availability Flow

### Initial Verify (Step 1)
```
BigQuery lookup → path_available: true or false
Returns in API response only (not saved to DB at this stage)
```

### User Edits (Step 2)
```
Manual path entered → path_available: false (not yet verified)
Image uploaded → path_available: true (file just uploaded)
```

### Verify Paths (Step 2)
```
Check all files exist:
  - Found → path_available: true + duration retrieved
  - Not found → path_available: false + error message
Returns in API response only (not saved to DB)
```

### Submit (Step 3)
```
All items must have path_available: true
Otherwise → Error: "Cannot submit. Fix missing paths first"
Note: path_available is NOT saved to job_items table
```

---

## Key Features Demonstrated

✅ **Unified sequence**: intro, videos, transitions, images, outro all in one table
✅ **Flexible paths**: BigQuery lookup OR manual entry OR uploaded files
✅ **Per-video customization**: logos, text animation different for each video
✅ **Path verification**: Two-step process ensures all files exist before submission
✅ **Real-time progress**: Detailed messages during processing
✅ **Production move**: Sanitized filenames in organized folders
✅ **Duration handling**: Auto-detected for videos, user-specified for images
✅ **Path status tracking**: Clear visual indicators throughout workflow

---

## End of Complete Workflow
