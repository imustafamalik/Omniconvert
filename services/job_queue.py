import asyncio
import uuid
import time
import os
from pathlib import Path
from typing import Dict, Any, Optional, Set, Callable
import logging

from config import (
    UPLOAD_DIR, CONVERTED_DIR, MAX_CONCURRENT_JOBS,
    SUPPORTED_OUTPUT_FORMATS, FILE_TTL_SECONDS
)
from services.ffmpeg_engine import (
    probe_media_file, build_ffmpeg_command, execute_ffmpeg_conversion
)
from services.url_extractor import download_source_url
from services.security import generate_signed_token, sanitize_safe_path

logger = logging.getLogger("OmniQueue")


class ConversionJob:
    def __init__(
        self,
        job_id: str,
        source_type: str, # "upload" or "url"
        target_format: str,
        options: Dict[str, Any],
        file_id: Optional[str] = None,
        source_url: Optional[str] = None,
        original_filename: Optional[str] = None
    ):
        self.job_id = job_id
        self.source_type = source_type
        self.target_format = target_format.lower()
        self.options = options or {}
        self.file_id = file_id
        self.source_url = source_url
        self.original_filename = original_filename or (
            f"media_download.{target_format}" if source_type == "url" else f"converted.{target_format}"
        )

        self.status = "queued" # queued, fetching_source, converting, completed, failed, cancelled
        self.stage = "Waiting in conversion queue..."
        self.progress_percent = 0.0
        self.fps = 0.0
        self.speed = "1.0x"
        self.eta_seconds = 0.0
        self.time_elapsed = 0.0
        self.error_message: Optional[str] = None
        self.created_at = time.time()
        self.completed_at: Optional[float] = None

        self.output_filename: Optional[str] = None
        self.output_file_path: Optional[Path] = None
        self.download_token: Optional[str] = None
        self.download_url: Optional[str] = None
        self.expires_at: Optional[int] = None
        self.output_size_bytes: int = 0

        self.cancel_event = asyncio.Event()
        self.listeners: Set[Callable[[Dict[str, Any]], Any]] = set()
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "stage": self.stage,
            "progress_percent": round(self.progress_percent, 1),
            "fps": round(self.fps, 1),
            "speed": self.speed,
            "eta_seconds": round(self.eta_seconds, 1),
            "time_elapsed": round(self.time_elapsed, 1),
            "error_message": self.error_message,
            "target_format": self.target_format,
            "original_filename": self.original_filename,
            "output_filename": self.output_filename,
            "output_size_bytes": self.output_size_bytes,
            "download_token": self.download_token,
            "download_url": self.download_url,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "completed_at": self.completed_at
        }

    def emit_update(self):
        data = self.to_dict()
        for listener in list(self.listeners):
            try:
                if self.loop and self.loop.is_running():
                    async def _dispatch(fn, payload):
                        try:
                            res = fn(payload)
                            if asyncio.iscoroutine(res):
                                await res
                        except Exception:
                            pass
                    try:
                        running_loop = asyncio.get_running_loop()
                        if running_loop == self.loop:
                            res = listener(data)
                            if asyncio.iscoroutine(res):
                                self.loop.create_task(res)
                        else:
                            asyncio.run_coroutine_threadsafe(_dispatch(listener, data), self.loop)
                    except RuntimeError:
                        asyncio.run_coroutine_threadsafe(_dispatch(listener, data), self.loop)
                else:
                    listener(data)
            except Exception as e:
                logger.error(f"Error notifying job listener: {e}")


