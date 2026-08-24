# Omniconvert Studio 🚀

> **High-Performance Media Conversion & URL Extraction Suite**  
> Convert local audio/video files or download & transcode content from YouTube, Vimeo, social media, and web URLs with precision FFmpeg encoding and real-time WebSocket updates.

![Omniconvert Architecture](https://img.shields.io/badge/FFmpeg-7.1-indigo.svg)
![Python](https://img.shields.io/badge/Python-3.12-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

## ✨ Key Features

- **Drag-and-Drop File Uploads**: Upload videos or audio files up to 500MB with instant waveform and HTML5 video preview player.
- **Magic Bytes MIME Sniffing**: Deep content sniffing to validate genuine container signatures and prevent extension spoofing.
- **URL Auto-Fetch & Downloader**: Extract metadata and transcode streams directly from YouTube, Vimeo, TikTok, Twitter/X, SoundCloud, Reddit, and direct URLs via `yt-dlp`.
- **Target Formats**:
  - **Audio**: MP3 (up to 320 kbps), WAV (Lossless PCM), AAC, FLAC (Hi-Res), OGG (Vorbis), M4A.
  - **Video**: MP4 (H.264/H.265), WebM (VP9 + Opus), MOV (QuickTime), MKV, AVI.
  - **Animation**: High-quality 2-Pass Palettegen GIF from any video clip.
- **Custom Transcoding Tuning**: Choose resolution (4K, 1080p, 720p, 480p), video codec, audio bitrate, sample rate, channels, and frame rates.
- **Privacy & Security**:
  - Auto-strip EXIF, GPS coordinates, and camera metadata (`-map_metadata -1`).
  - Sandboxed execution without shell command injection vulnerabilities.
  - Expiring HMAC-SHA256 signed download tokens (1 hour TTL).
  - Rate limiting per IP.
- **Real-Time Progress**: Live circular and linear meters with processing speed multiplier (e.g. `2.4x`), FPS, and ETA via WebSockets.
- **Automatic Cleanup Daemon**: Background worker automatically purges temporary and converted files older than their TTL.

---

## 🛠️ Architecture

```mermaid
graph TD
    Client["Frontend Client (Glassmorphic SPA)"]
    API["FastAPI Web Server (Async Gateway & Security)"]
    Queue["Async In-Memory Job Queue"]
    Worker["Conversion Worker Pool"]
    Storage["Isolated Temporary Storage (/uploads, /converted)"]
    FFmpeg["FFmpeg 7.1 Binary"]
    YTDLP["yt-dlp Engine"]
    Cleanup["Automatic Cleanup Daemon"]

    Client -->|Upload File / Paste URL| API
    Client -->|Real-time WebSockets| API
    Client -->|Signed Token Download| API
    API -->|Validate Magic Bytes & Rate Limits| API
    API -->|Enqueue Task| Queue
    Queue -->|Process Job| Worker
    Worker -->|Execute (Safe Arg Vector)| FFmpeg
    Worker -->|Fetch Media Stream| YTDLP
    FFmpeg -->|Read / Write| Storage
    YTDLP -->|Write Source Stream| Storage
    Cleanup -->|Purge Expired Files (>1 hr)| Storage
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- Git

### 2. Clone & Install
```bash
git clone https://github.com/imustafamalik/Omniconvert.git
cd Omniconvert

# Install dependencies
pip install -r requirements.txt
```

### 3. Run Locally
```bash
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```
Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** in your browser.

---

## 🐳 Docker Deployment

### Run with Docker Compose
```bash
docker-compose up -d --build
```

---

## 🧪 Testing

Run unit and transcoding test suite:
```bash
python test_converter.py
```

Run end-to-end API pipeline tests:
```bash
python test_e2e_http.py
```

---

## 📄 License
MIT License.
