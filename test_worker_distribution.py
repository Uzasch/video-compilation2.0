"""
Quick test to verify job distribution between PC1 and PC2 workers
"""
import requests
import time

BASE_URL = "http://localhost:8000/api/jobs"
USER_ID = "e6dc178a-545c-483b-999a-dcc86480d962"

# Use valid video IDs from temp.txt
VIDEO_IDS = [
    "AnB45678912",
    "AnB45678913"
]

def submit_job(job_num):
    """Submit a single job"""
    # Verify first
    verify_response = requests.post(
        f"{BASE_URL}/verify",
        params={"user_id": USER_ID},
        json={
            "channel_name": f"TestChannel_{job_num}",
            "video_ids": VIDEO_IDS,
            "manual_paths": []
        }
    )

    if verify_response.status_code != 200:
        print(f"Job {job_num}: Verify failed - {verify_response.text}")
        return None

    verify_data = verify_response.json()

    # Submit job - user_id in body
    submit_response = requests.post(
        f"{BASE_URL}/submit",
        json={
            "user_id": USER_ID,
            "channel_name": f"TestChannel_{job_num}",
            "items": verify_data["items"],
            "enable_4k": False
        }
    )

    if submit_response.status_code != 200:
        print(f"Job {job_num}: Submit failed - {submit_response.text}")
        return None

    job_data = submit_response.json()
    print(f"Job {job_num}: Submitted - {job_data['job_id']}")
    return job_data['job_id']

def check_job_status(job_id):
    """Check job status"""
    response = requests.get(f"{BASE_URL}/{job_id}")
    if response.status_code == 200:
        return response.json()
    return None

def main():
    print("=" * 60)
    print("WORKER DISTRIBUTION TEST")
    print("=" * 60)
    print(f"PC1: gpu_queue, 4k_queue, default_queue")
    print(f"PC2: default_queue only")
    print("=" * 60)

    # Submit 4 jobs quickly to test load balancing
    print("\n[1] Submitting 4 jobs simultaneously...")
    job_ids = []

    # Submit all jobs as fast as possible
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(submit_job, i) for i in range(1, 5)]
        for future in futures:
            job_id = future.result()
            if job_id:
                job_ids.append(job_id)

    if len(job_ids) < 4:
        print(f"Only submitted {len(job_ids)} jobs")
        if len(job_ids) == 0:
            return

    print(f"\n[2] Monitoring jobs...")
    print("-" * 60)

    # Monitor for 5 minutes (4 jobs)
    start_time = time.time()
    completed = set()

    while len(completed) < len(job_ids) and (time.time() - start_time) < 300:
        for job_id in job_ids:
            if job_id in completed:
                continue

            status = check_job_status(job_id)
            if status:
                job_status = status.get('status', 'unknown')
                progress = status.get('progress', 0)
                worker = status.get('worker_id', 'pending')

                if job_status == 'processing':
                    print(f"  {job_id[:8]}: {job_status} ({progress}%) - Worker: {worker}")
                elif job_status == 'completed':
                    print(f"  {job_id[:8]}: COMPLETED - Worker: {worker}")
                    completed.add(job_id)
                elif job_status == 'failed':
                    print(f"  {job_id[:8]}: FAILED - {status.get('error_message', 'unknown')}")
                    completed.add(job_id)

        time.sleep(3)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    workers_used = set()
    for job_id in job_ids:
        status = check_job_status(job_id)
        if status:
            worker = status.get('worker_id', 'unknown')
            workers_used.add(worker)
            print(f"Job {job_id[:8]}: Worker = {worker}")

    print(f"\nWorkers used: {workers_used}")
    if len(workers_used) == 2:
        print("SUCCESS: Jobs distributed to both workers!")
    elif len(workers_used) == 1:
        print("NOTE: Both jobs went to same worker (one may have been faster)")
    else:
        print("WARNING: Could not determine worker distribution")

if __name__ == "__main__":
    main()
