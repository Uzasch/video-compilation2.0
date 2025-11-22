from typing import List, Dict
from pathlib import Path
import subprocess
import os


def is_gpu_available() -> bool:
    """Check if NVIDIA GPU encoding is actually usable (not just compiled in)"""
    try:
        # Try to actually initialize h264_nvenc encoder
        # This will fail if CUDA/NVENC libraries aren't accessible
        result = subprocess.run(
            ['ffmpeg', '-f', 'lavfi', '-i', 'nullsrc=s=256x256:d=0.1',
             '-c:v', 'h264_nvenc', '-f', 'null', '-'],
            capture_output=True,
            text=True,
            timeout=10
        )
        # Check for common GPU/NVENC errors
        error_indicators = [
            'Cannot load libcuda',
            'Cannot load libnvidia-encode',
            'minimum required Nvidia driver',
            'No NVENC capable devices found'
        ]
        return not any(indicator in result.stderr for indicator in error_indicators)
    except Exception:
        return False


_GPU_AVAILABLE = None

def check_gpu() -> bool:
    """Check GPU availability (cached)"""
    global _GPU_AVAILABLE
    if _GPU_AVAILABLE is None:
        _GPU_AVAILABLE = is_gpu_available()
    return _GPU_AVAILABLE


def build_unified_compilation_command(
    job_items: List[Dict],
    output_path: str,
    job_id: str,
    enable_4k: bool = False
) -> List[str]:
    """
    Build FFmpeg command for unified sequence compilation.
    Handles mixed resolutions, per-video logos, and per-video text animation.

    Features:
    - Scales and pads videos/images to target resolution (maintains aspect ratio)
    - Adds black padding for 16:9 ratio
    - Supports per-video logos (overlaid at top-right)
    - Supports per-video text animation using ASS subtitles
    - Processes all item types: intro, video, transition, outro, image

    Args:
        job_items: List of job items from job_items table (ordered by position)
        output_path: Output file path
        job_id: Job ID (for temp ASS file paths)
        enable_4k: Force 4K output resolution (default: Full HD)

    Returns:
        FFmpeg command as list of strings
    """
    cmd = ['ffmpeg']

    # Track input index separately (since logos and ASS files add extra inputs)
    input_index = 0
    item_input_indices = []  # Maps item position to its input index

    # Target resolution
    target_width = 3840 if enable_4k else 1920
    target_height = 2160 if enable_4k else 1080

    filter_complex = []

    # First pass: Add all video/image inputs
    for i, item in enumerate(job_items):
        item_type = item['item_type']
        path = item['path']

        if item_type == 'image':
            # Image as video segment
            duration = item.get('duration', 5)
            cmd.extend([
                '-loop', '1',
                '-t', str(duration),
                '-i', path
            ])
        else:
            # Regular video (intro, video, transition, outro)
            cmd.extend(['-i', path])

        item_input_indices.append(input_index)
        input_index += 1

    # Second pass: Process each item with filters
    for i, item in enumerate(job_items):
        item_type = item['item_type']
        item_input_idx = item_input_indices[i]

        if item_type == 'image':
            # Scale image and add padding
            duration = item.get('duration', 5)
            filter_complex.append(
                f"[{item_input_idx}:v]scale={target_width}:{target_height}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black,"
                f"fps=30[v{i}_scaled]"
            )

            # Create silent audio for image
            filter_complex.append(
                f"anullsrc=channel_layout=stereo:sample_rate=44100,"
                f"atrim=duration={duration}[a{i}]"
            )

            video_stream = f"[v{i}_scaled]"

        else:
            # Regular video - scale and pad
            filter_complex.append(
                f"[{item_input_idx}:v]scale={target_width}:{target_height}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:black[v{i}_scaled]"
            )

            video_stream = f"[v{i}_scaled]"

        # Add logo overlay for videos (not intro, outro, transition, image)
        if item_type == 'video' and item.get('logo_path'):
            logo_path = item['logo_path']
            cmd.extend(['-i', logo_path])
            logo_input_idx = input_index
            input_index += 1

            filter_complex.append(
                f"{video_stream}[{logo_input_idx}:v]overlay=W-w-10:10[v{i}_logo]"
            )
            video_stream = f"[v{i}_logo]"

        # Add text animation for videos using ASS subtitles
        if item_type == 'video' and item.get('text_animation_text'):
            text = item['text_animation_text']
            video_duration = item.get('duration', 0)

            # Generate ASS file path
            ass_file = f"temp/{job_id}/text_{item['position']}.ass"

            # Note: ASS file should be generated before calling this function
            # Using subtitles filter for ASS overlay
            filter_complex.append(
                f"{video_stream}subtitles={ass_file}:force_style='Alignment=9,MarginR=40,MarginV=40'[v{i}_text]"
            )
            video_stream = f"[v{i}_text]"

        # Finalize video stream
        filter_complex.append(f"{video_stream}null[v{i}]")

        # Handle audio stream
        if item_type == 'image':
            # Silent audio already created above
            pass
        else:
            # Use original audio
            filter_complex.append(f"[{item_input_idx}:a]anull[a{i}]")

    # Concatenate all segments (interleave video and audio: v0,a0,v1,a1,...)
    concat_inputs = ''.join([f"[v{i}][a{i}]" for i in range(len(job_items))])
    filter_complex.append(
        f"{concat_inputs}concat=n={len(job_items)}:v=1:a=1[outv][outa]"
    )

    # Join filters
    cmd.extend(['-filter_complex', ';'.join(filter_complex)])

    # Map output streams
    cmd.extend(['-map', '[outv]', '-map', '[outa]'])

    # Check GPU availability
    use_gpu = check_gpu()

    # Encoding settings
    if enable_4k:
        if use_gpu:
            # GPU-Accelerated (Nvidia NVENC) - 4K
            cmd.extend([
                '-c:v', 'h264_nvenc',
                '-preset', 'p5',
                '-tune', 'hq',
                '-rc', 'vbr',
                '-b:v', '40M',
                '-maxrate', '50M',
                '-bufsize', '60M',
                '-profile:v', 'high',
                '-level', '5.1',
                '-pix_fmt', 'yuv420p',
                '-spatial-aq', '1',
                '-temporal-aq', '1',
            ])
        else:
            # CPU Fallback (libx264) - 4K
            cmd.extend([
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '18',
                '-profile:v', 'high',
                '-level', '5.1',
                '-pix_fmt', 'yuv420p',
            ])

        # Audio encoding (same for both)
        cmd.extend([
            '-c:a', 'aac',
            '-b:a', '320k',
            '-ar', '48000',
            '-ac', '2',
        ])
    else:
        if use_gpu:
            # GPU-Accelerated (Nvidia NVENC) - 1080p
            cmd.extend([
                '-c:v', 'h264_nvenc',
                '-preset', 'p5',
                '-tune', 'hq',
                '-rc', 'vbr',
                '-b:v', '16M',
                '-maxrate', '20M',
                '-bufsize', '24M',
                '-profile:v', 'main',
                '-level', '4.1',
                '-pix_fmt', 'yuv420p',
                '-spatial-aq', '1',
                '-temporal-aq', '1',
            ])
        else:
            # CPU Fallback (libx264) - 1080p
            cmd.extend([
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '20',
                '-profile:v', 'main',
                '-level', '4.1',
                '-pix_fmt', 'yuv420p',
            ])

        # Audio encoding (same for both)
        cmd.extend([
            '-c:a', 'aac',
            '-b:a', '320k',
            '-ar', '48000',
            '-ac', '2',
        ])

    cmd.extend([
        '-movflags', '+faststart',
        '-y',
        output_path
    ])

    return cmd


