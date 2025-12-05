#!/usr/bin/env python3
"""
GPU Monitor - Watch GPU stats during encoding
Run this WHILE running an FFmpeg encode to see what's happening
"""

import subprocess
import time
import sys

def get_gpu_stats():
    """Get current GPU stats"""
    try:
        result = subprocess.run([
            'nvidia-smi',
            '--query-gpu=name,temperature.gpu,power.draw,power.limit,clocks.current.graphics,clocks.max.graphics,utilization.gpu,utilization.encoder,utilization.decoder,pstate',
            '--format=csv,noheader,nounits'
        ], capture_output=True, text=True, timeout=5)

        if result.returncode == 0:
            parts = [p.strip() for p in result.stdout.strip().split(',')]
            if len(parts) >= 10:
                return {
                    'name': parts[0],
                    'temp': parts[1],
                    'power_draw': parts[2],
                    'power_limit': parts[3],
                    'clock_current': parts[4],
                    'clock_max': parts[5],
                    'gpu_util': parts[6],
                    'encoder_util': parts[7],
                    'decoder_util': parts[8],
                    'pstate': parts[9]
                }
    except Exception as e:
        return {'error': str(e)}
    return None

def main():
    print("=" * 80)
    print("GPU MONITOR - Press Ctrl+C to stop")
    print("Run an FFmpeg encode in another terminal to see GPU behavior")
    print("=" * 80)

    # Get initial stats
    stats = get_gpu_stats()
    if not stats:
        print("ERROR: Could not get GPU stats")
        return

    print(f"\nGPU: {stats.get('name', 'Unknown')}")
    print(f"Power Limit: {stats.get('power_limit', '?')}W")
    print(f"Max Clock: {stats.get('clock_max', '?')} MHz")
    print()

    print(f"{'Time':<10} {'Temp':<6} {'Power':<12} {'Clock':<12} {'GPU%':<6} {'Enc%':<6} {'Dec%':<6} {'PState':<8}")
    print("-" * 80)

    max_power = 0
    max_clock = 0
    max_gpu_util = 0

    try:
        start_time = time.time()
        while True:
            stats = get_gpu_stats()
            if stats and 'error' not in stats:
                elapsed = time.time() - start_time

                power = float(stats.get('power_draw', 0) or 0)
                clock = int(stats.get('clock_current', 0) or 0)
                gpu_util = int(stats.get('gpu_util', 0) or 0)

                max_power = max(max_power, power)
                max_clock = max(max_clock, clock)
                max_gpu_util = max(max_gpu_util, gpu_util)

                power_str = f"{power:.1f}W"
                power_limit = stats.get('power_limit', '?')

                # Warn if power is low
                warning = ""
                if power < 50 and gpu_util > 50:
                    warning = " ⚠️ LOW POWER!"

                print(f"{elapsed:>7.1f}s  {stats.get('temp', '?'):>4}C  {power_str:>5}/{power_limit}W  {clock:>5} MHz  {gpu_util:>4}%  {stats.get('encoder_util', '?'):>4}%  {stats.get('decoder_util', '?'):>4}%  {stats.get('pstate', '?'):<6}{warning}")

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n" + "=" * 80)
        print("SUMMARY:")
        print(f"  Max Power Draw: {max_power:.1f}W")
        print(f"  Max Clock: {max_clock} MHz")
        print(f"  Max GPU Utilization: {max_gpu_util}%")

        if max_power < 50:
            print("\n⚠️  WARNING: Max power was very low!")
            print("   Possible causes:")
            print("   - GPU not being used properly")
            print("   - Power limit set too low")
            print("   - PCIe power issue")
            print("   - GPU in power saving mode")

        if max_clock < 1500:
            print("\n⚠️  WARNING: GPU clock stayed low!")
            print("   GPU may not be boosting properly")

        print("=" * 80)

if __name__ == '__main__':
    main()
