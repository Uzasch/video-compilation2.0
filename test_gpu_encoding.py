#!/usr/bin/env python3
"""
GPU Encoding Benchmark Script
Tests NVENC encoding speed with various operations:
- Pure encoding (no filters)
- With PNG overlay
- With text overlay (drawtext)
- With both overlays combined

Compares GPU vs CPU encoding and logs all results.
"""

import subprocess
import time
import os
import sys
import json
from datetime import datetime
from pathlib import Path
import platform
import re

# Configuration
TEST_DIR = Path(__file__).parent / "test_gpu"
OUTPUT_DIR = TEST_DIR
LOG_FILE = OUTPUT_DIR / f"benchmark_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

# Test configurations
PRESETS_GPU = ['p1', 'p3', 'p5', 'p7']  # NVENC presets (p1=fastest, p7=slowest/best quality)
PRESETS_CPU = ['ultrafast', 'fast', 'medium']  # x264 presets

class BenchmarkLogger:
    def __init__(self, log_file):
        self.log_file = log_file
        self.results = []

    def log(self, message, also_print=True):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = f"[{timestamp}] {message}"
        if also_print:
            print(line)
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

    def add_result(self, test_name, data):
        self.results.append({'test': test_name, **data})

    def save_summary(self):
        summary_file = self.log_file.parent / f"benchmark_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(summary_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        self.log(f"Summary saved to: {summary_file}")


def get_system_info():
    """Get system and GPU information"""
    info = {
        'hostname': platform.node(),
        'platform': platform.system(),
        'python': platform.python_version(),
    }

    # Get GPU info via nvidia-smi
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,driver_version,memory.total,pcie.link.gen.current,pcie.link.width.current,clocks.current.graphics,clocks.current.memory,temperature.gpu,power.draw',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(', ')
            if len(parts) >= 9:
                info['gpu_name'] = parts[0]
                info['driver_version'] = parts[1]
                info['gpu_memory_mb'] = parts[2]
                info['pcie_gen'] = parts[3]
                info['pcie_width'] = parts[4]
                info['gpu_clock_mhz'] = parts[5]
                info['mem_clock_mhz'] = parts[6]
                info['gpu_temp_c'] = parts[7]
                info['power_draw_w'] = parts[8]
    except Exception as e:
        info['gpu_error'] = str(e)

    # Get CPU info
    try:
        if platform.system() == 'Windows':
            result = subprocess.run(['wmic', 'cpu', 'get', 'name'], capture_output=True, text=True)
            lines = [l.strip() for l in result.stdout.split('\n') if l.strip() and l.strip() != 'Name']
            if lines:
                info['cpu_name'] = lines[0]
        else:
            with open('/proc/cpuinfo') as f:
                for line in f:
                    if 'model name' in line:
                        info['cpu_name'] = line.split(':')[1].strip()
                        break
    except:
        pass

    return info


