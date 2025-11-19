# Queue Statistics Feature

## Overview
Added queue position tracking so users can see where their jobs are in the processing queue.

---

## Backend Changes (task4.md)

### New Endpoint: `GET /api/jobs/queue/stats`

Returns queue statistics for the current user:

```json
{
  "total_in_queue": 5,
  "active_workers": 3,
  "user_jobs": [
    {
      "job_id": "abc-123",
      "channel_name": "YBH",
      "queue_position": 1,
      "is_processing": true,
      "status": "processing",
      "waiting_count": 0
    },
    {
      "job_id": "def-456",
      "channel_name": "Tech",
      "queue_position": 4,
      "is_processing": false,
      "status": "queued",
      "waiting_count": 1
    }
  ],
  "available_slots": 0
}
```

**How it works:**
1. Fetches all jobs with status `queued` or `processing`
2. Orders by `created_at` (FIFO queue)
3. Calculates position for each job (1-indexed)
4. Jobs with position ≤ active_workers (3) are processing
5. Jobs with position > 3 are waiting

---

## Frontend Changes (task7.md)

### Dashboard - Queue Statistics Card

New visual card showing:

```
┌─────────────────────────────────────────────────────┐
│ Queue Status                   ● 3 workers active   │
│                                  5 total in queue   │
├─────────────────────────────────────────────────────┤
│  #1  YBH           🔄 Processing now    [View →]    │
│  #4  Tech          1 job ahead          [View →]    │
└─────────────────────────────────────────────────────┘

✓ 0 workers available
```

**Features:**
- **Auto-refresh**: Updates every 5 seconds
- **Position badges**:
  - Green (#1-3): Processing now
  - Amber (#4+): Waiting
- **Waiting count**: Shows how many jobs are ahead
- **Available slots**: Shows if workers are free
- **Direct navigation**: Click to view job details

**Visual States:**

1. **Processing** (position ≤ 3):
   - Green badge with spinning loader icon
   - Text: "Processing now"

2. **Next in queue** (position = 4):
   - Amber badge
   - Text: "Next in queue"

3. **Waiting** (position > 4):
   - Amber badge
   - Text: "N jobs ahead" (e.g., "2 jobs ahead")

4. **Available slots** (total < 3):
   - Green success message
   - "✓ N worker(s) available - your next job will start immediately!"

---

## Use Cases

### Scenario 1: User submits multiple compilations

```
User submits 3 jobs at 10:00, 10:05, 10:10

Queue at 10:10:
┌──────────────────────────────────────────┐
│ #1  YBH (Job A)   🔄 Processing now     │
│ #2  Tech (Job B)  🔄 Processing now     │
│ #3  YBH (Job C)   🔄 Processing now     │
└──────────────────────────────────────────┘

All 3 workers busy, 0 available slots
```

### Scenario 2: User has jobs waiting

```
5 jobs total in queue, user has 2 jobs:

Queue:
┌──────────────────────────────────────────┐
│ #2  Tech          🔄 Processing now     │
│ #5  YBH           2 jobs ahead          │
└──────────────────────────────────────────┘

User's job #5 will start when jobs #3 and #4 complete
```

### Scenario 3: Workers available

```
1 job in queue, user submits new job:

Before submit:
┌──────────────────────────────────────────┐
│ #1  YBH           🔄 Processing now     │
└──────────────────────────────────────────┘

✓ 2 workers available - your next job will start immediately!

After submit (new job):
┌──────────────────────────────────────────┐
│ #1  YBH (old)     🔄 Processing now     │
│ #2  Tech (new)    🔄 Processing now     │
└──────────────────────────────────────────┘
```

---

## History Viewing

Users can view previous compilations through:

### Dashboard
Shows **active** jobs only:
- Queued jobs
- Processing jobs
- Recently completed (until removed from active view)

### History Page (Task 8)
Shows **all completed** compilations:
- Filterable by channel, date range
- Shows output filename, video count, duration
- Links to job details
- Auto-populated via database trigger when job completes

---

## Database Flow

```
Submit Job (T=0)
    ↓
INSERT into jobs (status='queued')
INSERT into job_items (all items)
    ↓
Queue Celery task
    ↓
─────────────────────────────────────────
Worker picks up (T=5)
    ↓
UPDATE jobs (status='processing')
    ↓
[Processing... updates every few seconds]
    ↓
UPDATE jobs (status='completed')
    ↓
TRIGGER: Auto-insert into compilation_history
```

**Queue stats endpoint:**
- Queries jobs table for status IN ('queued', 'processing')
- Orders by created_at ASC
- Returns position for user's jobs only
- No data is modified

---

## Summary

✅ **Queue Position**: Users see their place in line (#1, #2, #3...)
✅ **Processing Status**: Clear indicator of which jobs are processing vs waiting
✅ **Waiting Count**: Shows how many jobs are ahead
✅ **Real-time Updates**: Auto-refresh every 5 seconds
✅ **Available Slots**: Shows when workers are free
✅ **Multiple Jobs**: Users can track multiple submissions simultaneously
✅ **History Access**: Dedicated History page for viewing past compilations (Task 8)

Users always know:
- Where their job is in the queue
- Whether it's processing or waiting
- How long until it starts (approximate)
- When workers become available
