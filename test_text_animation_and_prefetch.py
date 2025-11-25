"""
Test script to test ASS text animation and prefetch optimization
Submits 2 jobs with text animation to test both features
"""
import requests
import time
import json

# Read video IDs from temp.txt
with open('temp.txt', 'r') as f:
    video_ids = [line.strip() for line in f if line.strip()]

print(f"[VIDEO IDs] {video_ids}")
print(f"[TOTAL] {len(video_ids)} videos\n")

# API endpoints
BASE_URL = "http://localhost:8000/api/jobs"
VERIFY_URL = f"{BASE_URL}/verify"
SUBMIT_URL = f"{BASE_URL}/submit"

# Test user
USER_ID = "e6dc178a-545c-483b-999a-dcc86480d962"

def verify_videos():
    """Verify videos and get metadata"""
    print("=" * 60)
    print("STEP 1: Verify videos and get metadata")
    print("=" * 60)

    verify_payload = {
        "channel_name": "HooplaKidz Toon",
        "video_ids": video_ids,
        "manual_paths": []
    }

    print(f"\n[VERIFY] Sending verify request...")
    verify_response = requests.post(
        VERIFY_URL,
        params={"user_id": USER_ID},
        json=verify_payload
    )

    if verify_response.status_code != 200:
        print(f"[FAIL] Verify failed: {verify_response.status_code}")
        print(verify_response.text)
        exit(1)

    verify_data = verify_response.json()
    print(f"[OK] Verification successful!")
    print(f"   Default logo: {verify_data.get('default_logo_path')}")
    print(f"   Total duration: {verify_data['total_duration']:.2f}s ({verify_data['total_duration']/60:.2f} min)")
    print(f"   Items count: {len(verify_data['items'])}")

    # Check availability
    available_count = sum(1 for item in verify_data['items'] if item.get('path_available'))
    print(f"   Available: {available_count}/{len(verify_data['items'])}")

    if available_count == 0:
        print("[FAIL] No videos available! Check paths.")
        exit(1)

    return verify_data

def add_text_animation_to_items(items):
    """Add text animation to video items"""
    text_animations = [
        "FUNNY MOMENT!",
        "SUBSCRIBE NOW",
        "WATCH MORE",
        "NEW VIDEO",
        "CHECK THIS OUT",
        "AMAZING!"
    ]

    text_index = 0
    for item in items:
        if item['item_type'] == 'video':
            item['text_animation_text'] = text_animations[text_index % len(text_animations)]
            text_index += 1

    return items

def submit_job(job_number, items_with_text):
    """Submit a compilation job"""
    print("\n" + "=" * 60)
    print(f"STEP {job_number + 1}: Submit compilation job #{job_number + 1}")
    print("=" * 60)

    # Prepare submit payload
    submit_payload = {
        "user_id": USER_ID,
        "channel_name": "HooplaKidz Toon",
        "enable_4k": False,
        "items": items_with_text
    }

    print(f"\n[SUBMIT] Submitting job #{job_number + 1}...")
    print(f"   Videos: {len(video_ids)}")
    print(f"   Text Animation: Enabled on all videos")
    print(f"   Expected queue: gpu_queue (text animation enabled)")

    submit_response = requests.post(SUBMIT_URL, json=submit_payload)

    if submit_response.status_code != 200:
        print(f"[FAIL] Submit failed: {submit_response.status_code}")
        print(submit_response.text)
        exit(1)

    submit_data = submit_response.json()
    job_id = submit_data['job_id']

    print(f"[OK] Job #{job_number + 1} submitted successfully!")
    print(f"   Job ID: {job_id}")
    print(f"   Status: {submit_data['status']}")

    return job_id

