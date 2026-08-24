import asyncio
import os
import uuid
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Optional

import aiofiles
from fastapi import (
    FastAPI, UploadFile, File, Form, HTTPException, Request,
    WebSocket, WebSocketDisconnect, status
)
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import (
    UPLOAD_DIR, CONVERTED_DIR, STATIC_DIR, MAX_UPLOAD_SIZE_BYTES,
    MAX_UPLOAD_SIZE_MB, SUPPORTED_OUTPUT_FORMATS, FILE_TTL_SECONDS
)
from services.file_sniffer import sniff_file_header
from services.ffmpeg_engine import probe_media_file, get_ffmpeg_binary
from services.url_extractor import extract_url_metadata
from services.job_queue import queue_manager
from services.security import (
    check_rate_limit, verify_signed_token, sanitize_safe_path
)
from services.cleaner import run_periodic_cleanup

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("OmniconvertAPI")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: start worker pool and cleanup daemon
    logger.info("Initializing Omniconvert server...")
    await queue_manager.start_workers()
    cleanup_task = asyncio.create_task(run_periodic_cleanup())
    yield
    # Shutdown
    logger.info("Shutting down Omniconvert server...")
    cleanup_task.cancel()
    await queue_manager.stop_workers()


app = FastAPI(
    title="Omniconvert API",
    description="High-performance media conversion & URL downloader service",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Request Models
class InspectUrlRequest(BaseModel):
    url: str = Field(..., description="Target media URL (YouTube, Vimeo, SoundCloud, Twitter, etc.)")
    tos_agreed: bool = Field(..., description="User confirms ownership or permission to process the media")


class CreateJobRequest(BaseModel):
    source_type: str = Field(..., description="'upload' or 'url'")
    target_format: str = Field(..., description="Target format e.g. mp3, mp4, wav, aac, webm, gif")
    options: Dict[str, Any] = Field(default_factory=dict, description="Resolution, bitrate, codec, gif settings")
    file_id: Optional[str] = None
    url: Optional[str] = None
    original_filename: Optional[str] = None
    tos_agreed: bool = Field(True, description="TOS acceptance check")


# Endpoints
@app.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "engine": "FFmpeg",
        "ffmpeg_binary": get_ffmpeg_binary(),
        "supported_formats": list(SUPPORTED_OUTPUT_FORMATS.keys()),
        "max_upload_size_mb": MAX_UPLOAD_SIZE_MB,
        "ttl_seconds": FILE_TTL_SECONDS
    }


@app.post("/api/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    tos_agreed: bool = Form(...)
):
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_rate_limit(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait a minute before uploading again."
        )

    if not tos_agreed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must agree to the Terms of Service confirming you have rights to process this content."
        )

    file_id = f"up_{uuid.uuid4().hex[:12]}"
    raw_ext = Path(file.filename or "media").suffix or ".bin"
    temp_path = UPLOAD_DIR / f"{file_id}{raw_ext}"

    # Stream write with size limit checking
    total_bytes = 0
    try:
        async with aiofiles.open(temp_path, "wb") as out_file:
            while chunk := await file.read(1024 * 1024): # 1MB chunks
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                    temp_path.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds maximum allowed size of {MAX_UPLOAD_SIZE_MB}MB."
                    )
                await out_file.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"Failed to write uploaded file: {e}")

    # Sniff file headers and magic bytes
    sniff_res = sniff_file_header(temp_path)
    if not sniff_res.get("valid"):
        temp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=sniff_res.get("error", "Invalid or unsupported media format.")
        )

    # Rename temp path to use detected real extension if different
    detected_ext = sniff_res.get("detected_ext") or "bin"
    target_path = UPLOAD_DIR / f"{file_id}.{detected_ext}"
    if temp_path != target_path:
        temp_path.rename(target_path)

    # Probe duration and streams
    probe_data = await probe_media_file(target_path)

    return {
        "file_id": file_id,
        "filename": file.filename,
        "detected_mime": sniff_res.get("detected_mime"),
        "detected_ext": detected_ext,
        "media_type": sniff_res.get("media_type"),
        "size_bytes": total_bytes,
        "duration_seconds": probe_data.get("duration", 0.0),
        "probe": probe_data
    }


