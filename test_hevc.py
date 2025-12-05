#!/usr/bin/env python3
"""
HEVC (H.265) vs H.264 Encoding Speed Comparison
Tests if HEVC NVENC is faster on newer GPUs
"""

import subprocess
import time
import sys
from pathlib import Path
from datetime import datetime

TEST_DIR = Path(__file__).parent / "test_gpu"

def get_gpu_info():
    """Get GPU name and PCIe info"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,driver_version,pcie.link.gen.current,pcie.link.width.current,power.limit',
             '--format=csv,noheader'],
            capture_output=True, text=True, timeout=10
        )
        parts = [p.strip() for p in result.stdout.strip().split(',')]
        return {
            'name': parts[0] if len(parts) > 0 else 'Unknown',
            'driver': parts[1] if len(parts) > 1 else 'Unknown',
            'pcie_gen': parts[2] if len(parts) > 2 else '?',
            'pcie_width': parts[3] if len(parts) > 3 else '?',
            'power_limit': parts[4] if len(parts) > 4 else '?'
        }
    except:
        return {'name': 'Unknown GPU', 'driver': '?', 'pcie_gen': '?', 'pcie_width': '?', 'power_limit': '?'}

def check_encoders():
    """Check available encoders"""
    result = subprocess.run(['ffmpeg', '-hide_banner', '-encoders'], capture_output=True, text=True)
    encoders = {
        'h264_nvenc': 'h264_nvenc' in result.stdout,
        'hevc_nvenc': 'hevc_nvenc' in result.stdout,
        'av1_nvenc': 'av1_nvenc' in result.stdout,
    }
    return encoders

def run_encode_test(input_file, encoder, preset='p3', duration=30):
    """Run encoding test and return speed"""

    if encoder == 'h264_nvenc':
        codec_params = ['-c:v', 'h264_nvenc', '-preset', preset, '-rc', 'vbr', '-cq', '23']
    elif encoder == 'hevc_nvenc':
        codec_params = ['-c:v', 'hevc_nvenc', '-preset', preset, '-rc', 'vbr', '-cq', '23']
    elif encoder == 'av1_nvenc':
        codec_params = ['-c:v', 'av1_nvenc', '-preset', preset, '-cq', '23']
    else:
        return None

    cmd = [
        'ffmpeg', '-y',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-t', str(duration),
        '-i', str(input_file),
        *codec_params,
        '-an',  # No audio for speed test
        '-f', 'null', '-'
    ]

    print(f"  Testing {encoder} preset={preset}...")
    start = time.time()

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        elapsed = time.time() - start

        # Parse speed from output
        import re
        speed_match = re.search(r'speed=\s*([\d.]+)x', result.stderr)
        speed = float(speed_match.group(1)) if speed_match else None

        return {
            'success': result.returncode == 0,
            'elapsed': round(elapsed, 2),
            'speed': speed,
            'encoder': encoder,
            'preset': preset
        }
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': 'timeout'}
    except Exception as e:
        return {'success': False, 'error': str(e)}

def main():
    print("=" * 70)
    print("HEVC vs H.264 NVENC SPEED COMPARISON")
    print("=" * 70)

    # GPU info
    gpu_info = get_gpu_info()
    print(f"\nGPU: {gpu_info['name']}")
    print(f"Driver: {gpu_info['driver']}")
    print(f"PCIe: Gen {gpu_info['pcie_gen']} x{gpu_info['pcie_width']}")
    print(f"Power Limit: {gpu_info['power_limit']}W")

    # PCIe warning
    if gpu_info['pcie_gen'] == '1':
        print("\n⚠️  WARNING: PCIe running at Gen 1 - severely limited bandwidth!")

    # Check encoders
    print("\nChecking available encoders...")
    encoders = check_encoders()
    for enc, available in encoders.items():
        status = "✓ Available" if available else "✗ Not available"
        print(f"  {enc}: {status}")

    # Find test video
    videos = list(TEST_DIR.glob("*.mp4"))
    if not videos:
        print(f"\nERROR: No test videos in {TEST_DIR}")
        return

    test_video = videos[0]
    print(f"\nTest video: {test_video.name}")
    print(f"Testing first 30 seconds for speed comparison...\n")

    results = []

    # Test H.264
    if encoders['h264_nvenc']:
        print("\n--- H.264 (h264_nvenc) ---")
        for preset in ['p1', 'p3', 'p5']:
            result = run_encode_test(test_video, 'h264_nvenc', preset)
            if result:
                results.append(result)
                if result['success']:
                    print(f"    {preset}: {result['elapsed']}s, {result['speed']}x realtime")
                else:
                    print(f"    {preset}: FAILED")

    # Test HEVC
    if encoders['hevc_nvenc']:
        print("\n--- HEVC (hevc_nvenc) ---")
        for preset in ['p1', 'p3', 'p5']:
            result = run_encode_test(test_video, 'hevc_nvenc', preset)
            if result:
                results.append(result)
                if result['success']:
                    print(f"    {preset}: {result['elapsed']}s, {result['speed']}x realtime")
                else:
                    print(f"    {preset}: FAILED")

    # Test AV1 (RTX 40+ series only)
    if encoders['av1_nvenc']:
        print("\n--- AV1 (av1_nvenc) ---")
        for preset in ['p1', 'p4']:  # AV1 has different preset range
            result = run_encode_test(test_video, 'av1_nvenc', preset)
            if result:
                results.append(result)
                if result['success']:
                    print(f"    {preset}: {result['elapsed']}s, {result['speed']}x realtime")
                else:
                    print(f"    {preset}: FAILED - {result.get('error', 'unknown')}")

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"\nGPU: {gpu_info['name']}")
    print(f"PCIe: Gen {gpu_info['pcie_gen']} x{gpu_info['pcie_width']}")
    print(f"\n{'Encoder':<15} {'Preset':<8} {'Time':<10} {'Speed':<10}")
    print("-" * 50)

    for r in results:
        if r['success']:
            print(f"{r['encoder']:<15} {r['preset']:<8} {r['elapsed']:<10}s {r['speed']}x")

    # Compare H.264 vs HEVC at p3
    h264_p3 = next((r for r in results if r['encoder'] == 'h264_nvenc' and r['preset'] == 'p3' and r['success']), None)
    hevc_p3 = next((r for r in results if r['encoder'] == 'hevc_nvenc' and r['preset'] == 'p3' and r['success']), None)

    if h264_p3 and hevc_p3:
        print(f"\n--- Comparison at p3 preset ---")
        print(f"H.264: {h264_p3['speed']}x realtime")
        print(f"HEVC:  {hevc_p3['speed']}x realtime")

        if h264_p3['speed'] and hevc_p3['speed']:
            ratio = h264_p3['speed'] / hevc_p3['speed']
            print(f"\nH.264 is {ratio:.2f}x faster than HEVC")
            print("(HEVC is more complex but produces smaller files at same quality)")

    print("\n" + "=" * 70)

if __name__ == '__main__':
    main()
