#!/usr/bin/env python3
"""
Quick disk speed test - measure actual read speed
"""

import subprocess
import time
import os
from pathlib import Path

TEST_DIR = Path(__file__).parent / "test_gpu"

def test_raw_disk_read(file_path):
    """Test raw file read speed using Python"""
    file_size = os.path.getsize(file_path)

    print(f"File: {file_path.name}")
    print(f"Size: {file_size / (1024*1024):.1f} MB")

    # Clear file cache (Windows)
    try:
        subprocess.run(['sync'], capture_output=True, timeout=5)
    except:
        pass

    print("\nReading file...")
    start = time.time()

    with open(file_path, 'rb') as f:
        data = f.read()

    elapsed = time.time() - start
    speed_mbps = (file_size / (1024*1024)) / elapsed

    print(f"Read time: {elapsed:.2f}s")
    print(f"Speed: {speed_mbps:.1f} MB/s")

    if speed_mbps < 100:
        print("\n⚠️  WARNING: Very slow read speed!")
        print("   Expected: 500+ MB/s for NVMe")
        print("   Possible issues:")
        print("   - File is on network drive")
        print("   - Antivirus scanning")
        print("   - Disk power saving mode")
    elif speed_mbps < 500:
        print("\n⚠️  WARNING: Slower than expected for NVMe")
    else:
        print("\n✓ Good NVMe speed")

    return speed_mbps

def test_ffmpeg_read(file_path):
    """Test FFmpeg file read speed"""
    print("\n--- FFmpeg decode test ---")

    cmd = ['ffmpeg', '-y', '-i', str(file_path), '-f', 'null', '-']

    start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    elapsed = time.time() - start

    # Get file duration
    probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(file_path)]
    probe_result = subprocess.run(probe_cmd, capture_output=True, text=True)
    duration = float(probe_result.stdout.strip())

    speed = duration / elapsed
    print(f"FFmpeg decode: {elapsed:.2f}s ({speed:.2f}x realtime)")

    return speed

def check_drive_info():
    """Check drive information"""
    print("\n--- Drive Info ---")
    try:
        # Check if path is on network
        result = subprocess.run(['wmic', 'logicaldisk', 'get', 'name,drivetype,description'],
                              capture_output=True, text=True, timeout=10)
        print(result.stdout)
    except:
        pass

def main():
    print("=" * 60)
    print("DISK SPEED TEST")
    print("=" * 60)

    # Find test video
    videos = list(TEST_DIR.glob("*.mp4"))
    if not videos:
        print(f"No videos found in {TEST_DIR}")
        return

    test_file = videos[0]
    print(f"\nTest path: {test_file}")
    print(f"Drive: {test_file.drive}")

    check_drive_info()

    print("\n--- Raw Read Test ---")
    raw_speed = test_raw_disk_read(test_file)

    ffmpeg_speed = test_ffmpeg_read(test_file)

    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Raw disk read: {raw_speed:.1f} MB/s")
    print(f"FFmpeg decode: {ffmpeg_speed:.2f}x realtime")

    if raw_speed > 500 and ffmpeg_speed < 5:
        print("\n⚠️  Disk is fast but FFmpeg is slow")
        print("   CPU decoding might be the bottleneck")
    elif raw_speed < 100:
        print("\n⚠️  Disk read is the bottleneck")

if __name__ == '__main__':
    main()
