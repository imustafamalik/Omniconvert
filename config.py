import os
import tempfile
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# Handle Serverless / Read-only filesystems (Vercel / Lambda)
IS_VERCEL = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

if IS_VERCEL:
    TMP_DIR = Path(tempfile.gettempdir())
    STORAGE_DIR = TMP_DIR / "omniconvert_storage"
else:
    STORAGE_DIR = BASE_DIR / "storage"

UPLOAD_DIR = STORAGE_DIR / "uploads"
CONVERTED_DIR = STORAGE_DIR / "converted"

try:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    TMP_DIR = Path(tempfile.gettempdir())
    STORAGE_DIR = TMP_DIR / "omniconvert_storage"
    UPLOAD_DIR = STORAGE_DIR / "uploads"
    CONVERTED_DIR = STORAGE_DIR / "converted"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    CONVERTED_DIR.mkdir(parents=True, exist_ok=True)

# Application Limits & Settings
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", 500))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_DURATION_SECONDS = int(os.getenv("MAX_DURATION_SECONDS", 7200)) # 2 hours max
FILE_TTL_SECONDS = int(os.getenv("FILE_TTL_SECONDS", 3600)) # 1 hour expiry
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", 300)) # Clean every 5 mins
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", 3))
SECRET_KEY = os.getenv("SECRET_KEY", "omniconvert-super-secret-hmac-key-2026")

# Rate Limiting
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", 60))

# Supported Formats
SUPPORTED_OUTPUT_FORMATS = {
    # Audio
    "mp3": {"type": "audio", "mime": "audio/mpeg", "default_codec": "libmp3lame"},
    "wav": {"type": "audio", "mime": "audio/wav", "default_codec": "pcm_s16le"},
    "aac": {"type": "audio", "mime": "audio/aac", "default_codec": "aac"},
    "flac": {"type": "audio", "mime": "audio/flac", "default_codec": "flac"},
    "ogg": {"type": "audio", "mime": "audio/ogg", "default_codec": "libvorbis"},
    "m4a": {"type": "audio", "mime": "audio/mp4", "default_codec": "aac"},
    # Video
    "mp4": {"type": "video", "mime": "video/mp4", "default_codec": "libx264"},
    "webm": {"type": "video", "mime": "video/webm", "default_codec": "libvpx-vp9"},
    "mov": {"type": "video", "mime": "video/quicktime", "default_codec": "libx264"},
    "mkv": {"type": "video", "mime": "video/x-matroska", "default_codec": "libx264"},
    "avi": {"type": "video", "mime": "video/x-msvideo", "default_codec": "libx264"},
    # Animation
    "gif": {"type": "animation", "mime": "image/gif", "default_codec": "gif"}
}

ALLOWED_MIME_PATTERNS = [
    "video/",
    "audio/",
    "application/ogg",
    "application/x-matroska",
    "application/octet-stream" # For certain containers needing magic bytes check
]
