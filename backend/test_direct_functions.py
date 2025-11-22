"""
Test remaining functions directly - run inside Docker container
Usage: docker exec video-compilation-backend python /app/test_direct_functions.py
"""
from services.bigquery import get_production_path, insert_compilation_result
from services.storage import copy_file_sequential
from datetime import datetime
from pathlib import Path
import uuid

print("="*70)
print("TESTING REMAINING FUNCTIONS")
print("="*70)

# TEST 1: get_production_path()
print("\n1. Testing get_production_path()...")
try:
    channel_name = "HooplaKidz Toon"
    production_path = get_production_path(channel_name)

    if production_path:
        print(f"   [OK] Production path for '{channel_name}': {production_path}")
    else:
        print(f"   [FAIL] No production path found for '{channel_name}'")
except Exception as e:
    print(f"   [FAIL] Error: {e}")

# TEST 2: insert_compilation_result()
print("\n2. Testing insert_compilation_result()...")
try:
    test_job_data = {
        "job_id": "11111111-1111-1111-1111-111111111111",  # Test job_id (exists in jobs table)
        "user_id": "e6dc178a-545c-483b-999a-dcc86480d962",  # Test user UUID
        "channel_name": "HooplaKidz Toon",
        "video_count": 10,
        "total_duration": 480.5,
        "output_path": "/app/temp/test-job-123/output.mp4"
    }

    result = insert_compilation_result(test_job_data)

    if result:
        print(f"   [OK] Analytics inserted successfully to BigQuery")
        print(f"        Job ID: {test_job_data['job_id']}")
    else:
        print(f"   [FAIL] Failed to insert analytics")
except Exception as e:
    print(f"   [FAIL] Error: {e}")

# TEST 3: copy_file_sequential()
print("\n3. Testing copy_file_sequential()...")
try:
    # Create a test source file
    test_source = Path("/app/temp/test_source_file.txt")
    test_source.parent.mkdir(parents=True, exist_ok=True)
    test_source.write_text("Test content for copy function")

    # Copy to destination
    dest_dir = "/app/temp/test_copy_dest"
    dest_filename = "copied_file.txt"

    result_path = copy_file_sequential(
        source_path=str(test_source),
        dest_dir=dest_dir,
        dest_filename=dest_filename,
        use_optimal_method=True  # Auto-detect OS method (rsync/cp in Docker)
    )

    if result_path and Path(result_path).exists():
        content = Path(result_path).read_text()
        if content == "Test content for copy function":
            print(f"   [OK] File copied successfully: {result_path}")
        else:
            print(f"   [FAIL] File copied but content mismatch")
    else:
        print(f"   [FAIL] Copy failed")

    # Cleanup
    test_source.unlink(missing_ok=True)
    if result_path and Path(result_path).exists():
        Path(result_path).unlink(missing_ok=True)
        Path(dest_dir).rmdir()

except Exception as e:
    print(f"   [FAIL] Error: {e}")

print("\n" + "="*70)
print("TESTS COMPLETED")
print("="*70)
