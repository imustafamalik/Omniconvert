import filetype
from pathlib import Path
from typing import Dict, Any, Optional

MAGIC_SIGNATURES = {
    # MP4 / M4A / MOV
    b"ftyp": ("video/mp4", "mp4", "video"),
    b"moov": ("video/quicktime", "mov", "video"),
    # RIFF containers (WAV / AVI / WEBP)
    b"RIFF": ("audio/wav", "wav", "audio"),
    # Matroska / WebM
    b"\x1a\x45\xdf\xa3": ("video/webm", "webm", "video"),
    # FLAC
    b"fLaC": ("audio/flac", "flac", "audio"),
    # Ogg
    b"OggS": ("audio/ogg", "ogg", "audio"),
    # MP3 (ID3v2 or Frame Sync 0xFF 0xFB / 0xFA / 0xF3 / 0xF2)
    b"ID3": ("audio/mpeg", "mp3", "audio"),
    # MPEG Transport Stream
    b"\x47": ("video/mp2t", "ts", "video"),
}

AUDIO_MIMES = {
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/x-wav", "audio/wave",
    "audio/aac", "audio/flac", "audio/ogg", "audio/x-m4a", "audio/mp4",
    "audio/webm", "audio/opus", "audio/vorbis", "audio/aiff"
}

VIDEO_MIMES = {
    "video/mp4", "video/webm", "video/quicktime", "video/x-matroska",
    "video/x-msvideo", "video/mpeg", "video/ogg", "video/3gpp",
    "video/x-flv", "video/avi"
}

def sniff_file_header(file_path: Path) -> Dict[str, Any]:
    """
    Inspects magic bytes and headers of a file to determine true MIME type
    and media classification, protecting against extension spoofing.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    file_size = file_path.stat().st_size
    if file_size == 0:
        return {
            "valid": False,
            "error": "Uploaded file is empty (0 bytes)."
        }
    
    # Read the first 4KB for header analysis
    with open(file_path, "rb") as f:
        header = f.read(4096)
        
    # 1. Use filetype library
    kind = filetype.guess(header)
    detected_mime: Optional[str] = kind.mime if kind else None
    detected_ext: Optional[str] = kind.extension if kind else None
    media_type: Optional[str] = None
    
    if kind:
        if kind.mime in AUDIO_MIMES or kind.mime.startswith("audio/"):
            media_type = "audio"
        elif kind.mime in VIDEO_MIMES or kind.mime.startswith("video/"):
            media_type = "video"
            
    # 2. Fallback to custom magic byte sniffers
    if not detected_mime or not media_type:
        # Check MP3 sync frames
        if header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
            detected_mime = "audio/mpeg"
            detected_ext = "mp3"
            media_type = "audio"
        elif b"ftyp" in header[:32]:
            detected_mime = "video/mp4"
            detected_ext = "mp4"
            media_type = "video"
        elif header.startswith(b"RIFF") and len(header) >= 12:
            fourcc = header[8:12]
            if fourcc == b"WAVE":
                detected_mime = "audio/wav"
                detected_ext = "wav"
                media_type = "audio"
            elif fourcc == b"AVI ":
                detected_mime = "video/x-msvideo"
                detected_ext = "avi"
                media_type = "video"
        elif header.startswith(b"\x1a\x45\xdf\xa3"):
            detected_mime = "video/webm"
            detected_ext = "webm"
            media_type = "video"
        elif header.startswith(b"fLaC"):
            detected_mime = "audio/flac"
            detected_ext = "flac"
            media_type = "audio"
        elif header.startswith(b"OggS"):
            detected_mime = "audio/ogg"
            detected_ext = "ogg"
            media_type = "audio"

    if not media_type or not detected_mime:
        return {
            "valid": False,
            "detected_mime": detected_mime or "unknown/binary",
            "detected_ext": detected_ext or "unknown",
            "media_type": "unknown",
            "size_bytes": file_size,
            "error": "Unsupported or unrecognized media format. Please upload a valid audio or video file."
        }

    return {
        "valid": True,
        "detected_mime": detected_mime,
        "detected_ext": detected_ext,
        "media_type": media_type,
        "size_bytes": file_size
    }
