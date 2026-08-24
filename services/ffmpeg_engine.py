import asyncio
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from config import BASE_DIR

BIN_DIR = BASE_DIR / "bin"
BIN_DIR.mkdir(parents=True, exist_ok=True)

try:
    import imageio_ffmpeg
    raw_exe = imageio_ffmpeg.get_ffmpeg_exe()
    target_exe = BIN_DIR / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if not target_exe.exists() and os.path.exists(raw_exe):
        try:
            shutil.copyfile(raw_exe, target_exe)
        except Exception:
            pass
    FFMPEG_BIN = str(target_exe) if target_exe.exists() else raw_exe
except Exception:
    FFMPEG_BIN = shutil.which("ffmpeg") or "ffmpeg"

# Ensure bin directory is in system PATH
bin_dir_str = str(BIN_DIR.resolve())
if bin_dir_str not in os.environ.get("PATH", ""):
    os.environ["PATH"] = bin_dir_str + os.pathsep + os.environ.get("PATH", "")


def get_ffmpeg_binary() -> str:
    """Returns absolute path to the FFmpeg binary."""
    return FFMPEG_BIN


def get_ffmpeg_dir() -> str:
    """Returns directory containing FFmpeg binary."""
    return str(BIN_DIR.resolve())


async def probe_media_file(file_path: Path) -> Dict[str, Any]:
    """
    Probes media file metadata (duration, resolution, codecs, bitrate) using FFmpeg.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    # Use ffmpeg -i <file> and inspect stderr
    cmd = [get_ffmpeg_binary(), "-hide_banner", "-i", str(file_path)]
    
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    _, stderr_bytes = await proc.communicate()
    output = stderr_bytes.decode("utf-8", errors="ignore")

    info: Dict[str, Any] = {
        "duration": 0.0,
        "bitrate_kbps": None,
        "has_video": False,
        "has_audio": False,
        "video": None,
        "audio": None
    }

    # Extract Duration: 00:01:23.45, start: 0.000000, bitrate: 1420 kb/s
    dur_match = re.search(r"Duration:\s*(\d{2}):(\d{2}):(\d{2}\.\d+)", output)
    if dur_match:
        h, m, s = dur_match.groups()
        info["duration"] = int(h) * 3600 + int(m) * 60 + float(s)

    bitrate_match = re.search(r"bitrate:\s*(\d+)\s*kb/s", output)
    if bitrate_match:
        info["bitrate_kbps"] = int(bitrate_match.group(1))

    # Extract Video Stream: Stream #0:0: Video: h264 (High), yuv420p, 1920x1080 [SAR 1:1 DAR 16:9], 29.97 fps
    video_match = re.search(
        r"Stream #\d+:\d+(?:\[0x\w+\])?(?:\([a-z]+\))?:\s*Video:\s*([a-zA-Z0-9_\-]+).*?,\s*(\d{2,5})x(\d{2,5})",
        output
    )
    if video_match:
        codec, width, height = video_match.groups()
        fps_match = re.search(r"(\d+(?:\.\d+)?)\s*fps", output)
        fps = float(fps_match.group(1)) if fps_match else 30.0
        info["has_video"] = True
        info["video"] = {
            "codec": codec,
            "width": int(width),
            "height": int(height),
            "resolution": f"{width}x{height}",
            "fps": fps
        }

    # Extract Audio Stream: Stream #0:1: Audio: aac (LC), 48000 Hz, stereo, fltp, 128 kb/s
    audio_match = re.search(
        r"Stream #\d+:\d+(?:\[0x\w+\])?(?:\([a-z]+\))?:\s*Audio:\s*([a-zA-Z0-9_\-]+).*?,\s*(\d+)\s*Hz",
        output
    )
    if audio_match:
        codec, hz = audio_match.groups()
        channels = "stereo" if "stereo" in output else ("mono" if "mono" in output else "unknown")
        info["has_audio"] = True
        info["audio"] = {
            "codec": codec,
            "sample_rate": int(hz),
            "channels": channels
        }

    return info


def build_ffmpeg_command(
    input_path: Path,
    output_path: Path,
    target_format: str,
    options: Dict[str, Any]
) -> List[str]:
    """
    Constructs a safe, parameterized FFmpeg command vector.
    Never uses shell strings to prevent command injection.
    """
    target_format = target_format.lower()
    cmd = [
        get_ffmpeg_binary(),
        "-y", # Overwrite output if exists
        "-hide_banner",
        "-i", str(input_path),
    ]

    # Strip metadata unless explicitly opted out
    if options.get("strip_metadata", True):
        cmd.extend(["-map_metadata", "-1"])

    # 1. GIF Output (2-pass high quality palettegen / paletteuse)
    if target_format == "gif":
        fps = int(options.get("gif_fps", 15))
        width = int(options.get("gif_width", 480))
        vf_filter = f"fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        cmd.extend(["-vf", vf_filter, "-loop", "0"])

    # 2. Audio-only target formats
    elif target_format in ["mp3", "wav", "aac", "flac", "ogg", "m4a"]:
        cmd.append("-vn") # Discard video stream
        
        # Audio Codec
        if target_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame"])
        elif target_format == "wav":
            cmd.extend(["-c:a", "pcm_s16le"])
        elif target_format in ["aac", "m4a"]:
            cmd.extend(["-c:a", "aac"])
        elif target_format == "flac":
            cmd.extend(["-c:a", "flac"])
        elif target_format == "ogg":
            cmd.extend(["-c:a", "libvorbis"])

        # Audio Bitrate
        audio_bitrate = options.get("audio_bitrate")
        if audio_bitrate and target_format not in ["wav", "flac"]:
            cmd.extend(["-b:a", str(audio_bitrate)])

        # Sample Rate
        sample_rate = options.get("audio_sample_rate")
        if sample_rate:
            cmd.extend(["-ar", str(sample_rate)])

        # Channels (1 = mono, 2 = stereo)
        channels = options.get("audio_channels")
        if channels:
            cmd.extend(["-ac", str(channels)])

    # 3. Video Target Formats (MP4, WebM, MOV, MKV, AVI)
    else:
        # Video Resolution scaling
        resolution = options.get("resolution", "original")
        scale_filter = None
        if resolution == "4k":
            scale_filter = "scale='min(3840,iw)':-2"
        elif resolution == "1080p":
            scale_filter = "scale='min(1920,iw)':-2"
        elif resolution == "720p":
            scale_filter = "scale='min(1280,iw)':-2"
        elif resolution == "480p":
            scale_filter = "scale='min(854,iw)':-2"
        elif resolution == "360p":
            scale_filter = "scale='min(640,iw)':-2"

        if scale_filter:
            cmd.extend(["-vf", scale_filter])

        # Video Codec
        video_codec = options.get("video_codec")
        if not video_codec:
            if target_format == "webm":
                video_codec = "libvpx-vp9"
            else:
                video_codec = "libx264"
        cmd.extend(["-c:v", video_codec])

        # Video Bitrate / Preset
        if video_codec in ["libx264", "libx265"]:
            cmd.extend(["-preset", "fast", "-crf", "23"])
            if target_format == "mp4":
                cmd.extend(["-movflags", "+faststart"])
        elif video_codec == "libvpx-vp9":
            cmd.extend(["-crf", "30", "-b:v", "0"])

        # Audio stream for video container
        if target_format == "webm":
            cmd.extend(["-c:a", "libopus", "-b:a", "128k"])
        else:
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])

        # Frame rate if specified
        fps = options.get("fps")
        if fps:
            cmd.extend(["-r", str(fps)])

    # Add progress reporting to pipe
    cmd.extend(["-progress", "pipe:1", str(output_path)])
    return cmd


async def execute_ffmpeg_conversion(
    cmd: List[str],
    total_duration_sec: float,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: Optional[asyncio.Event] = None
) -> Dict[str, Any]:
    """
    Executes FFmpeg with real-time stdout progress parsing and cancellation support.
    """
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    progress_data = {
        "percent": 0.0,
        "fps": 0.0,
        "speed": "1.0x",
        "time_elapsed": 0.0,
        "eta_seconds": 0.0,
        "stage": "Converting..."
    }

    async def monitor_cancellation():
        if cancel_event:
            await cancel_event.wait()
            try:
                process.terminate()
                await asyncio.sleep(0.5)
                if process.returncode is None:
                    process.kill()
            except Exception:
                pass

    cancel_task = asyncio.create_task(monitor_cancellation())

    try:
        assert process.stdout is not None
        while True:
            line_bytes = await process.stdout.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8", errors="ignore").strip()
            if "=" in line:
                key, val = line.split("=", 1)
                key, val = key.strip(), val.strip()

                if key == "out_time_us":
                    try:
                        time_sec = int(val) / 1_000_000.0
                        progress_data["time_elapsed"] = round(time_sec, 2)
                        if total_duration_sec > 0:
                            percent = min(99.5, round((time_sec / total_duration_sec) * 100, 1))
                            progress_data["percent"] = percent
                            if percent > 0:
                                eta = max(0.0, round((total_duration_sec - time_sec), 1))
                                progress_data["eta_seconds"] = eta
                    except ValueError:
                        pass
                elif key == "fps":
                    try:
                        progress_data["fps"] = float(val)
                    except ValueError:
                        pass
                elif key == "speed":
                    progress_data["speed"] = val
                elif key == "progress" and val == "end":
                    progress_data["percent"] = 100.0
                    progress_data["eta_seconds"] = 0.0

                if on_progress:
                    on_progress(dict(progress_data))

        _, stderr_bytes = await process.communicate()
        stderr_msg = stderr_bytes.decode("utf-8", errors="ignore")

        if cancel_event and cancel_event.is_set():
            return {"success": False, "cancelled": True, "error": "Job was cancelled by user."}

        if process.returncode != 0:
            return {
                "success": False,
                "cancelled": False,
                "error": f"FFmpeg failed with code {process.returncode}: {stderr_msg[-600:]}"
            }

        return {"success": True, "cancelled": False, "error": None}

    finally:
        cancel_task.cancel()
