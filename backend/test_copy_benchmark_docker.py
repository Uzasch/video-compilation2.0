"""
Test different copy methods in Docker Linux environment
Compares: rsync, cp, shutil (both sequential and parallel)
Usage: docker exec video-compilation-backend python /app/test_copy_benchmark_docker.py
"""
import os
import shutil
import time
import subprocess
import json
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Video IDs to test with
VIDEO_IDS = [
    "1b9AcqPFTz8",
    "J2htsBo8WgA",
    "-Vpx09PpcNU",
    "B9GD1SFd6BM",
    "6PKp0yVRsY8",
]

CHANNEL_NAME = "HooplaKidz Toon"
NUM_RUNS = 3  # Number of runs per method

class CopyMethodBenchmark:
    def __init__(self, video_ids, channel_name, num_runs=3):
        self.video_ids = video_ids
        self.channel_name = channel_name
        self.num_runs = num_runs
        self.test_base = Path("/app/temp/copy_benchmark")
        self.source_files = []

    def setup(self):
        """Get video paths from BigQuery"""
        from services.bigquery import get_videos_info_by_ids

        print("="*80)
        print("COPY METHOD BENCHMARK - DOCKER/LINUX")
        print("="*80)
        print(f"Channel: {self.channel_name}")
        print(f"Videos to test: {len(self.video_ids)}")
        print(f"Runs per method: {self.num_runs}")

        print("\nFetching video paths from BigQuery...")
        videos_info = get_videos_info_by_ids(self.video_ids)

        if not videos_info:
            raise Exception("No video paths found")

        # Normalize paths for Docker
        from services.storage import normalize_paths

        self.source_files = []
        for video_id, info in videos_info.items():
            normalized = normalize_paths([info['path']])[0]
            if os.path.exists(normalized):
                self.source_files.append({
                    'video_id': video_id,
                    'path': normalized,
                    'title': info['title'],
                    'size_mb': os.path.getsize(normalized) / (1024 * 1024)
                })

        print(f"Found {len(self.source_files)} accessible video files")
        total_size = sum(f['size_mb'] for f in self.source_files)
        print(f"Total size: {total_size:.2f} MB\n")

        return len(self.source_files) > 0

    def check_commands(self):
        """Check which copy commands are available"""
        print("Checking available copy commands...")

        commands = {
            'rsync': False,
            'cp': False,
            'parallel': False
        }

        # Check rsync
        try:
            result = subprocess.run(['rsync', '--version'],
                                   capture_output=True, timeout=5)
            commands['rsync'] = result.returncode == 0
        except:
            pass

        # Check cp
        try:
            result = subprocess.run(['cp', '--version'],
                                   capture_output=True, timeout=5)
            commands['cp'] = result.returncode == 0
        except:
            pass

        # Check GNU parallel
        try:
            result = subprocess.run(['parallel', '--version'],
                                   capture_output=True, timeout=5)
            commands['parallel'] = result.returncode == 0
        except:
            pass

        for cmd, available in commands.items():
            status = "[OK]" if available else "[NOT FOUND]"
            print(f"  {status} {cmd}")

        print()
        return commands

    # ===== RSYNC METHODS =====
    def copy_with_rsync(self, src_file, dest_dir):
        """Copy single file with rsync"""
        file_size = os.path.getsize(src_file)
        dest_path = Path(dest_dir) / Path(src_file).name

        cmd = [
            'rsync', '-av',
            '--timeout=300',
            '--contimeout=60',
            src_file,
            str(dest_path)
        ]

        start = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=360)
            elapsed = time.time() - start
            success = result.returncode == 0
            return {'size': file_size, 'time': elapsed, 'success': success}
        except Exception as e:
            elapsed = time.time() - start
            return {'size': file_size, 'time': elapsed, 'success': False, 'error': str(e)}

    def test_rsync_sequential(self, dest_dir, run_num):
        """Test rsync sequential copying"""
        method = 'rsync_sequential'
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"  [{method}] Run {run_num}/{self.num_runs}...", end='', flush=True)

        start_time = time.time()
        total_bytes = 0

        for file_info in self.source_files:
            result = self.copy_with_rsync(file_info['path'], dest_dir)
            if result['success']:
                total_bytes += result['size']

        elapsed = time.time() - start_time
        speed_mbps = (total_bytes / elapsed) / (1024 * 1024) if elapsed > 0 else 0

        print(f" {elapsed:.2f}s @ {speed_mbps:.2f} MB/s")
        return {'time': elapsed, 'speed_mbps': speed_mbps, 'bytes': total_bytes}

    def test_rsync_parallel(self, dest_dir, run_num):
        """Test rsync parallel copying"""
        method = 'rsync_parallel'
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"  [{method}] Run {run_num}/{self.num_runs}...", end='', flush=True)

        start_time = time.time()
        total_bytes = 0

        with ThreadPoolExecutor(max_workers=len(self.source_files)) as executor:
            futures = {executor.submit(self.copy_with_rsync, f['path'], dest_dir): f
                      for f in self.source_files}

            for future in as_completed(futures):
                result = future.result()
                if result['success']:
                    total_bytes += result['size']

        elapsed = time.time() - start_time
        speed_mbps = (total_bytes / elapsed) / (1024 * 1024) if elapsed > 0 else 0

        print(f" {elapsed:.2f}s @ {speed_mbps:.2f} MB/s")
        return {'time': elapsed, 'speed_mbps': speed_mbps, 'bytes': total_bytes}

    # ===== CP METHODS =====
    def copy_with_cp(self, src_file, dest_dir):
        """Copy single file with cp"""
        file_size = os.path.getsize(src_file)
        dest_path = Path(dest_dir) / Path(src_file).name

        cmd = ['cp', src_file, str(dest_path)]

        start = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=300)
            elapsed = time.time() - start
            success = result.returncode == 0
            return {'size': file_size, 'time': elapsed, 'success': success}
        except Exception as e:
            elapsed = time.time() - start
            return {'size': file_size, 'time': elapsed, 'success': False, 'error': str(e)}

    def test_cp_sequential(self, dest_dir, run_num):
        """Test cp sequential copying"""
        method = 'cp_sequential'
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"  [{method}] Run {run_num}/{self.num_runs}...", end='', flush=True)

        start_time = time.time()
        total_bytes = 0

        for file_info in self.source_files:
            result = self.copy_with_cp(file_info['path'], dest_dir)
            if result['success']:
                total_bytes += result['size']

        elapsed = time.time() - start_time
        speed_mbps = (total_bytes / elapsed) / (1024 * 1024) if elapsed > 0 else 0

        print(f" {elapsed:.2f}s @ {speed_mbps:.2f} MB/s")
        return {'time': elapsed, 'speed_mbps': speed_mbps, 'bytes': total_bytes}

    def test_cp_parallel(self, dest_dir, run_num):
        """Test cp parallel copying"""
        method = 'cp_parallel'
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"  [{method}] Run {run_num}/{self.num_runs}...", end='', flush=True)

        start_time = time.time()
        total_bytes = 0

        with ThreadPoolExecutor(max_workers=len(self.source_files)) as executor:
            futures = {executor.submit(self.copy_with_cp, f['path'], dest_dir): f
                      for f in self.source_files}

            for future in as_completed(futures):
                result = future.result()
                if result['success']:
                    total_bytes += result['size']

        elapsed = time.time() - start_time
        speed_mbps = (total_bytes / elapsed) / (1024 * 1024) if elapsed > 0 else 0

        print(f" {elapsed:.2f}s @ {speed_mbps:.2f} MB/s")
        return {'time': elapsed, 'speed_mbps': speed_mbps, 'bytes': total_bytes}

    # ===== SHUTIL METHODS =====
    def copy_with_shutil(self, src_file, dest_dir):
        """Copy single file with shutil"""
        file_size = os.path.getsize(src_file)
        dest_path = Path(dest_dir) / Path(src_file).name

        start = time.time()
        try:
            shutil.copy(src_file, str(dest_path))
            elapsed = time.time() - start
            return {'size': file_size, 'time': elapsed, 'success': True}
        except Exception as e:
            elapsed = time.time() - start
            return {'size': file_size, 'time': elapsed, 'success': False, 'error': str(e)}

    def test_shutil_sequential(self, dest_dir, run_num):
        """Test shutil sequential copying"""
        method = 'shutil_sequential'
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"  [{method}] Run {run_num}/{self.num_runs}...", end='', flush=True)

        start_time = time.time()
        total_bytes = 0

        for file_info in self.source_files:
            result = self.copy_with_shutil(file_info['path'], dest_dir)
            if result['success']:
                total_bytes += result['size']

        elapsed = time.time() - start_time
        speed_mbps = (total_bytes / elapsed) / (1024 * 1024) if elapsed > 0 else 0

        print(f" {elapsed:.2f}s @ {speed_mbps:.2f} MB/s")
        return {'time': elapsed, 'speed_mbps': speed_mbps, 'bytes': total_bytes}

    def test_shutil_parallel(self, dest_dir, run_num):
        """Test shutil parallel copying"""
        method = 'shutil_parallel'
        dest_dir.mkdir(parents=True, exist_ok=True)
        print(f"  [{method}] Run {run_num}/{self.num_runs}...", end='', flush=True)

        start_time = time.time()
        total_bytes = 0

        with ThreadPoolExecutor(max_workers=len(self.source_files)) as executor:
            futures = {executor.submit(self.copy_with_shutil, f['path'], dest_dir): f
                      for f in self.source_files}

            for future in as_completed(futures):
                result = future.result()
                if result['success']:
                    total_bytes += result['size']

        elapsed = time.time() - start_time
        speed_mbps = (total_bytes / elapsed) / (1024 * 1024) if elapsed > 0 else 0

        print(f" {elapsed:.2f}s @ {speed_mbps:.2f} MB/s")
        return {'time': elapsed, 'speed_mbps': speed_mbps, 'bytes': total_bytes}

    def run_all_tests(self, available_commands):
        """Run all available copy methods"""
        tests = []

        # Add tests based on available commands
        if available_commands['rsync']:
            tests.extend([
                ('rsync_sequential', self.test_rsync_sequential),
                ('rsync_parallel', self.test_rsync_parallel),
            ])

        if available_commands['cp']:
            tests.extend([
                ('cp_sequential', self.test_cp_sequential),
                ('cp_parallel', self.test_cp_parallel),
            ])

        # Shutil is always available
        tests.extend([
            ('shutil_sequential', self.test_shutil_sequential),
            ('shutil_parallel', self.test_shutil_parallel),
        ])

        all_results = {name: [] for name, _ in tests}

        print("="*80)
        print(f"RUNNING {self.num_runs} ITERATIONS OF EACH METHOD")
        print("="*80)

        for test_idx, (name, test_func) in enumerate(tests, 1):
            print(f"\n[TEST {test_idx}/{len(tests)}] {name.upper()}")
            print("-"*80)

            for run_num in range(1, self.num_runs + 1):
                dest_dir = self.test_base / name

                # Clean destination
                if dest_dir.exists():
                    shutil.rmtree(dest_dir, ignore_errors=True)

                # Run test
                result = test_func(dest_dir, run_num)
                all_results[name].append(result)

                # Clean after run
                if dest_dir.exists():
                    shutil.rmtree(dest_dir, ignore_errors=True)

                time.sleep(0.5)  # Brief pause

        return all_results

    def generate_report(self, all_results):
        """Generate and print benchmark report"""
        print("\n" + "="*80)
        print(f"BENCHMARK RESULTS - AVERAGED OVER {self.num_runs} RUNS")
        print("="*80)

        stats = {}
        for method, runs in all_results.items():
            times = [r['time'] for r in runs]
            speeds = [r['speed_mbps'] for r in runs]

            stats[method] = {
                'avg_time': sum(times) / len(times),
                'min_time': min(times),
                'max_time': max(times),
                'avg_speed': sum(speeds) / len(speeds),
                'runs': runs
            }

        # Print table
        print(f"\n{'Method':<25} {'Avg Time':<12} {'Min/Max':<18} {'Avg Speed':<15}")
        print("-"*80)

        # Sort by avg time (fastest first)
        sorted_methods = sorted(stats.items(), key=lambda x: x[1]['avg_time'])

        for method, data in sorted_methods:
            print(f"{method:<25} {data['avg_time']:>10.2f}s  "
                  f"{data['min_time']:>6.2f}/{data['max_time']:<6.2f}s  "
                  f"{data['avg_speed']:>10.2f} MB/s")

        # Show fastest
        fastest = sorted_methods[0]
        print(f"\n{'='*80}")
        print(f"FASTEST: {fastest[0]} @ {fastest[1]['avg_time']:.2f}s "
              f"({fastest[1]['avg_speed']:.2f} MB/s)")
        print(f"{'='*80}")

        # Sequential vs Parallel comparison
        print(f"\n{'='*80}")
        print("SEQUENTIAL vs PARALLEL COMPARISON")
        print(f"{'='*80}")

        for base in ['rsync', 'cp', 'shutil']:
            seq_key = f"{base}_sequential"
            par_key = f"{base}_parallel"

            if seq_key in stats and par_key in stats:
                seq_time = stats[seq_key]['avg_time']
                par_time = stats[par_key]['avg_time']
                improvement = ((seq_time - par_time) / seq_time) * 100

                print(f"\n{base.upper()}:")
                print(f"  Sequential: {seq_time:>6.2f}s @ {stats[seq_key]['avg_speed']:>6.2f} MB/s")
                print(f"  Parallel:   {par_time:>6.2f}s @ {stats[par_key]['avg_speed']:>6.2f} MB/s")
                print(f"  Improvement: {improvement:+.1f}% {'(parallel faster)' if improvement > 0 else '(sequential faster)'}")

        # Save results
        report_file = '/app/temp/copy_benchmark_results.json'
        report = {
            'timestamp': datetime.now().isoformat(),
            'channel': self.channel_name,
            'num_videos': len(self.source_files),
            'num_runs': self.num_runs,
            'statistics': stats
        }

        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)

        print(f"\n{'='*80}")
        print(f"Report saved to: {report_file}")
        print(f"{'='*80}")

        return stats

# ============================================================================
# Main execution
# ============================================================================
if __name__ == '__main__':
    benchmark = CopyMethodBenchmark(VIDEO_IDS, CHANNEL_NAME, NUM_RUNS)

    # Setup and get source files
    if not benchmark.setup():
        print("Failed to setup benchmark - no files found")
        exit(1)

    # Check available commands
    available_commands = benchmark.check_commands()

    # Run tests
    results = benchmark.run_all_tests(available_commands)

    # Generate report
    benchmark.generate_report(results)

    print("\n[OK] Benchmark completed!")