@app.post("/api/url/inspect")
async def inspect_url_endpoint(req: InspectUrlRequest, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please wait a minute.")

    if not req.tos_agreed:
        raise HTTPException(status_code=400, detail="You must agree to the Terms of Service.")

    url = req.url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid URL protocol. Must start with http:// or https://")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, extract_url_metadata, url)

    if not result.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error", "Unable to extract media information from this URL.")
        )

    return result


@app.post("/api/jobs/create")
async def create_conversion_job(req: CreateJobRequest, request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")

    if not req.tos_agreed:
        raise HTTPException(status_code=400, detail="You must agree to the Terms of Service.")

    target_fmt = req.target_format.lower()
    if target_fmt not in SUPPORTED_OUTPUT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{target_fmt}'. Supported: {list(SUPPORTED_OUTPUT_FORMATS.keys())}"
        )

    if req.source_type == "upload":
        if not req.file_id:
            raise HTTPException(status_code=400, detail="file_id is required for upload source.")
        # Verify file exists
        matches = list(UPLOAD_DIR.glob(f"{req.file_id}.*"))
        if not matches:
            raise HTTPException(status_code=404, detail="Uploaded source file not found or expired.")
    elif req.source_type == "url":
        if not req.url:
            raise HTTPException(status_code=400, detail="url is required for url source.")
    else:
        raise HTTPException(status_code=400, detail="source_type must be 'upload' or 'url'.")

    job = queue_manager.create_job(
        source_type=req.source_type,
        target_format=target_fmt,
        options=req.options,
        file_id=req.file_id,
        source_url=req.url,
        original_filename=req.original_filename
    )

    return job.to_dict()


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = queue_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job.to_dict()


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job_endpoint(job_id: str):
    success = queue_manager.cancel_job(job_id)
    if not success:
        raise HTTPException(status_code=400, detail="Job could not be cancelled or has already completed.")
    return {"message": "Job cancellation initiated."}


@app.get("/api/download/{token}")
async def download_file_endpoint(token: str):
    # Extract file_id from token prefix
    parts = token.split("--")
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail="Malformed download token.")

    file_name = parts[0]
    is_valid, resolved_id, err_msg = verify_signed_token(token, file_name)
    if not is_valid:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=err_msg or "Invalid download token.")

    file_path = CONVERTED_DIR / file_name
    try:
        safe_path = sanitize_safe_path(file_path)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Forbidden file path access.")

    if not safe_path.exists():
        raise HTTPException(status_code=404, detail="The requested file has expired and was removed from storage.")

    # Determine media mime type
    ext = safe_path.suffix.lstrip(".").lower()
    fmt_info = SUPPORTED_OUTPUT_FORMATS.get(ext, {})
    media_mime = fmt_info.get("mime", "application/octet-stream")

    return FileResponse(
        path=safe_path,
        media_type=media_mime,
        filename=file_name,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Content-Disposition": f'attachment; filename="{file_name}"'
        }
    )


@app.websocket("/api/ws/{job_id}")
async def websocket_job_updates(websocket: WebSocket, job_id: str):
    await websocket.accept()
    job = queue_manager.get_job(job_id)
    if not job:
        await websocket.send_json({"error": "Job not found", "job_id": job_id})
        await websocket.close()
        return

    # Send immediate state
    await websocket.send_json(job.to_dict())

    # Listener function
    async def listener_callback(data: dict):
        try:
            await websocket.send_json(data)
        except Exception:
            pass

    job.listeners.add(listener_callback)

    try:
        while True:
            # Keep alive and listen for client actions (e.g. cancel)
            msg = await websocket.receive_text()
            if msg == "cancel":
                queue_manager.cancel_job(job_id)
    except WebSocketDisconnect:
        pass
    finally:
        job.listeners.discard(listener_callback)


# Mount Static Files and Root Route
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def serve_index():
    index_path = BASE_DIR / "index.html"
    if not index_path.exists():
        index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    return FileResponse(index_path)
