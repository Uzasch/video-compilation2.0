"""
Test the new copy_files_parallel() function
Usage: docker exec video-compilation-backend python /app/test_parallel_copy.py
"""
from services.storage import copy_files_parallel
from services.bigquery import get_videos_info_by_ids
from pathlib import Path
import shutil
import time

# Test video IDs
VIDEO_IDS = [
    "1b9AcqPFTz8",
    "J2htsBo8WgA",
    "-Vpx09PpcNU",
]

CHANNEL_NAME = "HooplaKidz Toon"

print("="*80)
print("TESTING PARALLEL COPY FUNCTION")
print("="*80)

# Get video paths
print("\n1. Fetching video paths from BigQuery...")
videos_info = get_videos_info_by_ids(VIDEO_IDS)

if not videos_info:
    print("  [FAIL] No videos found")
    exit(1)

print(f"  [OK] Found {len(videos_info)} videos")

# Prepare file list for parallel copy
files_to_copy = []
for idx, (video_id, info) in enumerate(videos_info.items(), 1):
    files_to_copy.append({
        'source_path': info['path'],
        'dest_filename': f'video_{idx:03d}.mp4'
    })
    print(f"    - {video_id}: {info['title'][:50]}")

# Test parallel copy
print(f"\n2. Testing parallel copy with {len(files_to_copy)} files...")

dest_dir = "/app/temp/test-parallel-copy"
Path(dest_dir).mkdir(parents=True, exist_ok=True)

start_time = time.time()

results = copy_files_parallel(
    source_files=files_to_copy,
    dest_dir=dest_dir,
    max_workers=5
)

elapsed = time.time() - start_time

# Check results
successful = sum(1 for v in results.values() if v is not None)
failed = len(results) - successful

print(f"\n3. Results:")
print(f"  Time: {elapsed:.2f}s")
print(f"  Successful: {successful}/{len(files_to_copy)}")
print(f"  Failed: {failed}/{len(files_to_copy)}")

# Verify files exist
print(f"\n4. Verifying copied files...")
for dest_filename, result_path in results.items():
    if result_path and Path(result_path).exists():
        size_mb = Path(result_path).stat().st_size / (1024 * 1024)
        print(f"  [OK] {dest_filename}: {size_mb:.2f} MB")
    else:
        print(f"  [FAIL] {dest_filename}: Not found")

# Cleanup
print(f"\n5. Cleaning up...")
if Path(dest_dir).exists():
    shutil.rmtree(dest_dir)
    print(f"  [OK] Removed {dest_dir}")

print("\n" + "="*80)
print(f"TEST COMPLETED - {successful}/{len(files_to_copy)} files copied successfully in {elapsed:.2f}s")
print("="*80)
