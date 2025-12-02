"""
Test NVENC GPU encoding availability with different presets.
Run this on each worker PC to check GPU encoding support.
"""

import subprocess
import sys

def test_nvenc(preset=None):
    """Test if NVENC encoding works with optional preset."""
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi', '-i', 'nullsrc=s=256x256:d=0.1',
        '-c:v', 'h264_nvenc',
    ]

    if preset:
        cmd.extend(['-preset', preset])

    cmd.extend(['-f', 'null', '-'])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.returncode == 0, result.stderr
    except Exception as e:
        return False, str(e)

def main():
    print("=" * 60)
    print("NVENC GPU ENCODING TEST")
    print("=" * 60)

    # Get GPU info
    print("\n[GPU INFO]")
    gpu_info = subprocess.run(
        ['nvidia-smi', '--query-gpu=name,driver_version', '--format=csv,noheader'],
        capture_output=True, text=True
    )
    if gpu_info.returncode == 0:
        print(f"  {gpu_info.stdout.strip()}")
    else:
        print("  nvidia-smi not available")

    # Test basic NVENC
    print("\n[NVENC TESTS]")

    # Test without preset (basic)
    success, err = test_nvenc(None)
    print(f"  Basic NVENC:     {'✅ PASS' if success else '❌ FAIL'}")
    if not success:
        print(f"    Error: {err[:200]}")
        print("\n❌ NVENC not available - will use CPU encoding")
        return

    # Test each preset
    presets = ['p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7']

    print("\n[PRESET TESTS]")
    results = {}
    for preset in presets:
        success, err = test_nvenc(preset)
        results[preset] = success
        status = '✅ PASS' if success else '❌ FAIL'
        print(f"  Preset {preset}:       {status}")

    # Test old-style presets (for older GPUs)
    print("\n[OLD-STYLE PRESETS]")
    old_presets = ['fast', 'medium', 'slow', 'hq', 'hp', 'llhq']
    for preset in old_presets:
        success, err = test_nvenc(preset)
        status = '✅ PASS' if success else '❌ FAIL'
        print(f"  Preset {preset:8s}: {status}")

    # Recommendation
    print("\n[RECOMMENDATION]")
    if results.get('p3'):
        print("  ✅ Use p3 preset - fully supported")
    elif results.get('p2'):
        print("  ⚠️ Use p2 preset - p3 not supported")
    elif results.get('p1'):
        print("  ⚠️ Use p1 preset - limited support")
    else:
        print("  ❌ Use old-style presets (medium/fast) or CPU fallback")

    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()