class JobQueueManager:
    def __init__(self):
        self.jobs: Dict[str, ConversionJob] = {}
        self.queue: asyncio.Queue = asyncio.Queue()
        self.workers: list = []
        self._running = False

    def create_job(
        self,
        source_type: str,
        target_format: str,
        options: Dict[str, Any],
        file_id: Optional[str] = None,
        source_url: Optional[str] = None,
        original_filename: Optional[str] = None
    ) -> ConversionJob:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = ConversionJob(
            job_id=job_id,
            source_type=source_type,
            target_format=target_format,
            options=options,
            file_id=file_id,
            source_url=source_url,
            original_filename=original_filename
        )
        self.jobs[job_id] = job
        self.queue.put_nowait(job)
        return job

    def get_job(self, job_id: str) -> Optional[ConversionJob]:
        return self.jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        job = self.jobs.get(job_id)
        if not job:
            return False
        if job.status in ["completed", "failed", "cancelled"]:
            return False

        job.cancel_event.set()
        job.status = "cancelled"
        job.stage = "Cancelled by user"
        job.error_message = "Conversion was cancelled."
        job.emit_update()

        # Clean up partial output if any
        if job.output_file_path and job.output_file_path.exists():
            try:
                job.output_file_path.unlink(missing_ok=True)
            except Exception:
                pass
        return True

    async def start_workers(self):
        self._running = True
        for i in range(MAX_CONCURRENT_JOBS):
            worker_task = asyncio.create_task(self._worker_loop(i + 1))
            self.workers.append(worker_task)
        logger.info(f"Started {MAX_CONCURRENT_JOBS} background conversion workers.")

    async def stop_workers(self):
        self._running = False
        for worker in self.workers:
            worker.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)
        logger.info("All background conversion workers stopped.")

    async def _worker_loop(self, worker_id: int):
        while self._running:
            try:
                job: ConversionJob = await self.queue.get()
                if job.cancel_event.is_set():
                    self.queue.task_done()
                    continue

                await self._process_job(job, worker_id)
                self.queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker {worker_id} unexpected error: {e}")

    async def _process_job(self, job: ConversionJob, worker_id: int):
        logger.info(f"[Worker {worker_id}] Starting job {job.job_id} ({job.target_format})")
        input_path: Optional[Path] = None
        
        try:
            # 1. Resolve or Download Input Source
            if job.source_type == "url":
                job.status = "fetching_source"
                job.stage = "Downloading media stream from source URL..."
                job.emit_update()

                def on_download_progress(data):
                    job.stage = data.get("stage", "Downloading...")
                    job.progress_percent = data.get("percent", 0.0)
                    job.speed = data.get("speed", "N/A")
                    job.eta_seconds = data.get("eta_seconds", 0.0)
                    job.emit_update()

                download_base = f"url_src_{job.job_id}"
                input_path = await download_source_url(
                    url=job.source_url,
                    target_filename_base=download_base,
                    target_format=job.target_format,
                    resolution=job.options.get("resolution"),
                    on_progress=on_download_progress,
                    cancel_event=job.cancel_event
                )
            else:
                # Local upload
                matches = list(UPLOAD_DIR.glob(f"{job.file_id}.*"))
                if not matches:
                    raise FileNotFoundError("Uploaded source file was not found on server.")
                input_path = matches[0]

            if job.cancel_event.is_set():
                job.status = "cancelled"
                job.stage = "Cancelled by user"
                job.emit_update()
                return

            # 2. Probe Source File
            job.stage = "Analyzing source media streams..."
            job.emit_update()
            probe_info = await probe_media_file(input_path)
            duration_sec = probe_info.get("duration", 0.0)

            # 3. Prepare Output Path
            output_ext = job.target_format
            stem_clean = Path(job.original_filename).stem if job.original_filename else "converted"
            clean_stem = "".join(c for c in stem_clean if c.isalnum() or c in (" ", "_", "-")).strip() or "media"
            out_filename = f"{clean_stem}_{job.job_id[:8]}.{output_ext}"
            output_path = CONVERTED_DIR / out_filename
            sanitize_safe_path(output_path)

            job.output_filename = out_filename
            job.output_file_path = output_path

            # 4. Build and Run FFmpeg
            job.status = "converting"
            job.stage = "Encoding and converting media..."
            job.progress_percent = 0.0
            job.emit_update()

            cmd = build_ffmpeg_command(
                input_path=input_path,
                output_path=output_path,
                target_format=job.target_format,
                options=job.options
            )

            def on_ffmpeg_progress(pdata):
                job.progress_percent = pdata.get("percent", job.progress_percent)
                job.fps = pdata.get("fps", job.fps)
                job.speed = pdata.get("speed", job.speed)
                job.time_elapsed = pdata.get("time_elapsed", job.time_elapsed)
                job.eta_seconds = pdata.get("eta_seconds", job.eta_seconds)
                job.stage = f"Encoding ({job.speed}) • ETA {int(job.eta_seconds)}s"
                job.emit_update()

            result = await execute_ffmpeg_conversion(
                cmd=cmd,
                total_duration_sec=duration_sec,
                on_progress=on_ffmpeg_progress,
                cancel_event=job.cancel_event
            )

            if result["cancelled"]:
                job.status = "cancelled"
                job.stage = "Cancelled by user"
                job.emit_update()
                return

            if not result["success"]:
                raise Exception(result["error"] or "FFmpeg conversion failed.")

            if not output_path.exists() or output_path.stat().st_size == 0:
                raise Exception("Conversion completed but output file is empty or missing.")

            # 5. Finalize Job
            job.output_size_bytes = output_path.stat().st_size
            job.progress_percent = 100.0
            job.status = "completed"
            job.stage = "Conversion complete! Ready for download."
            job.completed_at = time.time()
            job.expires_at = int(job.completed_at) + FILE_TTL_SECONDS

            # Generate Signed Download URL
            token = generate_signed_token(
                file_id=out_filename,
                original_name=out_filename,
                ttl_seconds=FILE_TTL_SECONDS
            )
            job.download_token = token
            job.download_url = f"/api/download/{token}"
            job.emit_update()
            logger.info(f"[Worker {worker_id}] Job {job.job_id} completed successfully.")

        except Exception as e:
            logger.error(f"[Worker {worker_id}] Job {job.job_id} failed: {e}")
            job.status = "failed"
            job.stage = "Conversion failed"
            job.error_message = str(e)
            job.emit_update()


# Global Singleton Instance
queue_manager = JobQueueManager()
