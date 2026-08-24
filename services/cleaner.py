import asyncio
import time
import os
from pathlib import Path
import logging
from config import UPLOAD_DIR, CONVERTED_DIR, FILE_TTL_SECONDS, CLEANUP_INTERVAL_SECONDS

logger = logging.getLogger("OmniCleaner")


async def run_periodic_cleanup():
    """
    Background worker that runs every CLEANUP_INTERVAL_SECONDS to delete expired
    raw uploads and converted assets from disk.
    """
    logger.info("Auto-cleanup daemon started.")
    while True:
        try:
            now = time.time()
            deleted_count = 0
            freed_bytes = 0

            for folder in [UPLOAD_DIR, CONVERTED_DIR]:
                if not folder.exists():
                    continue
                for file_path in folder.iterdir():
                    if file_path.is_file():
                        try:
                            mtime = file_path.stat().st_mtime
                            if (now - mtime) > FILE_TTL_SECONDS:
                                size = file_path.stat().st_size
                                file_path.unlink(missing_ok=True)
                                deleted_count += 1
                                freed_bytes += size
                        except Exception as e:
                            logger.warning(f"Failed to delete expired file {file_path.name}: {e}")

            if deleted_count > 0:
                mb_freed = freed_bytes / (1024 * 1024)
                logger.info(f"Cleanup run: removed {deleted_count} expired files ({mb_freed:.2f} MB freed).")

        except asyncio.CancelledError:
            logger.info("Cleanup daemon stopped.")
            break
        except Exception as e:
            logger.error(f"Error during file cleanup cycle: {e}")

        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
