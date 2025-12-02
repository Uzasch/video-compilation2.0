"""
GPU Encoding/Decoding Benchmark & Diagnostic Tool
Run this on each PC to compare performance and diagnose slowdowns.

Outputs detailed report to: gpu_benchmark_report.txt
"""

import subprocess
import time
import platform
import os
import json
import tempfile
from pathlib import Path
from datetime import datetime

REPORT_FILE = "gpu_benchmark_report.txt"
TEST_DURATION = 10  # seconds for test video

def run_cmd(cmd, timeout=60):
    """Run command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip() + result.stderr.strip()
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    except Exception as e:
        return f"ERROR: {e}"

def run_cmd_timed(cmd, timeout=300):
    """Run command and return (success, output, duration)."""
    start = time.time()
    try:
        result = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout)
        duration = time.time() - start
        return result.returncode == 0, result.stdout + result.stderr, duration
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT", timeout
    except Exception as e:
        return False, str(e), time.time() - start

def write_report(lines):
    """Write lines to report file."""
    with open(REPORT_FILE, 'a', encoding='utf-8') as f:
        for line in lines:
            f.write(line + '\n')
            print(line)

def section(title):
    """Print section header."""
    lines = [
        "",
        "=" * 70,
        f" {title}",
        "=" * 70,
    ]
    write_report(lines)

def main():
    # Clear previous report
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"GPU BENCHMARK REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Computer Name: {platform.node()}\n")

    # ==================== SYSTEM INFO ====================
    section("SYSTEM INFORMATION")

    # OS
    write_report([
        f"OS: {platform.system()} {platform.release()}",
        f"Version: {platform.version()}",
        f"Architecture: {platform.machine()}",
    ])

    # CPU
    section("CPU INFORMATION")
    cpu_info = run_cmd('wmic cpu get name,numberofcores,numberoflogicalprocessors,maxclockspeed /format:list')
    for line in cpu_info.split('\n'):
        if '=' in line and line.split('=')[1].strip():
            write_report([f"  {line.strip()}"])

    # RAM
    section("MEMORY (RAM)")
    ram_info = run_cmd('wmic memorychip get capacity,speed /format:list')
    total_ram = 0
    for line in ram_info.split('\n'):
        if line.startswith('Capacity=') and line.split('=')[1].strip():
            try:
                total_ram += int(line.split('=')[1].strip())
            except:
                pass
    write_report([f"  Total RAM: {total_ram / (1024**3):.1f} GB"])

    # ==================== GPU INFO ====================
    section("GPU INFORMATION (nvidia-smi)")

    gpu_queries = [
        ('name', 'GPU Name'),
        ('driver_version', 'Driver Version'),
        ('memory.total', 'VRAM Total'),
        ('memory.free', 'VRAM Free'),
        ('memory.used', 'VRAM Used'),
        ('temperature.gpu', 'Temperature'),
        ('power.draw', 'Power Draw'),
        ('power.limit', 'Power Limit'),
        ('clocks.current.graphics', 'GPU Clock'),
        ('clocks.max.graphics', 'Max GPU Clock'),
        ('clocks.current.memory', 'Memory Clock'),
        ('clocks.max.memory', 'Max Memory Clock'),
        ('utilization.gpu', 'GPU Utilization'),
        ('utilization.memory', 'Memory Utilization'),
        ('pcie.link.gen.current', 'PCIe Gen'),
        ('pcie.link.width.current', 'PCIe Width'),
        ('encoder.stats.sessionCount', 'NVENC Sessions'),
        ('encoder.stats.averageFps', 'NVENC Avg FPS'),
    ]

    for query, label in gpu_queries:
        result = run_cmd(f'nvidia-smi --query-gpu={query} --format=csv,noheader,nounits')
        if 'ERROR' not in result and 'not supported' not in result.lower():
            write_report([f"  {label}: {result}"])

    # GPU detailed info
    section("GPU DETAILED INFO")
    gpu_detail = run_cmd('nvidia-smi -q')
    # Extract important sections
    important_lines = []
    capture = False
    for line in gpu_detail.split('\n'):
        if any(x in line for x in ['Product Name', 'CUDA Version', 'Driver Version', 'NVENC', 'NVDEC', 'Encoder', 'Decoder']):
            important_lines.append(f"  {line.strip()}")
    write_report(important_lines[:20])  # Limit output

    # ==================== NVENC/NVDEC CAPABILITIES ====================
    section("NVENC/NVDEC CAPABILITIES")

    # Check FFmpeg encoders
    encoders = run_cmd('ffmpeg -hide_banner -encoders 2>&1')
    nvenc_encoders = [line.strip() for line in encoders.split('\n') if 'nvenc' in line.lower()]
    write_report(["NVENC Encoders:"])
    for enc in nvenc_encoders:
        write_report([f"  {enc}"])

    # Check FFmpeg decoders
    decoders = run_cmd('ffmpeg -hide_banner -decoders 2>&1')
    nvdec_decoders = [line.strip() for line in decoders.split('\n') if 'cuvid' in line.lower()]
    write_report(["NVDEC Decoders:"])
    for dec in nvdec_decoders:
        write_report([f"  {dec}"])

    # ==================== FFMPEG INFO ====================
    section("FFMPEG INFORMATION")
    ffmpeg_version = run_cmd('ffmpeg -version')
    for line in ffmpeg_version.split('\n')[:5]:
        write_report([f"  {line}"])

    # ==================== POWER SETTINGS ====================
    section("POWER SETTINGS")
    power_plan = run_cmd('powercfg /getactivescheme')
    write_report([f"  {power_plan}"])

    # Check if high performance
    if 'high performance' in power_plan.lower():
        write_report(["  ✅ High Performance mode"])
    elif 'balanced' in power_plan.lower():
        write_report(["  ⚠️ Balanced mode - consider High Performance"])
    else:
        write_report(["  ⚠️ Check power settings"])

    # ==================== STORAGE SPEED ====================
    section("STORAGE INFORMATION")
    drives = run_cmd('wmic diskdrive get model,mediatype,size /format:list')
    current = {}
    for line in drives.split('\n'):
        if '=' in line:
            key, val = line.split('=', 1)
            val = val.strip()
            if val:
                current[key.strip()] = val
        elif current:
            if current.get('Model'):
                size_gb = int(current.get('Size', 0)) / (1024**3) if current.get('Size', '').isdigit() else 0
                write_report([f"  {current.get('Model')}: {size_gb:.0f} GB ({current.get('MediaType', 'Unknown')})"])
            current = {}

    # ==================== ENCODING BENCHMARKS ====================
    section("ENCODING BENCHMARKS")

    # Create test video
    write_report(["Creating test video..."])
    test_input = tempfile.mktemp(suffix='.mp4')
    test_output = tempfile.mktemp(suffix='.mp4')

    # Generate test video (1080p, 10 seconds of color bars)
    gen_cmd = f'ffmpeg -y -f lavfi -i testsrc=duration={TEST_DURATION}:size=1920x1080:rate=30 -f lavfi -i sine=frequency=1000:duration={TEST_DURATION} -c:v libx264 -preset ultrafast -c:a aac -shortest "{test_input}"'
    success, output, duration = run_cmd_timed(gen_cmd)
    if not success:
        write_report([f"  ❌ Failed to create test video: {output[:200]}"])
        return
    write_report([f"  ✅ Test video created ({TEST_DURATION}s, 1080p)"])

    # Benchmark presets
    presets_to_test = ['p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7']
    cq_values = [23]

    write_report([""])
    write_report(["NVENC Encoding Speed (h264_nvenc):"])
    write_report(["-" * 50])

    results = []

    for preset in presets_to_test:
        for cq in cq_values:
            # Clean output
            if os.path.exists(test_output):
                os.remove(test_output)

            cmd = [
                'ffmpeg', '-y',
                '-i', test_input,
                '-c:v', 'h264_nvenc',
                '-preset', preset,
                '-cq', str(cq),
                '-c:a', 'copy',
                test_output
            ]

            success, output, duration = run_cmd_timed(cmd, timeout=120)

            if success:
                # Calculate speed
                speed = TEST_DURATION / duration if duration > 0 else 0
                file_size = os.path.getsize(test_output) / (1024 * 1024) if os.path.exists(test_output) else 0
                bitrate = (file_size * 8) / TEST_DURATION if TEST_DURATION > 0 else 0

                result_line = f"  Preset {preset} CQ{cq}: {duration:.2f}s ({speed:.1f}x realtime) | {file_size:.1f}MB | {bitrate:.1f} Mbps"
                write_report([result_line])
                results.append({
                    'preset': preset,
                    'cq': cq,
                    'duration': duration,
                    'speed': speed,
                    'size_mb': file_size,
                    'bitrate_mbps': bitrate
                })
            else:
                write_report([f"  Preset {preset} CQ{cq}: ❌ FAILED"])
                if 'not supported' in output.lower() or 'invalid' in output.lower():
                    write_report([f"    (Preset not supported on this GPU)"])

    # CPU encoding benchmark
    write_report([""])
    write_report(["CPU Encoding Speed (libx264):"])
    write_report(["-" * 50])

    cpu_presets = ['ultrafast', 'veryfast', 'fast', 'medium']
    for preset in cpu_presets:
        if os.path.exists(test_output):
            os.remove(test_output)

        cmd = [
            'ffmpeg', '-y',
            '-i', test_input,
            '-c:v', 'libx264',
            '-preset', preset,
            '-crf', '23',
            '-c:a', 'copy',
            test_output
        ]

        success, output, duration = run_cmd_timed(cmd, timeout=300)

        if success:
            speed = TEST_DURATION / duration if duration > 0 else 0
            file_size = os.path.getsize(test_output) / (1024 * 1024) if os.path.exists(test_output) else 0
            bitrate = (file_size * 8) / TEST_DURATION if TEST_DURATION > 0 else 0
            write_report([f"  Preset {preset:10s}: {duration:.2f}s ({speed:.1f}x realtime) | {file_size:.1f}MB | {bitrate:.1f} Mbps"])
        else:
            write_report([f"  Preset {preset:10s}: ❌ FAILED"])

    # ==================== DECODING BENCHMARK ====================
    section("DECODING BENCHMARKS")

    write_report(["GPU Decoding (h264_cuvid):"])
    if os.path.exists(test_output):
        os.remove(test_output)

    # GPU decode
    cmd = f'ffmpeg -y -hwaccel cuvid -c:v h264_cuvid -i "{test_input}" -f null -'
    success, output, duration = run_cmd_timed(cmd)
    if success:
        speed = TEST_DURATION / duration if duration > 0 else 0
        write_report([f"  h264_cuvid: {duration:.2f}s ({speed:.1f}x realtime)"])
    else:
        write_report([f"  h264_cuvid: ❌ FAILED or not supported"])

    # CPU decode
    write_report(["CPU Decoding:"])
    cmd = f'ffmpeg -y -i "{test_input}" -f null -'
    success, output, duration = run_cmd_timed(cmd)
    if success:
        speed = TEST_DURATION / duration if duration > 0 else 0
        write_report([f"  Software: {duration:.2f}s ({speed:.1f}x realtime)"])

    # ==================== DISK I/O TEST ====================
    section("DISK I/O TEST")

    write_report(["Writing 500MB test file..."])
    io_test_file = tempfile.mktemp(suffix='.bin')
    start = time.time()
    try:
        with open(io_test_file, 'wb') as f:
            f.write(os.urandom(500 * 1024 * 1024))
        write_duration = time.time() - start
        write_speed = 500 / write_duration
        write_report([f"  Write Speed: {write_speed:.1f} MB/s"])

        # Read test
        start = time.time()
        with open(io_test_file, 'rb') as f:
            _ = f.read()
        read_duration = time.time() - start
        read_speed = 500 / read_duration
        write_report([f"  Read Speed: {read_speed:.1f} MB/s"])

        os.remove(io_test_file)
    except Exception as e:
        write_report([f"  ❌ I/O test failed: {e}"])

    # ==================== POTENTIAL ISSUES ====================
    section("POTENTIAL ISSUES / RECOMMENDATIONS")

    issues = []

    # Check power mode
    if 'balanced' in power_plan.lower():
        issues.append("⚠️ Power mode is 'Balanced' - switch to 'High Performance' for better GPU encoding")

    # Check driver
    driver_result = run_cmd('nvidia-smi --query-gpu=driver_version --format=csv,noheader')
    try:
        driver_ver = int(driver_result.split('.')[0])
        if driver_ver < 530:
            issues.append(f"⚠️ Driver version {driver_result} is old - consider updating")
    except:
        pass

    # Check GPU utilization during idle
    util_result = run_cmd('nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits')
    try:
        util = int(util_result)
        if util > 20:
            issues.append(f"⚠️ GPU is {util}% utilized at idle - check for background processes")
    except:
        pass

    # Check PCIe
    pcie_gen = run_cmd('nvidia-smi --query-gpu=pcie.link.gen.current --format=csv,noheader')
    pcie_width = run_cmd('nvidia-smi --query-gpu=pcie.link.width.current --format=csv,noheader')
    try:
        if int(pcie_gen) < 3:
            issues.append(f"⚠️ PCIe Gen {pcie_gen} is slow - check motherboard slot")
        if int(pcie_width) < 8:
            issues.append(f"⚠️ PCIe x{pcie_width} is narrow - check slot or cable")
    except:
        pass

    # Check temp
    temp_result = run_cmd('nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader')
    try:
        temp = int(temp_result)
        if temp > 80:
            issues.append(f"⚠️ GPU temperature is {temp}°C - check cooling")
    except:
        pass

    if issues:
        for issue in issues:
            write_report([f"  {issue}"])
    else:
        write_report(["  ✅ No obvious issues detected"])

    # Cleanup
    for f in [test_input, test_output]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except:
            pass

    section("END OF REPORT")
    write_report([f"Report saved to: {REPORT_FILE}"])
    write_report([f"Run this on both PCs and compare the results!"])

if __name__ == "__main__":
    main()
