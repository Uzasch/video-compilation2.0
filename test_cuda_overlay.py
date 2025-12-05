#!/usr/bin/env python3
"""
CUDA vs CPU Overlay Benchmark
Tests different FFmpeg filter approaches to find the fastest method for PNG overlay.

Compares:
1. CPU filters (current approach) - scale, pad, overlay on CPU
2. CUDA filters - scale_cuda, pad_cuda, overlay_cuda on GPU
3. Hybrid approach - GPU decode, CPU overlay, GPU encode

This helps determine if CUDA filters can bypass PCIe bottleneck.
"""

import subprocess
import time
import json
import os
from pathlib import Path
from datetime import datetime

# Test configuration
TEST_GPU_DIR = Path(r"C:\Users\uzair\softwares\video-compilation-2.0\test_gpu")
OUTPUT_DIR = TEST_GPU_DIR / "cuda_test_output"
RESULTS_DIR = Path(r"C:\Users\uzair\softwares\video-compilation-2.0\test_gpu\test_results")

# Find test files
VIDEO_FILE = TEST_GPU_DIR / "ABC_OS_Fivezombiesjumpinginthemiddleofthenight_nyv-26Sep-2025-15-28-59.mp4"
OVERLAY_PNG = TEST_GPU_DIR / "ABC_English.png"

# Target resolution
TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080


def get_gpu_info():
    """Get GPU name and PCIe info"""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,driver_version,pcie.link.gen.current,pcie.link.width.current',
             '--format=csv,noheader'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(', ')
            return {
                'name': parts[0] if len(parts) > 0 else 'Unknown',
                'driver': parts[1] if len(parts) > 1 else 'Unknown',
                'pcie_gen': parts[2] if len(parts) > 2 else 'Unknown',
                'pcie_width': parts[3] if len(parts) > 3 else 'Unknown'
            }
    except Exception as e:
        print(f"Error getting GPU info: {e}")
    return {'name': 'Unknown', 'driver': 'Unknown', 'pcie_gen': 'Unknown', 'pcie_width': 'Unknown'}


def run_ffmpeg_test(name: str, cmd: list, output_file: str) -> dict:
    """Run an FFmpeg command and measure performance"""
    print(f"\n{'='*60}")
    print(f"TEST: {name}")
    print(f"{'='*60}")
    print(f"Command: {' '.join(cmd)}")

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600  # 10 minute timeout
        )
        elapsed = time.time() - start_time

        # Parse speed from FFmpeg output
        speed = None
        for line in result.stderr.split('\n'):
            if 'speed=' in line:
                try:
                    speed_str = line.split('speed=')[1].split()[0].replace('x', '')
                    speed = float(speed_str)
                except:
                    pass

        success = result.returncode == 0

        # Check output file size
        output_size = 0
        if success and os.path.exists(output_file):
            output_size = os.path.getsize(output_file) / (1024 * 1024)  # MB

        print(f"  Result: {'SUCCESS' if success else 'FAILED'}")
        print(f"  Time: {elapsed:.2f}s")
        if speed:
            print(f"  Speed: {speed}x realtime")
        print(f"  Output: {output_size:.2f} MB")

        if not success:
            print(f"  Error: {result.stderr[-500:]}")

        return {
            'name': name,
            'success': success,
            'elapsed_seconds': round(elapsed, 2),
            'speed': speed,
            'output_size_mb': round(output_size, 2),
            'return_code': result.returncode
        }

    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after 600s")
        return {
            'name': name,
            'success': False,
            'elapsed_seconds': 600,
            'speed': None,
            'error': 'timeout'
        }
    except Exception as e:
        print(f"  ERROR: {e}")
        return {
            'name': name,
            'success': False,
            'error': str(e)
        }