def get_video_info(video_path):
    """Get video properties using ffprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,duration,r_frame_rate,codec_name',
            '-show_entries', 'format=duration,size',
            '-of', 'json',
            str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)

        stream = data.get('streams', [{}])[0]
        format_info = data.get('format', {})

        # Parse frame rate
        fps_str = stream.get('r_frame_rate', '30/1')
        if '/' in fps_str:
            num, den = fps_str.split('/')
            fps = float(num) / float(den)
        else:
            fps = float(fps_str)

        return {
            'width': stream.get('width', 0),
            'height': stream.get('height', 0),
            'fps': round(fps, 2),
            'codec': stream.get('codec_name', 'unknown'),
            'duration': float(format_info.get('duration', stream.get('duration', 0))),
            'size_mb': round(int(format_info.get('size', 0)) / (1024*1024), 2)
        }
    except Exception as e:
        return {'error': str(e)}


def run_ffmpeg_benchmark(cmd, description, logger, timeout=300):
    """Run FFmpeg command and measure performance"""
    logger.log(f"Running: {description}")
    logger.log(f"Command: {' '.join(cmd)}")

    start_time = time.time()

    try:
        # Run FFmpeg with stderr captured for progress
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        stdout, stderr = process.communicate(timeout=timeout)
        end_time = time.time()

        elapsed = end_time - start_time

        # Parse FFmpeg output for speed info
        speed_match = re.search(r'speed=\s*([\d.]+)x', stderr)
        fps_match = re.search(r'fps=\s*([\d.]+)', stderr)
        bitrate_match = re.search(r'bitrate=\s*([\d.]+)kbits/s', stderr)

        result = {
            'success': process.returncode == 0,
            'elapsed_seconds': round(elapsed, 2),
            'return_code': process.returncode,
            'speed': float(speed_match.group(1)) if speed_match else None,
            'fps': float(fps_match.group(1)) if fps_match else None,
            'bitrate_kbps': float(bitrate_match.group(1)) if bitrate_match else None,
        }

        if process.returncode != 0:
            result['error'] = stderr[-500:] if len(stderr) > 500 else stderr
            logger.log(f"  ERROR: {result['error']}")
        else:
            logger.log(f"  Elapsed: {elapsed:.2f}s, Speed: {result['speed']}x, FPS: {result['fps']}")

        return result

    except subprocess.TimeoutExpired:
        process.kill()
        logger.log(f"  TIMEOUT after {timeout}s")
        return {'success': False, 'error': 'timeout', 'elapsed_seconds': timeout}
    except Exception as e:
        logger.log(f"  EXCEPTION: {str(e)}")
        return {'success': False, 'error': str(e)}


def create_test_overlay_png(output_path, width=400, height=100):
    """Create a simple test PNG overlay using FFmpeg"""
    cmd = [
        'ffmpeg', '-y', '-f', 'lavfi',
        '-i', f'color=c=red@0.5:size={width}x{height}:d=1',
        '-vframes', '1',
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True)
    return output_path.exists()


def benchmark_pure_encoding(video_path, logger, use_gpu=True, preset='p3'):
    """Test pure encoding speed without filters"""
    output = OUTPUT_DIR / f"test_pure_{'gpu' if use_gpu else 'cpu'}_{preset}.mp4"

    if use_gpu:
        cmd = [
            'ffmpeg', '-y', '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
            '-i', str(video_path),
            '-c:v', 'h264_nvenc',
            '-preset', preset,
            '-rc', 'vbr', '-cq', '23',
            '-maxrate', '9M', '-bufsize', '12M',
            '-c:a', 'copy',
            str(output)
        ]
    else:
        cmd = [
            'ffmpeg', '-y',
            '-i', str(video_path),
            '-c:v', 'libx264',
            '-preset', preset,
            '-crf', '23',
            '-maxrate', '9M', '-bufsize', '12M',
            '-c:a', 'copy',
            str(output)
        ]

    result = run_ffmpeg_benchmark(cmd, f"Pure encoding ({'GPU' if use_gpu else 'CPU'}, preset={preset})", logger)
    result['output_file'] = str(output)
    result['encoder'] = 'h264_nvenc' if use_gpu else 'libx264'
    result['preset'] = preset

    # Get output file size
    if output.exists():
        result['output_size_mb'] = round(output.stat().st_size / (1024*1024), 2)

    return result


def benchmark_with_png_overlay(video_path, overlay_path, logger, use_gpu=True, preset='p3'):
    """Test encoding with PNG overlay"""
    output = OUTPUT_DIR / f"test_overlay_{'gpu' if use_gpu else 'cpu'}_{preset}.mp4"

    if use_gpu:
        # GPU: Need to handle overlay in a way compatible with NVENC
        cmd = [
            'ffmpeg', '-y',
            '-hwaccel', 'cuda',
            '-i', str(video_path),
            '-i', str(overlay_path),
            '-filter_complex', '[0:v][1:v]overlay=10:10',
            '-c:v', 'h264_nvenc',
            '-preset', preset,
            '-rc', 'vbr', '-cq', '23',
            '-maxrate', '9M', '-bufsize', '12M',
            '-c:a', 'copy',
            str(output)
        ]
    else:
        cmd = [
            'ffmpeg', '-y',
            '-i', str(video_path),
            '-i', str(overlay_path),
            '-filter_complex', '[0:v][1:v]overlay=10:10',
            '-c:v', 'libx264',
            '-preset', preset,
            '-crf', '23',
            '-maxrate', '9M', '-bufsize', '12M',
            '-c:a', 'copy',
            str(output)
        ]

    result = run_ffmpeg_benchmark(cmd, f"PNG overlay ({'GPU' if use_gpu else 'CPU'}, preset={preset})", logger)
    result['output_file'] = str(output)
    result['encoder'] = 'h264_nvenc' if use_gpu else 'libx264'
    result['preset'] = preset
    result['filter'] = 'overlay'

    if output.exists():
        result['output_size_mb'] = round(output.stat().st_size / (1024*1024), 2)

    return result


def benchmark_with_text_overlay(video_path, logger, use_gpu=True, preset='p3'):
    """Test encoding with drawtext filter"""
    output = OUTPUT_DIR / f"test_text_{'gpu' if use_gpu else 'cpu'}_{preset}.mp4"

    # Text overlay with timestamp and custom text - use Windows font path
    font_path = "C\\\\:/Windows/Fonts/arial.ttf"
    drawtext = f"drawtext=text='BENCHMARK TEST':fontfile='{font_path}':fontsize=48:fontcolor=white:x=50:y=50:box=1:boxcolor=black@0.5"

    if use_gpu:
        cmd = [
            'ffmpeg', '-y',
            '-hwaccel', 'cuda',
            '-i', str(video_path),
            '-vf', drawtext,
            '-c:v', 'h264_nvenc',
            '-preset', preset,
            '-rc', 'vbr', '-cq', '23',
            '-maxrate', '9M', '-bufsize', '12M',
            '-c:a', 'copy',
            str(output)
        ]
    else:
        cmd = [
            'ffmpeg', '-y',
            '-i', str(video_path),
            '-vf', drawtext,
            '-c:v', 'libx264',
            '-preset', preset,
            '-crf', '23',
            '-maxrate', '9M', '-bufsize', '12M',
            '-c:a', 'copy',
            str(output)
        ]

    result = run_ffmpeg_benchmark(cmd, f"Text overlay ({'GPU' if use_gpu else 'CPU'}, preset={preset})", logger)
    result['output_file'] = str(output)
    result['encoder'] = 'h264_nvenc' if use_gpu else 'libx264'
    result['preset'] = preset
    result['filter'] = 'drawtext'

    if output.exists():
        result['output_size_mb'] = round(output.stat().st_size / (1024*1024), 2)

    return result


def benchmark_combined_filters(video_path, overlay_path, logger, use_gpu=True, preset='p3'):
    """Test encoding with both PNG and text overlay"""
    output = OUTPUT_DIR / f"test_combined_{'gpu' if use_gpu else 'cpu'}_{preset}.mp4"

    # Complex filter: overlay + drawtext - use Windows font path
    font_path = "C\\\\:/Windows/Fonts/arial.ttf"
    filter_complex = f"[0:v][1:v]overlay=10:10,drawtext=text='BENCHMARK TEST':fontfile='{font_path}':fontsize=48:fontcolor=white:x=50:y=150:box=1:boxcolor=black@0.5"

    if use_gpu:
        cmd = [
            'ffmpeg', '-y',
            '-hwaccel', 'cuda',
            '-i', str(video_path),
            '-i', str(overlay_path),
            '-filter_complex', filter_complex,
            '-c:v', 'h264_nvenc',
            '-preset', preset,
            '-rc', 'vbr', '-cq', '23',
            '-maxrate', '9M', '-bufsize', '12M',
            '-c:a', 'copy',
            str(output)
        ]
    else:
        cmd = [
            'ffmpeg', '-y',
            '-i', str(video_path),
            '-i', str(overlay_path),
            '-filter_complex', filter_complex,
            '-c:v', 'libx264',
            '-preset', preset,
            '-crf', '23',
            '-maxrate', '9M', '-bufsize', '12M',
            '-c:a', 'copy',
            str(output)
        ]

    result = run_ffmpeg_benchmark(cmd, f"Combined filters ({'GPU' if use_gpu else 'CPU'}, preset={preset})", logger)
    result['output_file'] = str(output)
    result['encoder'] = 'h264_nvenc' if use_gpu else 'libx264'
    result['preset'] = preset
    result['filter'] = 'overlay+drawtext'

    if output.exists():
        result['output_size_mb'] = round(output.stat().st_size / (1024*1024), 2)

    return result


def benchmark_decoding(video_path, logger, use_gpu=True):
    """Test pure decoding speed"""
    if use_gpu:
        cmd = [
            'ffmpeg', '-y',
            '-hwaccel', 'cuda',
            '-i', str(video_path),
            '-f', 'null', '-'
        ]
    else:
        cmd = [
            'ffmpeg', '-y',
            '-i', str(video_path),
            '-f', 'null', '-'
        ]

    result = run_ffmpeg_benchmark(cmd, f"Decoding ({'GPU NVDEC' if use_gpu else 'CPU'})", logger)
    result['decoder'] = 'cuda' if use_gpu else 'cpu'
    return result


def find_test_videos(test_dir):
    """Find video files in test directory"""
    video_extensions = {'.mp4', '.mkv', '.mov', '.avi', '.webm'}
    videos = []

    for f in test_dir.iterdir():
        if f.is_file() and f.suffix.lower() in video_extensions:
            videos.append(f)

    return sorted(videos)


def test_pcie_bandwidth(logger):
    """Test PCIe bandwidth by measuring GPU memory transfer speed"""
    logger.log("\n--- PCIe BANDWIDTH TEST ---")

    results = {}

    # Test 1: Generate video directly on GPU (no PCIe transfer needed)
    logger.log("Test 1: GPU-only generation (no PCIe transfer)")
    cmd = [
        'ffmpeg', '-y', '-f', 'lavfi',
        '-i', 'testsrc=duration=10:size=3840x2160:rate=30',
        '-c:v', 'h264_nvenc', '-preset', 'p3',
        '-f', 'null', '-'
    ]
    result = run_ffmpeg_benchmark(cmd, "GPU-only 4K generation", logger, timeout=120)
    results['gpu_only_generation'] = result

    # Test 2: CPU decode -> GPU encode (tests PCIe upload)
    logger.log("\nTest 2: CPU decode -> GPU encode (PCIe upload test)")
    cmd = [
        'ffmpeg', '-y', '-f', 'lavfi',
        '-i', 'testsrc=duration=10:size=3840x2160:rate=30',
        '-c:v', 'h264_nvenc', '-preset', 'p3',
        '-f', 'null', '-'
    ]
    # This is same as above, let's do a rawvideo test

    # Test 3: Large frame transfer test
    logger.log("\nTest 3: Raw frame transfer (stress test PCIe)")
    cmd = [
        'ffmpeg', '-y', '-f', 'lavfi',
        '-i', 'color=c=blue:size=3840x2160:rate=60:duration=5',
        '-pix_fmt', 'yuv420p',
        '-c:v', 'h264_nvenc', '-preset', 'p1',
        '-f', 'null', '-'
    ]
    result = run_ffmpeg_benchmark(cmd, "4K60 raw frames -> NVENC", logger, timeout=120)
    results['raw_4k60_encode'] = result

    # Test 4: GPU decode + GPU encode (minimal PCIe)
    logger.log("\nTest 4: NVDEC decode -> NVENC encode (GPU-to-GPU, minimal PCIe)")
    # We'll test this with actual video file later

    return results


def test_bottleneck_diagnosis(video_path, logger):
    """Run specific tests to identify bottlenecks"""
    logger.log("\n" + "=" * 50)
    logger.log("BOTTLENECK DIAGNOSIS TESTS")
    logger.log("=" * 50)

    results = {}
    video_info = get_video_info(video_path)
    duration = video_info.get('duration', 30)

    # Test A: Pure GPU pipeline (NVDEC -> NVENC, minimal CPU/PCIe)
    logger.log("\n[A] GPU-ONLY PIPELINE (NVDEC -> NVENC)")
    logger.log("    If this is slow: GPU hardware issue")
    cmd = [
        'ffmpeg', '-y',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(video_path),
        '-c:v', 'h264_nvenc', '-preset', 'p3',
        '-c:a', 'copy',
        '-f', 'null', '-'
    ]
    result = run_ffmpeg_benchmark(cmd, "GPU-only pipeline", logger)
    results['gpu_only_pipeline'] = result
    if result.get('success') and result.get('speed'):
        expected_time = duration / result['speed']
        logger.log(f"    -> GPU processing: {result['speed']}x realtime")

    # Test B: CPU decode -> GPU encode (tests PCIe upload bandwidth)
    logger.log("\n[B] CPU DECODE -> GPU ENCODE (PCIe upload test)")
    logger.log("    If slower than [A]: PCIe upload is bottleneck")
    cmd = [
        'ffmpeg', '-y',
        '-i', str(video_path),  # CPU decode
        '-c:v', 'h264_nvenc', '-preset', 'p3',
        '-c:a', 'copy',
        '-f', 'null', '-'
    ]
    result = run_ffmpeg_benchmark(cmd, "CPU decode -> GPU encode", logger)
    results['cpu_decode_gpu_encode'] = result
    if result.get('success') and result.get('speed'):
        logger.log(f"    -> With CPU decode: {result['speed']}x realtime")

    # Test C: GPU decode -> CPU encode (tests PCIe download bandwidth)
    logger.log("\n[C] GPU DECODE -> CPU ENCODE (PCIe download test)")
    logger.log("    If slower than [A]: PCIe download is bottleneck")
    cmd = [
        'ffmpeg', '-y',
        '-hwaccel', 'cuda',
        '-i', str(video_path),
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
        '-c:a', 'copy',
        '-f', 'null', '-'
    ]
    result = run_ffmpeg_benchmark(cmd, "GPU decode -> CPU encode", logger)
    results['gpu_decode_cpu_encode'] = result
    if result.get('success') and result.get('speed'):
        logger.log(f"    -> With GPU decode + CPU encode: {result['speed']}x realtime")

    # Test D: CPU only (no GPU at all)
    logger.log("\n[D] CPU-ONLY PIPELINE (baseline)")
    logger.log("    Baseline for comparison")
    cmd = [
        'ffmpeg', '-y',
        '-i', str(video_path),
        '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '23',
        '-c:a', 'copy',
        '-f', 'null', '-'
    ]
    result = run_ffmpeg_benchmark(cmd, "CPU-only pipeline", logger)
    results['cpu_only_pipeline'] = result
    if result.get('success') and result.get('speed'):
        logger.log(f"    -> CPU only: {result['speed']}x realtime")

    # Test E: With complex filter (forces CPU-GPU transfers)
    logger.log("\n[E] COMPLEX FILTER TEST (forces CPU-GPU sync)")
    logger.log("    If much slower: CPU-GPU data transfer is bottleneck")

    # Use Windows system font to avoid fontconfig issues
    font_path = "C\\\\:/Windows/Fonts/arial.ttf"
    drawtext_filter = f"drawtext=text='Test':fontfile='{font_path}':fontsize=24:x=10:y=10"

    cmd = [
        'ffmpeg', '-y',
        '-hwaccel', 'cuda',
        '-i', str(video_path),
        '-vf', f'scale=1920:1080,{drawtext_filter}',
        '-c:v', 'h264_nvenc', '-preset', 'p3',
        '-c:a', 'copy',
        '-f', 'null', '-'
    ]
    result = run_ffmpeg_benchmark(cmd, "With filter chain", logger)
    results['with_filters'] = result
    if result.get('success') and result.get('speed'):
        logger.log(f"    -> With filters: {result['speed']}x realtime")

    # Test F: Disk read speed (decode only, no encode)
    logger.log("\n[F] DISK READ TEST (decode to null)")
    logger.log("    Tests storage read speed")
    cmd = [
        'ffmpeg', '-y',
        '-i', str(video_path),
        '-f', 'null', '-'
    ]
    result = run_ffmpeg_benchmark(cmd, "Disk read + decode", logger)
    results['disk_read_test'] = result
    if result.get('success') and result.get('speed'):
        logger.log(f"    -> Disk read: {result['speed']}x realtime")

    # Analysis
    logger.log("\n" + "-" * 50)
    logger.log("DIAGNOSIS ANALYSIS:")
    logger.log("-" * 50)

    a_speed = results.get('gpu_only_pipeline', {}).get('speed', 0) or 0
    b_speed = results.get('cpu_decode_gpu_encode', {}).get('speed', 0) or 0
    c_speed = results.get('gpu_decode_cpu_encode', {}).get('speed', 0) or 0
    d_speed = results.get('cpu_only_pipeline', {}).get('speed', 0) or 0
    e_speed = results.get('with_filters', {}).get('speed', 0) or 0
    f_speed = results.get('disk_read_test', {}).get('speed', 0) or 0

    if a_speed > 0:
        logger.log(f"\n  GPU Pipeline Speed: {a_speed}x")

        if b_speed > 0 and a_speed > b_speed * 1.3:
            logger.log(f"  WARNING: CPU decode slows down by {((a_speed/b_speed)-1)*100:.0f}%")
            logger.log(f"  -> Possible PCIe UPLOAD bottleneck")

        if c_speed > 0 and a_speed > 0:
            # Compare GPU encode vs CPU encode
            logger.log(f"  GPU encode is {a_speed/max(d_speed,0.1):.1f}x faster than CPU")

        if e_speed > 0 and a_speed > e_speed * 1.5:
            logger.log(f"  WARNING: Filters slow down by {((a_speed/e_speed)-1)*100:.0f}%")
            logger.log(f"  -> CPU-GPU sync overhead detected")

        if f_speed > 0 and f_speed < a_speed * 0.8:
            logger.log(f"  WARNING: Disk read may be limiting ({f_speed}x vs {a_speed}x)")

    return results


def find_overlay_png(test_dir):
    """Find PNG overlay in test directory"""
    for f in test_dir.iterdir():
        if f.is_file() and f.suffix.lower() == '.png':
            return f
    return None


def main():
    print("=" * 70)
    print("GPU ENCODING BENCHMARK")
    print("=" * 70)

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize logger
    logger = BenchmarkLogger(LOG_FILE)
    logger.log("=" * 70)
    logger.log("GPU ENCODING BENCHMARK STARTED")
    logger.log("=" * 70)

    # Get and log system info
    logger.log("\n--- SYSTEM INFORMATION ---")
    sys_info = get_system_info()
    for key, value in sys_info.items():
        logger.log(f"  {key}: {value}")

    # Check for NVENC support
    logger.log("\n--- CHECKING NVENC SUPPORT ---")
    nvenc_check = subprocess.run(
        ['ffmpeg', '-hide_banner', '-encoders'],
        capture_output=True, text=True
    )
    has_nvenc = 'h264_nvenc' in nvenc_check.stdout
    logger.log(f"  h264_nvenc available: {has_nvenc}")

    if not has_nvenc:
        logger.log("  WARNING: NVENC not available, GPU tests will be skipped")

    # Find test videos
    logger.log("\n--- FINDING TEST VIDEOS ---")
    videos = find_test_videos(TEST_DIR)

    if not videos:
        logger.log(f"  ERROR: No video files found in {TEST_DIR}")
        logger.log("  Please add .mp4, .mkv, .mov, .avi, or .webm files to the test-gpu folder")
        return

    for v in videos:
        info = get_video_info(v)
        logger.log(f"  Found: {v.name}")
        logger.log(f"    Resolution: {info.get('width')}x{info.get('height')}")
        logger.log(f"    Duration: {info.get('duration', 0):.1f}s, FPS: {info.get('fps')}, Size: {info.get('size_mb')}MB")

    # Find or create overlay PNG
    logger.log("\n--- OVERLAY PNG ---")
    overlay_png = find_overlay_png(TEST_DIR)

    if not overlay_png:
        overlay_png = TEST_DIR / "test_overlay.png"
        logger.log(f"  Creating test overlay: {overlay_png}")
        if not create_test_overlay_png(overlay_png):
            logger.log("  WARNING: Could not create overlay PNG")
            overlay_png = None
    else:
        logger.log(f"  Found overlay: {overlay_png.name}")

    # Use first video for benchmarks
    test_video = videos[0]
    video_info = get_video_info(test_video)

    logger.log(f"\n--- USING TEST VIDEO: {test_video.name} ---")

    # ==================== BENCHMARKS ====================

    all_results = {
        'system_info': sys_info,
        'video_info': video_info,
        'benchmarks': {},
        'diagnosis': {}
    }

    # 0. BOTTLENECK DIAGNOSIS (most important!)
    logger.log("\n" + "=" * 70)
    logger.log("BOTTLENECK DIAGNOSIS - Finding the root cause")
    logger.log("=" * 70)

    if has_nvenc:
        diagnosis_results = test_bottleneck_diagnosis(test_video, logger)
        all_results['diagnosis'] = diagnosis_results

    # 1. Decoding benchmarks
    logger.log("\n" + "=" * 50)
    logger.log("DECODING BENCHMARKS")
    logger.log("=" * 50)

    all_results['benchmarks']['decode_cpu'] = benchmark_decoding(test_video, logger, use_gpu=False)
    if has_nvenc:
        all_results['benchmarks']['decode_gpu'] = benchmark_decoding(test_video, logger, use_gpu=True)

    # 2. Pure encoding benchmarks
    logger.log("\n" + "=" * 50)
    logger.log("PURE ENCODING BENCHMARKS (no filters)")
    logger.log("=" * 50)

    for preset in PRESETS_CPU:
        all_results['benchmarks'][f'encode_cpu_{preset}'] = benchmark_pure_encoding(
            test_video, logger, use_gpu=False, preset=preset
        )

    if has_nvenc:
        for preset in PRESETS_GPU:
            all_results['benchmarks'][f'encode_gpu_{preset}'] = benchmark_pure_encoding(
                test_video, logger, use_gpu=True, preset=preset
            )

    # 3. PNG overlay benchmarks
    if overlay_png:
        logger.log("\n" + "=" * 50)
        logger.log("PNG OVERLAY BENCHMARKS")
        logger.log("=" * 50)

        all_results['benchmarks']['overlay_cpu_fast'] = benchmark_with_png_overlay(
            test_video, overlay_png, logger, use_gpu=False, preset='fast'
        )

        if has_nvenc:
            all_results['benchmarks']['overlay_gpu_p3'] = benchmark_with_png_overlay(
                test_video, overlay_png, logger, use_gpu=True, preset='p3'
            )

    # 4. Text overlay benchmarks
    logger.log("\n" + "=" * 50)
    logger.log("TEXT OVERLAY BENCHMARKS (drawtext)")
    logger.log("=" * 50)

    all_results['benchmarks']['text_cpu_fast'] = benchmark_with_text_overlay(
        test_video, logger, use_gpu=False, preset='fast'
    )

    if has_nvenc:
        all_results['benchmarks']['text_gpu_p3'] = benchmark_with_text_overlay(
            test_video, logger, use_gpu=True, preset='p3'
        )

    # 5. Combined filter benchmarks
    if overlay_png:
        logger.log("\n" + "=" * 50)
        logger.log("COMBINED FILTER BENCHMARKS (overlay + text)")
        logger.log("=" * 50)

        all_results['benchmarks']['combined_cpu_fast'] = benchmark_combined_filters(
            test_video, overlay_png, logger, use_gpu=False, preset='fast'
        )

        if has_nvenc:
            all_results['benchmarks']['combined_gpu_p3'] = benchmark_combined_filters(
                test_video, overlay_png, logger, use_gpu=True, preset='p3'
            )

    # ==================== SUMMARY ====================

    logger.log("\n" + "=" * 70)
    logger.log("BENCHMARK SUMMARY")
    logger.log("=" * 70)

    logger.log(f"\nSystem: {sys_info.get('hostname', 'Unknown')}")
    logger.log(f"GPU: {sys_info.get('gpu_name', 'Unknown')}")
    logger.log(f"PCIe: Gen {sys_info.get('pcie_gen', '?')} x{sys_info.get('pcie_width', '?')}")
    logger.log(f"Video: {test_video.name} ({video_info.get('width')}x{video_info.get('height')}, {video_info.get('duration', 0):.1f}s)")

    logger.log("\n--- ENCODING SPEEDS ---")
    logger.log(f"{'Test':<35} {'Time (s)':<12} {'Speed':<10} {'FPS':<10}")
    logger.log("-" * 70)

    for name, result in all_results['benchmarks'].items():
        if result.get('success'):
            time_str = f"{result.get('elapsed_seconds', 0):.1f}s"
            speed_str = f"{result.get('speed', 0)}x" if result.get('speed') else "N/A"
            fps_str = f"{result.get('fps', 0):.1f}" if result.get('fps') else "N/A"
            logger.log(f"{name:<35} {time_str:<12} {speed_str:<10} {fps_str:<10}")
        else:
            logger.log(f"{name:<35} FAILED")

    # Save JSON results
    json_file = OUTPUT_DIR / f"benchmark_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(json_file, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)

    logger.log(f"\nResults saved to:")
    logger.log(f"  Log: {LOG_FILE}")
    logger.log(f"  JSON: {json_file}")

    # Print key comparison metrics
    logger.log("\n" + "=" * 70)
    logger.log("KEY METRICS FOR COMPARISON (copy this)")
    logger.log("=" * 70)
    logger.log(f"PC: {sys_info.get('hostname', 'Unknown')}")
    logger.log(f"GPU: {sys_info.get('gpu_name', 'Unknown')}")
    logger.log(f"PCIe: Gen {sys_info.get('pcie_gen', '?')} x{sys_info.get('pcie_width', '?')}")
    logger.log(f"Driver: {sys_info.get('driver_version', 'Unknown')}")

    diag = all_results.get('diagnosis', {})
    logger.log(f"\nDIAGNOSIS SPEEDS (x realtime):")
    logger.log(f"  [A] GPU-only (NVDEC->NVENC): {diag.get('gpu_only_pipeline', {}).get('speed', 'N/A')}x")
    logger.log(f"  [B] CPU decode->GPU encode: {diag.get('cpu_decode_gpu_encode', {}).get('speed', 'N/A')}x")
    logger.log(f"  [C] GPU decode->CPU encode: {diag.get('gpu_decode_cpu_encode', {}).get('speed', 'N/A')}x")
    logger.log(f"  [D] CPU-only:               {diag.get('cpu_only_pipeline', {}).get('speed', 'N/A')}x")
    logger.log(f"  [E] With filters:           {diag.get('with_filters', {}).get('speed', 'N/A')}x")
    logger.log(f"  [F] Disk read:              {diag.get('disk_read_test', {}).get('speed', 'N/A')}x")

    logger.log("\nINTERPRETATION:")
    logger.log("  - If [A] is slow: GPU hardware/driver issue")
    logger.log("  - If [B] << [A]: PCIe UPLOAD bottleneck (CPU->GPU)")
    logger.log("  - If [C] << [D]: PCIe DOWNLOAD bottleneck (GPU->CPU)")
    logger.log("  - If [E] << [A]: CPU-GPU sync overhead")
    logger.log("  - If [F] is slow: Storage bottleneck")

    logger.log("\n" + "=" * 70)
    logger.log("BENCHMARK COMPLETE")
    logger.log("=" * 70)

    print(f"\nDone! Check results in: {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
