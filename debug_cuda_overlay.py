#!/usr/bin/env python3
"""
Debug script for overlay_cuda issues.
Tests various overlay_cuda configurations to find why output is corrupted.
"""

import subprocess
import os
from pathlib import Path

TEST_GPU_DIR = Path(r"C:\Users\uzair\softwares\video-compilation-2.0\test_gpu")

OUTPUT_DIR = TEST_GPU_DIR / "debug_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

VIDEO_FILE = TEST_GPU_DIR / "ABC_OS_Fivezombiesjumpinginthemiddleofthenight_nyv-26Sep-2025-15-28-59.mp4"
OVERLAY_PNG = TEST_GPU_DIR / "ABC_English.png"

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080


def run_test(name: str, cmd: list):
    """Run FFmpeg command and show full output"""
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print(f"{'='*70}")
    print(f"Command:\n{' '.join(cmd)}\n")

    result = subprocess.run(cmd, capture_output=True, text=True)

    print(f"Return code: {result.returncode}")
    print(f"\n--- STDERR (last 2000 chars) ---")
    print(result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr)

    # Check output file
    output_file = cmd[-1]
    if os.path.exists(output_file):
        size_mb = os.path.getsize(output_file) / (1024*1024)
        print(f"\nOutput file: {output_file}")
        print(f"Size: {size_mb:.2f} MB")

        # Get video info
        probe = subprocess.run([
            'ffprobe', '-v', 'error',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=width,height,nb_frames,duration',
            '-of', 'csv=p=0',
            output_file
        ], capture_output=True, text=True)
        print(f"Video info: {probe.stdout.strip()}")
    else:
        print(f"\nOutput file NOT created!")

    return result.returncode == 0


