"""
Diagnostic script to check Redis queues and task status.
Run: python tests/check_redis_queues.py
"""
import redis
import json
import os

# Standalone - no project imports needed
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')

# Task IDs from the stuck jobs (hardcoded for quick check)
STUCK_TASK_IDS = [
    ("a8637c4f-beba-4c55-8429-bb2b7890f6fa", "d57c3cef-48ac-4722-bc25-df87e4589032", "Kidscamp Bahasa"),
    ("af709817-d25a-4738-bf7a-9b934a131ad0", "28fd4eab-bdf8-40d6-901a-cba69e2c4cb6", "Hoopla Halloween"),
    ("b5bf88ee-6054-4a9d-8761-98eb2a96e279", "033c26d7-7c79-4742-a174-3ce65aa5a029", "Hooplakidz Bahasa"),
    ("15c9315e-cc90-4e46-b673-af01d8070706", "32807a03-f27d-4b57-b80a-d0e6fc08f971", "Kent French"),
    ("de56fce9-1919-409e-b628-89d5ae037770", "5593f705-b34a-4482-a5dc-4c149c65c9d2", "GO GO BUS"),
    ("8aa43efa-18c4-4c24-80a5-0ee57bdff24d", "39f46d95-30e0-4627-92dc-7dd477eb3dea", "GO GO BUS"),
    ("c051caa2-ee69-4912-8faf-ac12bbab976a", "5dd4e99d-2ee5-4ad3-bae9-e68dff115b80", "Hoopla Halloween"),
    ("e96a9830-47bb-4d5d-ab0c-05070c9a93d8", "2f7a3ef7-1b70-4b3e-a6a9-510b28cf0660", "Hoopla Halloween"),
]

def check_redis_queues():
    """Check what's in the Celery queues."""
    print("=" * 60)
    print("REDIS QUEUE DIAGNOSTICS")
    print("=" * 60)

    # Connect to Redis
    r = redis.from_url(REDIS_URL)

    # Check connection
    try:
        r.ping()
        print(f"[OK] Connected to Redis: {REDIS_URL}")
    except Exception as e:
        print(f"[ERROR] Cannot connect to Redis: {e}")
        return

    print()

    # List all keys
    print("--- All Keys in Redis ---")
    all_keys = r.keys("*")
    print(f"  Total keys: {len(all_keys)}")
    for key in sorted([k.decode() for k in all_keys])[:20]:
        key_type = r.type(key).decode()
        if key_type == 'list':
            length = r.llen(key)
            print(f"  {key} (list, {length} items)")
        elif key_type == 'set':
            length = r.scard(key)
            print(f"  {key} (set, {length} items)")
        elif key_type == 'string':
            print(f"  {key} (string)")
        else:
            print(f"  {key} ({key_type})")
    if len(all_keys) > 20:
        print(f"  ... and {len(all_keys) - 20} more keys")

    print()

    # Check specific queues
    queues = ['default_queue', 'gpu_queue', '4k_queue', 'celery']
    print("--- Queue Lengths ---")
    for queue in queues:
        length = r.llen(queue)
        print(f"  {queue}: {length} tasks")

    print()

    # Check stuck task IDs
    print("--- Stuck Task Status ---")
    for job_id, task_id, channel in STUCK_TASK_IDS:
        task_key = f"celery-task-meta-{task_id}"
        exists = r.exists(task_key)
        if exists:
            data = r.get(task_key)
            try:
                parsed = json.loads(data)
                status = parsed.get('status', 'unknown')
                print(f"  {channel[:20]:<20} | EXISTS | status: {status}")
            except:
                print(f"  {channel[:20]:<20} | EXISTS | (cannot parse)")
        else:
            print(f"  {channel[:20]:<20} | MISSING from Redis")

    print()

    # Check if tasks are in any queue
    print("--- Tasks in Queues ---")
    for queue in queues:
        tasks = r.lrange(queue, 0, -1)
        if tasks:
            print(f"  {queue}:")
            for task_data in tasks[:3]:
                try:
                    task = json.loads(task_data)
                    headers = task.get('headers', {})
                    task_id = headers.get('id', 'unknown')
                    print(f"    - {task_id}")
                except:
                    print(f"    - (cannot parse)")
            if len(tasks) > 3:
                print(f"    ... and {len(tasks) - 3} more")

    print()
    print("=" * 60)

if __name__ == "__main__":
    check_redis_queues()
