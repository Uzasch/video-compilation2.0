"""
Test the full video copying process inside Docker
Usage: docker exec video-compilation-backend python /app/test_full_copy_in_docker.py
"""
from services.storage import copy_file_sequential, normalize_paths
from services.bigquery import get_videos_info_by_ids
from utils.video_utils import get_video_info
from pathlib import Path
import shutil

# Video IDs from temp.txt
VIDEO_IDS = [
    "1b9AcqPFTz8",
    "J2htsBo8WgA",
    "-Vpx09PpcNU",
    "B9GD1SFd6BM",
    "6PKp0yVRsY8",
    "uv11tjZ3avk",
    "XmS8jjTj3-Q",
    "hYgcXAAAOdg",
    "uRYHXRKUDy8",
    "zvovneG6AFQ"
]

CHANNEL_NAME = "HooplaKidz Toon"

print("="*80)
print("FULL VIDEO COPY PROCESS TEST (Inside Docker)")
print("="*80)
print(f"Channel: {CHANNEL_NAME}")
print(f"Video Count: {len(VIDEO_IDS)}")

# ============================================================================
# STEP 1: Get video paths from BigQuery
# ============================================================================
print("\n[STEP 1] Fetching video paths from BigQuery")
print("-"*80)

videos_info = get_videos_info_by_ids(VIDEO_IDS)

if not videos_info:
    print("  [FAIL] No video paths found in BigQuery")
    exit(1)

print(f"  [OK] Found {len(videos_info)} video paths")

# Show sample paths
for idx, (video_id, info) in enumerate(list(videos_info.items())[:2], 1):
    print(f"\n  Sample {idx}:")
    print(f"    Video ID: {video_id}")
    print(f"    Title: {info['title'][:60]}")
    print(f"    Path: {info['path'][:80]}...")

# ============================================================================
# STEP 2: Copy videos to temp directory
# ============================================================================
print("\n[STEP 2] Copying videos to temp directory")
print("-"*80)

test_job_id = "test-copy-hooplakidz"
temp_base = Path("/app/temp") / test_job_id

print(f"  Creating temp directory: {temp_base}")
temp_base.mkdir(parents=True, exist_ok=True)

# Copy first 3 videos as a test
videos_to_copy = list(videos_info.items())[:3]

print(f"\n  Copying {len(videos_to_copy)} videos...\n")

successful_copies = 0
failed_copies = 0
copy_results = []

for idx, (video_id, info) in enumerate(videos_to_copy, 1):
    source_path = info['path']
    dest_filename = f"video_{idx:03d}.mp4"

    print(f"  [{idx}/{len(videos_to_copy)}] Copying: {video_id}")
    print(f"      Title: {info['title'][:60]}")
    print(f"      Source: {source_path[:80]}...")

    try:
        result_path = copy_file_sequential(
            source_path=source_path,
            dest_dir=str(temp_base),
            dest_filename=dest_filename,
            use_optimal_method=True
        )

        if result_path and Path(result_path).exists():
            file_size = Path(result_path).stat().st_size / (1024 * 1024)  # MB
            print(f"      [OK] Copied successfully ({file_size:.2f} MB)")
            successful_copies += 1
            copy_results.append({
                'video_id': video_id,
                'path': result_path,
                'size_mb': file_size
            })
        else:
            print(f"      [FAIL] Copy returned None or file doesn't exist")
            failed_copies += 1

    except Exception as e:
        print(f"      [FAIL] Copy error: {e}")
        failed_copies += 1

    print()

# Summary
print("="*80)
print("Copy Summary:")
print(f"  [OK] Successful: {successful_copies}/{len(videos_to_copy)}")
print(f"  [FAIL] Failed: {failed_copies}/{len(videos_to_copy)}")
print("="*80)

# ============================================================================
# STEP 3: Verify copied files with ffprobe
# ============================================================================
if successful_copies > 0:
    print("\n[STEP 3] Verifying copied files with ffprobe")
    print("-"*80)

    for result in copy_results:
        video_id = result['video_id']
        file_path = result['path']

        print(f"\n  Checking: {Path(file_path).name}")
        print(f"    Video ID: {video_id}")

        try:
            info = get_video_info(file_path)

            if info:
                print(f"    [OK] Valid video file")
                print(f"    Duration: {info['duration_seconds']:.2f}s")
                print(f"    Resolution: {info['width']}x{info['height']}")
                print(f"    Is 4K: {info['is_4k']}")
            else:
                print(f"    [FAIL] Invalid video file (ffprobe failed)")

        except Exception as e:
            print(f"    [FAIL] Verification error: {e}")

# ============================================================================
# STEP 4: Show temp directory contents
# ============================================================================
print("\n[STEP 4] Temp directory contents")
print("-"*80)

if temp_base.exists():
    files = list(temp_base.glob("*.mp4"))
    print(f"  Found {len(files)} files in {temp_base}:\n")

    total_size = 0
    for f in files:
        size_mb = f.stat().st_size / (1024 * 1024)
        total_size += size_mb
        print(f"    - {f.name}: {size_mb:.2f} MB")

    print(f"\n  Total size: {total_size:.2f} MB")

# ============================================================================
# STEP 5: Cleanup
# ============================================================================
print("\n[STEP 5] Cleanup test files")
print("-"*80)

try:
    if temp_base.exists():
        print(f"  Removing: {temp_base}")
        shutil.rmtree(temp_base)
        print("  [OK] Temp directory cleaned up")
except Exception as e:
    print(f"  [FAIL] Cleanup error: {e}")

print("\n" + "="*80)
print("TEST COMPLETED")
print("="*80)
print(f"[OK] Successfully copied and verified {successful_copies} videos!")