def test_1_baseline_no_overlay():
    """Test: Just scale_cuda, no overlay - does this work?"""
    output = str(OUTPUT_DIR / "test1_baseline.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-vf', f'scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("Baseline: scale_cuda only (no overlay)", cmd)


def test_2_overlay_cuda_simple():
    """Test: Simple overlay_cuda - what's in the original failing test"""
    output = str(OUTPUT_DIR / "test2_overlay_cuda_simple.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12[base];'
        f'[1:v]format=nv12,hwupload[logo];'
        f'[base][logo]overlay_cuda=(W-w)/2:(H-h)/2',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("overlay_cuda simple (original failing)", cmd)


def test_3_overlay_cuda_fixed_coords():
    """Test: overlay_cuda with fixed x:y coordinates"""
    output = str(OUTPUT_DIR / "test3_overlay_cuda_fixed.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12[base];'
        f'[1:v]format=nv12,hwupload[logo];'
        f'[base][logo]overlay_cuda=x=0:y=0',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("overlay_cuda with x=0:y=0", cmd)


def test_4_overlay_cuda_scale_logo():
    """Test: Scale the logo to smaller size first"""
    output = str(OUTPUT_DIR / "test4_overlay_cuda_scaled_logo.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12[base];'
        f'[1:v]scale=200:-1,format=nv12,hwupload[logo];'
        f'[base][logo]overlay_cuda=x=10:y=10',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("overlay_cuda with scaled logo (200px wide)", cmd)


def test_5_hwdownload_cpu_overlay():
    """Test: Download from GPU, CPU overlay, upload back - known working"""
    output = str(OUTPUT_DIR / "test5_hwdownload_overlay.mp4")
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
    return run_test("hwdownload + CPU overlay (known working)", cmd)


def test_6_check_png_info():
    """Check PNG file info"""
    print(f"\n{'='*70}")
    print("PNG FILE INFO")
    print(f"{'='*70}")

    result = subprocess.run([
        'ffprobe', '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,pix_fmt,codec_name',
        '-of', 'csv=p=0',
        str(OVERLAY_PNG)
    ], capture_output=True, text=True)
    print(f"PNG info: {result.stdout.strip()}")
    print(f"File size: {os.path.getsize(OVERLAY_PNG) / 1024:.1f} KB")


def test_7_overlay_cuda_yuv420p():
    """Test: Use yuv420p instead of nv12"""
    output = str(OUTPUT_DIR / "test7_overlay_cuda_yuv420p.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=yuv420p[base];'
        f'[1:v]format=yuv420p,hwupload[logo];'
        f'[base][logo]overlay_cuda=x=10:y=10',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("overlay_cuda with yuv420p format", cmd)


def test_8_overlay_cuda_no_scale():
    """Test: No scaling, just overlay_cuda on original video"""
    output = str(OUTPUT_DIR / "test8_overlay_cuda_no_scale.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale_cuda=format=nv12[base];'
        f'[1:v]scale=200:-1,format=nv12,hwupload[logo];'
        f'[base][logo]overlay_cuda=x=10:y=10',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("overlay_cuda no resize (keep 4K)", cmd)


def test_9_shortest_option():
    """Test: Add shortest=1 option"""
    output = str(OUTPUT_DIR / "test9_overlay_cuda_shortest.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12[base];'
        f'[1:v]scale=200:-1,format=nv12,hwupload[logo];'
        f'[base][logo]overlay_cuda=x=10:y=10:shortest=1',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("overlay_cuda with shortest=1", cmd)


def test_10_eof_action():
    """Test: Add eof_action=repeat"""
    output = str(OUTPUT_DIR / "test10_overlay_cuda_eof.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12[base];'
        f'[1:v]scale=200:-1,format=nv12,hwupload[logo];'
        f'[base][logo]overlay_cuda=x=10:y=10:eof_action=repeat',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("overlay_cuda with eof_action=repeat", cmd)


def test_11_loop_png():
    """Test: Loop the PNG input"""
    output = str(OUTPUT_DIR / "test11_loop_png.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-loop', '1', '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12[base];'
        f'[1:v]scale=200:-1,format=nv12,hwupload[logo];'
        f'[base][logo]overlay_cuda=x=10:y=10:shortest=1',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("overlay_cuda with -loop 1 on PNG", cmd)


def test_12_solid_color_overlay():
    """Test: Use solid color instead of PNG (to isolate PNG issue)"""
    output = str(OUTPUT_DIR / "test12_solid_color.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-f', 'lavfi', '-i', 'color=c=red:s=200x100:d=120',
        '-filter_complex',
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12[base];'
        f'[1:v]format=nv12,hwupload[logo];'
        f'[base][logo]overlay_cuda=x=10:y=10:shortest=1',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("overlay_cuda with solid red color (no PNG)", cmd)


def test_13_png_scale_on_gpu():
    """Test: Scale PNG on GPU too using hwupload first then scale_cuda"""
    output = str(OUTPUT_DIR / "test13_png_scale_gpu.mp4")
    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-i', str(OVERLAY_PNG),
        '-filter_complex',
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12[base];'
        f'[1:v]format=nv12,hwupload,scale_cuda=200:-1:format=nv12[logo];'
        f'[base][logo]overlay_cuda=x=10:y=10',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("overlay_cuda with PNG scaled on GPU (scale_cuda)", cmd)


def test_14_check_overlay_cuda_help():
    """Check overlay_cuda filter options"""
    print(f"\n{'='*70}")
    print("overlay_cuda FILTER OPTIONS")
    print(f"{'='*70}")
    result = subprocess.run([
        'ffmpeg', '-h', 'filter=overlay_cuda'
    ], capture_output=True, text=True)
    print(result.stdout if result.stdout else result.stderr)


def test_15_video_to_video_overlay():
    """Test: Use video input for overlay instead of PNG"""
    output = str(OUTPUT_DIR / "test15_video_overlay.mp4")
    # Create a short test video first
    test_overlay = str(OUTPUT_DIR / "test_overlay_video.mp4")
    subprocess.run([
        'ffmpeg', '-y',
        '-f', 'lavfi', '-i', 'color=c=blue:s=200x100:d=120,format=nv12',
        '-c:v', 'h264_nvenc', '-preset', 'p1',
        test_overlay
    ], capture_output=True)

    cmd = [
        'ffmpeg', '-y',
        '-init_hw_device', 'cuda=cuda', '-filter_hw_device', 'cuda',
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', str(VIDEO_FILE),
        '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda',
        '-i', test_overlay,
        '-filter_complex',
        f'[0:v]scale_cuda={TARGET_WIDTH}:{TARGET_HEIGHT}:format=nv12[base];'
        f'[1:v]scale_cuda=200:100:format=nv12[logo];'
        f'[base][logo]overlay_cuda=x=10:y=10:shortest=1',
        '-c:v', 'h264_nvenc', '-preset', 'p3', '-cq', '23',
        '-c:a', 'copy',
        output
    ]
    return run_test("overlay_cuda with VIDEO overlay (both GPU decoded)", cmd)


def main():
    print("="*70)
    print("DEBUGGING overlay_cuda ISSUES")
    print("="*70)

    # Check PNG and overlay_cuda options first
    test_6_check_png_info()
    test_14_check_overlay_cuda_help()

    # Run tests
    results = []
    results.append(("Baseline (no overlay)", test_1_baseline_no_overlay()))
    results.append(("hwdownload + CPU overlay", test_5_hwdownload_cpu_overlay()))
    results.append(("overlay_cuda simple", test_2_overlay_cuda_simple()))
    results.append(("overlay_cuda fixed coords", test_3_overlay_cuda_fixed_coords()))
    results.append(("overlay_cuda scaled logo", test_4_overlay_cuda_scale_logo()))
    results.append(("overlay_cuda yuv420p", test_7_overlay_cuda_yuv420p()))
    results.append(("overlay_cuda no scale", test_8_overlay_cuda_no_scale()))
    results.append(("overlay_cuda shortest=1", test_9_shortest_option()))
    results.append(("overlay_cuda eof_action=repeat", test_10_eof_action()))
    results.append(("overlay_cuda loop PNG", test_11_loop_png()))
    results.append(("overlay_cuda solid color", test_12_solid_color_overlay()))
    results.append(("overlay_cuda PNG scale GPU", test_13_png_scale_on_gpu()))
    results.append(("overlay_cuda video-on-video", test_15_video_to_video_overlay()))

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    for name, success in results:
        status = "✓ OK" if success else "✗ FAILED"
        print(f"  {status}: {name}")


if __name__ == '__main__':
    main()
