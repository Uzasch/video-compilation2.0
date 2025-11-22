"""
Test script to submit a compilation job via the API
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

print("\n[ITEMS]")
for item in verify_data['items']:
    status = "[OK]" if item.get('path_available') else "[FAIL]"
    print(f"   {status} {item['position']}. {item['item_type']}: {item.get('title', 'N/A')}")
    if item.get('duration'):
        print(f"      Duration: {item['duration']:.2f}s, Resolution: {item.get('resolution')}, 4K: {item.get('is_4k')}")

print("\n" + "=" * 60)
print("STEP 2: Submit compilation job")
print("=" * 60)

# Prepare submit payload
submit_payload = {
    "user_id": USER_ID,
    "channel_name": "HooplaKidz Toon",
    "enable_4k": False,  # Set to True if you want 4K output
    "items": verify_data['items']
}

print(f"\n[SUBMIT] Submitting job...")
print(f"   Videos: {len(video_ids)}")
print(f"   4K: {submit_payload['enable_4k']}")
print(f"   Expected queue: {'default_queue' if not submit_payload['enable_4k'] or len(video_ids) <= 20 else '4k_queue'}")

submit_response = requests.post(SUBMIT_URL, json=submit_payload)

if submit_response.status_code != 200:
    print(f"[FAIL] Submit failed: {submit_response.status_code}")
    print(submit_response.text)
    exit(1)

submit_data = submit_response.json()
job_id = submit_data['job_id']

print(f"[OK] Job submitted successfully!")
print(f"   Job ID: {job_id}")
print(f"   Status: {submit_data['status']}")

print("\n" + "=" * 60)
print("STEP 3: Monitor job progress")
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
            print(f"[{timestamp}] Status: {status:12s} | Progress: {progress:3d}%", end="")

            if job_status.get('worker_id'):
                print(f" | Worker: {job_status['worker_id']}", end="")
            if job_status.get('queue_name'):
                print(f" | Queue: {job_status['queue_name']}", end="")

            print()  # New line
            last_progress = progress

        # Check if job finished
        if status in ['completed', 'failed']:
            print(f"\n{'='*60}")
            print(f"JOB {status.upper()}!")
            print(f"{'='*60}")

            if status == 'completed':
                print(f"[OUTPUT] {job_status.get('output_path')}")
                print(f"   Duration: {job_status.get('final_duration'):.2f}s")
                if job_status.get('completed_at'):
                    print(f"   Completed: {job_status['completed_at']}")
            else:
                print(f"[ERROR] {job_status.get('error_message', 'Unknown error')}")

            break

        time.sleep(5)

    except KeyboardInterrupt:
        print(f"\n\n[STOPPED] Monitoring stopped by user")
        print(f"   Job {job_id} is still running")
        print(f"   Check status at: {STATUS_URL}")
        break
    except Exception as e:
        print(f"[ERROR] Error polling status: {e}")
        time.sleep(5)

print(f"\n[DONE] Test complete!")