def generate_ass_subtitle_file(
    text: str,
    video_duration: float,
    output_path: str,
    letter_delay: float = 0.1,
    cycle_duration: float = 20.0,
    visible_duration: float = 10.0
) -> str:
    """
    Generate ASS subtitle file for letter-by-letter text animation.

    Args:
        text: The text to animate
        video_duration: Duration of the video in seconds
        output_path: Path to save the .ass file
        letter_delay: Seconds between each letter appearing (default: 0.1)
        cycle_duration: Seconds between animation cycles (default: 20)
        visible_duration: How long full text stays visible (default: 10)

    Returns:
        Path to the generated ASS file
    """
    # ASS subtitle header
    ass_content = f"""[Script Info]
Title: Animated Text
ScriptType: v4.00+
WrapStyle: 0
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Impact,50,&H00FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,3,9,40,40,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # Calculate number of cycles needed
    num_cycles = int(video_duration / cycle_duration) + 1

    def format_time(seconds):
        """Convert seconds to ASS time format (H:MM:SS.CS)"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = seconds % 60
        return f"{h}:{m:02d}:{s:05.2f}"

    # Generate animated text for each cycle
    for cycle in range(num_cycles):
        cycle_start = cycle * cycle_duration

        # Letter-by-letter animation
        for i in range(1, len(text) + 1):
            substring = text[:i]
            start_time = cycle_start + (i - 1) * letter_delay

            # Last letter stays until visible_duration ends
            if i == len(text):
                end_time = cycle_start + visible_duration
            else:
                end_time = cycle_start + i * letter_delay

            # Stop if we exceed video duration
            if start_time >= video_duration:
                break

            start_str = format_time(start_time)
            end_str = format_time(min(end_time, video_duration))

            # Add fade effect for smooth appearance
            ass_content += f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{{\\fad(150,0)}}{substring}\\N\n"

    # Write ASS file
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(ass_content)

    return output_path