def test_cpu_overlay():
    """Test 1: Current CPU-based approach (no hwaccel)"""
    output = str(OUTPUT_DIR / "test_cpu_overlay.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,'
        f'pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black[base];'
        f'[1:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}[logo];'
        f'[base][logo]overlay=(W-w)/2:(H-h)/2',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_ffmpeg_test("CPU Filters + GPU Encode", cmd, output)


def test_cpu_overlay_with_hwaccel_decode():
    """Test 2: GPU decode, CPU filters, GPU encode"""
    output = str(OUTPUT_DIR / "test_hybrid_overlay.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-hwaccel', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,'
        f'pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black[base];'
        f'[1:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}[logo];'
        f'[base][logo]overlay=(W-w)/2:(H-h)/2',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_ffmpeg_test("GPU Decode + CPU Filters + GPU Encode", cmd, output)


def test_cuda_overlay_simple():
    """Test 3: Full CUDA pipeline with overlay_cuda"""
    output = str(OUTPUT_DIR / "test_cuda_overlay_simple.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        # Scale video on GPU, download for overlay (overlay_cuda needs matching formats)
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12[base];'
        f'[1:v]format=nv12,hwupload[logo];'
        f'[base][logo]overlay_cuda=(W-w)/2:(H-h)/2',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_ffmpeg_test("Full CUDA Pipeline (overlay_cuda)", cmd, output)


def test_cuda_scale_cpu_overlay():
    """Test 4: CUDA scale, download, CPU overlay, GPU encode"""
    output = str(OUTPUT_DIR / "test_cuda_scale_cpu_overlay.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12,hwdownload,format=nv12[base];'
        f'[1:v]scale={TARGET_WIDTH}:{TARGET_HEIGHT}[logo];'
        f'[base][logo]overlay=(W-w)/2:(H-h)/2',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_ffmpeg_test("CUDA Scale + CPU Overlay + GPU Encode", cmd, output)


def test_cuda_full_gpu_no_overlay():
    """Test 5: Full GPU pipeline WITHOUT overlay (baseline)"""
    output = str(OUTPUT_DIR / "test_cuda_no_overlay.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-vf', f'scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_ffmpeg_test("Full GPU (no overlay - baseline)", cmd, output)


def test_cuda_overlay_with_pad():
    """Test 6: Full CUDA with scale, pad, and overlay"""
    output = str(OUTPUT_DIR / "test_cuda_full_pipeline.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        # Try pad_cuda if available, otherwise this may fail
        f'[0:v]scale_cuda=w={TARGET_WIDTH}:h={TARGET_HEIGHT}:force_original_aspect_ratio=decrease:format=nv12,'
        f'pad_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2[base];'
        f'[1:v]format=nv12,hwupload[logo];'
        f'[base][logo]overlay_cuda=(W-w)/2:(H-h)/2',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_ffmpeg_test("Full CUDA with pad_cuda + overlay_cuda", cmd, output)


def test_npp_scale_overlay():
    """Test 7: NPP-based scaling (alternative CUDA library)"""
    output = str(OUTPUT_DIR / "test_npp_overlay.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale_npp={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12[base];'
        f'[1:v]format=nv12,hwupload[logo];'
        f'[base][logo]overlay_cuda=(W-w)/2:(H-h)/2',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_ffmpeg_test("NPP Scale + overlay_cuda", cmd, output)


def main():
    print("="*70)
    print("CUDA vs CPU OVERLAY BENCHMARK")
    print("="*70)

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # Get system info
    gpu_info = get_gpu_info()
    print(f"\nGPU: {gpu_info['name']}")
    print(f"Driver: {gpu_info['driver']}")
    print(f"PCIe: Gen {gpu_info['pcie_gen']} x{gpu_info['pcie_width']}")
    print(f"\nVideo: {VIDEO_FILE.name}")
    print(f"Overlay: {OVERLAY_PNG.name}")
    print(f"Target: {TARGET_WIDTH}x{TARGET_HEIGHT}")

    # Run tests
    results = {
        'timestamp': datetime.now().isoformat(),
        'gpu_info': gpu_info,
        'video_file': str(VIDEO_FILE),
        'overlay_file': str(OVERLAY_PNG),
        'target_resolution': f'{TARGET_WIDTH}x{TARGET_HEIGHT}',
        'tests': []
    }

    # Test 5: Baseline (no overlay)
    results['tests'].append(test_cuda_full_gpu_no_overlay())

    # Test 1: Current CPU approach
    results['tests'].append(test_cpu_overlay())

    # Test 2: Hybrid (GPU decode, CPU filters)
    results['tests'].append(test_cpu_overlay_with_hwaccel_decode())

    # Test 4: CUDA scale, CPU overlay
    results['tests'].append(test_cuda_scale_cpu_overlay())

    # Test 3: Full CUDA overlay
    results['tests'].append(test_cuda_overlay_simple())

    # Test 6: Full CUDA with pad
    results['tests'].append(test_cuda_overlay_with_pad())

    # Test 7: NPP scale
    results['tests'].append(test_npp_scale_overlay())

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"\n{'Test':<45} {'Time':>10} {'Speed':>10} {'Status':>10}")
    print("-"*75)

    for test in results['tests']:
        status = "OK" if test.get('success') else "FAILED"
        time_str = f"{test.get('elapsed_seconds', 0):.1f}s"
        speed_str = f"{test.get('speed', 0):.2f}x" if test.get('speed') else "N/A"
        print(f"{test['name']:<45} {time_str:>10} {speed_str:>10} {status:>10}")

    # Find best result
    successful = [t for t in results['tests'] if t.get('success') and t.get('speed')]
    if successful:
        best = max(successful, key=lambda x: x['speed'])
        baseline = next((t for t in results['tests'] if 'baseline' in t['name'].lower()), None)

        print(f"\nBest overlay method: {best['name']}")
        print(f"  Speed: {best['speed']}x realtime")
        if baseline and baseline.get('speed'):
            overhead = ((baseline['speed'] / best['speed']) - 1) * 100
            print(f"  Overhead vs no-overlay: {overhead:.1f}%")

    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    json_file = RESULTS_DIR / f"cuda_overlay_benchmark_{timestamp}.json"
    with open(json_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {json_file}")


if __name__ == '__main__':
    main()
