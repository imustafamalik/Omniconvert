import asyncio
import os
from pathlib import Path
from typing import Dict, Any, Optional, Callable
import yt_dlp
from config import UPLOAD_DIR, MAX_DURATION_SECONDS
from services.ffmpeg_engine import get_ffmpeg_binary


def get_base_ydl_opts() -> Dict[str, Any]:
    """Returns resilient base options for yt-dlp with mobile client rotation."""
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "geo_bypass": True,
        "ffmpeg_location": get_ffmpeg_binary(),
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "mweb", "web"],
            }
        },
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
    }


def extract_url_metadata(url: str) -> Dict[str, Any]:
    """
    Extracts metadata from YouTube, Vimeo, TikTok, SoundCloud, Twitter/X, Reddit, or direct URLs.
    Does NOT download the file yet.
    """
    ydl_opts = get_base_ydl_opts()
    ydl_opts.update({
        "skip_download": True,
        "extract_flat": False,
    })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError("Could not extract metadata from the provided URL.")

            # Duration check
            duration = info.get("duration") or 0
            if duration > MAX_DURATION_SECONDS:
                raise ValueError(
                    f"Media duration ({duration // 60} min) exceeds maximum allowed limit ({MAX_DURATION_SECONDS // 60} min)."
                )

            # Available resolutions
            formats = info.get("formats", [])
            resolutions = set()
            has_video = False
            has_audio = False

            for f in formats:
                height = f.get("height")
                if height:
                    has_video = True
                    if height >= 2160:
                        resolutions.add("4K")
                    elif height >= 1080:
                        resolutions.add("1080p")
                    elif height >= 720:
                        resolutions.add("720p")
                    elif height >= 480:
                        resolutions.add("480p")
                    elif height >= 360:
                        resolutions.add("360p")
                if f.get("acodec") and f.get("acodec") != "none":
                    has_audio = True

            # Sort resolutions
            order = ["4K", "1080p", "720p", "480p", "360p"]
            sorted_res = [r for r in order if r in resolutions]
            if not sorted_res and has_video:
                sorted_res = ["Original"]

            return {
                "valid": True,
                "url": url,
                "title": info.get("title", "Untitled Media"),
                "uploader": info.get("uploader") or info.get("channel") or "Unknown Source",
                "duration": duration,
                "thumbnail": info.get("thumbnail"),
                "description": (info.get("description") or "")[:200],
                "available_resolutions": sorted_res,
                "has_video": has_video,
                "has_audio": has_audio or not has_video,
                "extractor": info.get("extractor_key", "Generic"),
                "error": None
            }

    except Exception as e:
        err_msg = str(e)
        if "unavailable" in err_msg.lower():
            err_msg = "This video is unavailable or has been removed from YouTube."
        elif "DRM" in err_msg or "protected" in err_msg.lower():
            err_msg = "Content is DRM-protected and cannot be downloaded/processed."
        elif "Private video" in err_msg or "private" in err_msg.lower():
            err_msg = "This video is set to private by the creator."
        elif "Sign in" in err_msg or "bot" in err_msg.lower():
            err_msg = "YouTube bot verification triggered. Please try another video or direct media link."
        return {
            "valid": False,
            "url": url,
            "error": err_msg
        }


async def download_source_url(
    url: str,
    target_filename_base: str,
    target_format: str = "mp4",
    resolution: Optional[str] = None,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    cancel_event: Optional[asyncio.Event] = None
) -> Path:
    """
    Downloads media from third-party URL into storage/uploads/ asynchronously.
    Selects optimal stream (audio-only or requested resolution) to minimize transfer time.
    """
    output_template = str(UPLOAD_DIR / f"{target_filename_base}.%(ext)s")

    # Format selector optimization
    is_audio_only = target_format.lower() in ["mp3", "wav", "aac", "flac", "ogg", "m4a"]
    if is_audio_only:
        fmt_string = "bestaudio/best"
    else:
        res_map = {"360p": 360, "480p": 480, "720p": 720, "1080p": 1080, "4k": 2160}
        h_max = res_map.get(str(resolution).lower()) if resolution else None
        if h_max:
            fmt_string = f"bestvideo[height<={h_max}]+bestaudio/best[height<={h_max}]/best"
        else:
            fmt_string = "bestvideo+bestaudio/best"

    def progress_hook(d):
        if cancel_event and cancel_event.is_set():
            raise Exception("Download cancelled by user.")
            
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes", 0)
            percent = (downloaded / total * 100) if total > 0 else 0
            speed = d.get("speed") or 0
            speed_str = f"{speed / 1024 / 1024:.1f} MB/s" if speed > 0 else "N/A"
            eta = d.get("eta") or 0

            if on_progress:
                on_progress({
                    "stage": f"Downloading source stream ({speed_str})...",
                    "percent": round(percent, 1),
                    "speed": speed_str,
                    "eta_seconds": eta
                })

    ydl_opts = get_base_ydl_opts()
    ydl_opts.update({
        "outtmpl": output_template,
        "format": fmt_string,
        "progress_hooks": [progress_hook],
        "overwrites": True,
    })

    loop = asyncio.get_running_loop()

    def run_ydl():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    await loop.run_in_executor(None, run_ydl)

    # Find the downloaded file
    matching_files = list(UPLOAD_DIR.glob(f"{target_filename_base}.*"))
    if not matching_files:
        raise FileNotFoundError("Downloaded source file could not be located on disk.")

    return matching_files[0]