def monitor_job(job_id, job_number):
    """Monitor a single job"""
    print("\n" + "=" * 60)
    print(f"STEP {job_number + 2}: Monitor job #{job_number + 1} progress")
    print("=" * 60)

    STATUS_URL = f"{BASE_URL}/{job_id}"
    print(f"\n[MONITOR] Polling status every 5 seconds...")
    print(f"   URL: {STATUS_URL}\n")

    last_progress = -1
    while True:
        try:
            status_response = requests.get(STATUS_URL)
            if status_response.status_code != 200:
                print(f"[FAIL] Failed to get status: {status_response.status_code}")
                break

            job_status = status_response.json()
            status = job_status['status']
            progress = job_status.get('progress', 0)

            # Only print if progress changed
            if progress != last_progress:
                timestamp = time.strftime("%H:%M:%S")
                print(f"[{timestamp}] Job #{job_number + 1} | Status: {status:12s} | Progress: {progress:3d}%", end="")

                if job_status.get('worker_id'):
                    print(f" | Worker: {job_status['worker_id']}", end="")
                if job_status.get('queue_name'):
                    print(f" | Queue: {job_status['queue_name']}", end="")

                print()  # New line
                last_progress = progress

            # Check if job finished
            if status in ['completed', 'failed']:
                print(f"\n{'='*60}")
                print(f"JOB #{job_number + 1} {status.upper()}!")
                print(f"{'='*60}")

                if status == 'completed':
                    print(f"[OUTPUT] {job_status.get('output_path')}")
                    print(f"   Duration: {job_status.get('final_duration'):.2f}s")
                    if job_status.get('completed_at'):
                        print(f"   Completed: {job_status['completed_at']}")
                else:
                    print(f"[ERROR] {job_status.get('error_message', 'Unknown error')}")

                return status == 'completed'

            time.sleep(5)

        except KeyboardInterrupt:
            print(f"\n\n[STOPPED] Monitoring stopped by user")
            print(f"   Job {job_id} is still running")
            print(f"   Check status at: {STATUS_URL}")
            return False
        except Exception as e:
            print(f"[ERROR] Error polling status: {e}")
            time.sleep(5)

# Main test flow
print("=" * 60)
print("TEST: Text Animation (ASS) and Prefetch Optimization")
print("=" * 60)
print()
print("This test will:")
print("1. Submit 2 jobs with text animation enabled")
print("2. Monitor job #1 completion")
print("3. Check logs to verify:")
print("   - ASS subtitle files were generated")
print("   - Job #2 files were prefetched during job #1 processing")
print()

# Verify videos once
verify_data = verify_videos()

# Add text animation to items
items_with_text = add_text_animation_to_items(verify_data['items'].copy())

print("\n[TEXT ANIMATION] Added to video items:")
for item in items_with_text:
    if item['item_type'] == 'video' and item.get('text_animation_text'):
        print(f"   Position {item['position']}: \"{item['text_animation_text']}\"")

# Submit both jobs
print("\n" + "=" * 60)
print("SUBMITTING BOTH JOBS")
print("=" * 60)

job_id_1 = submit_job(0, items_with_text)
time.sleep(2)  # Small delay between submissions
job_id_2 = submit_job(1, items_with_text)

print("\n" + "=" * 60)
print("MONITORING JOB #1")
print("=" * 60)
print("\n[NOTE] While job #1 runs, check Celery logs for prefetch messages:")
print("   docker logs video-compilation-celery -f | grep -i prefetch")
print()

# Monitor first job
success = monitor_job(job_id_1, 0)

if success:
    print("\n" + "=" * 60)
    print("VERIFICATION CHECKS")
    print("=" * 60)

    print("\n[CHECK 1] ASS subtitle files:")
    print(f"   Check: logs/*/e6dc178a-545c-483b-999a-dcc86480d962/jobs/*_{job_id_1}.log")
    print("   Look for: 'Text animation ASS file generated'")

    print("\n[CHECK 2] Prefetch optimization:")
    print(f"   Check Celery logs for:")
    print(f"   - 'Next job in queue: {job_id_2}'")
    print(f"   - 'Background prefetch thread started for {job_id_2}'")
    print(f"   - 'Prefetching N files for job {job_id_2}'")
    print(f"   - '✓ Prefetch completed for job {job_id_2}'")

    print("\n[CHECK 3] Job #2 should start faster:")
    print(f"   Monitor job #2 to see if file copying is skipped/faster")

    print("\n" + "=" * 60)
    print("MONITORING JOB #2")
    print("=" * 60)

    # Monitor second job
    monitor_job(job_id_2, 1)

print(f"\n[DONE] Test complete!")
print("\nResults Summary:")
print(f"  Job #1: {job_id_1}")
print(f"  Job #2: {job_id_2}")
