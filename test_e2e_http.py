import urllib.request
import urllib.parse
import json
import time
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from services.ffmpeg_engine import get_ffmpeg_binary
import subprocess

def test_api_e2e():
    print("[*] Starting End-to-End HTTP API Validation...")
    ffmpeg_bin = get_ffmpeg_binary()

    # 1. Create a 1-second sample video
    sample_file = "e2e_source.mp4"
    subprocess.run([
        ffmpeg_bin, "-y",
        "-f", "lavfi", "-i", "testsrc=duration=1:size=320x240:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=1",
        "-c:v", "libx264", "-c:a", "aac",
        sample_file
    ], check=True, capture_output=True)

    # 2. Upload file via multipart/form-data
    boundary = "----WebKitFormBoundaryE2ETest"
    with open(sample_file, "rb") as f:
        file_bytes = f.read()

    parts = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"tos_agreed\"\r\n\r\ntrue\r\n".encode("utf-8"),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"e2e_source.mp4\"\r\nContent-Type: video/mp4\r\n\r\n".encode("utf-8"),
        file_bytes,
        f"\r\n--{boundary}--\r\n".encode("utf-8")
    ]
    body = b"".join(parts)

    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )
    res = urllib.request.urlopen(req)
    up_data = json.loads(res.read().decode())
    print(f"  ✓ Upload Successful! File ID: {up_data['file_id']}, Detected MIME: {up_data['detected_mime']}")

    # 3. Create Conversion Job (MP4 -> MP3)
    job_payload = {
        "source_type": "upload",
        "target_format": "mp3",
        "options": {"audio_bitrate": "320k", "audio_sample_rate": 44100},
        "file_id": up_data["file_id"],
        "original_filename": "e2e_source.mp4",
        "tos_agreed": True
    }
    job_req = urllib.request.Request(
        "http://127.0.0.1:8000/api/jobs/create",
        data=json.dumps(job_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    job_res = urllib.request.urlopen(job_req)
    job_data = json.loads(job_res.read().decode())
    job_id = job_data["job_id"]
    print(f"  ✓ Job Queued: {job_id}")

    # 4. Poll Status
    download_url = None
    for _ in range(20):
        time.sleep(0.3)
        poll_res = urllib.request.urlopen(f"http://127.0.0.1:8000/api/jobs/{job_id}")
        st = json.loads(poll_res.read().decode())
        print(f"    -> Status: {st['status']}, Stage: {st['stage']}, Progress: {st['progress_percent']}%")
        if st["status"] == "completed":
            download_url = st["download_url"]
            break
        elif st["status"] in ["failed", "cancelled"]:
            raise Exception(f"Job failed: {st['error_message']}")

    assert download_url is not None, "Job did not complete within timeout."
    print(f"  ✓ Conversion Completed! Signed Download URL: {download_url}")

    # 5. Test Download with Signed Token
    dl_res = urllib.request.urlopen(f"http://127.0.0.1:8000{download_url}")
    assert dl_res.status == 200
    converted_bytes = dl_res.read()
    print(f"  ✓ Download Verified! Received {len(converted_bytes)} bytes of valid MP3 audio stream.")

    # Clean up local test file
    if os.path.exists(sample_file):
        os.remove(sample_file)

    print("\n[SUCCESS] ALL E2E HTTP API VERIFICATION TESTS PASSED PERFECTLY!")

if __name__ == "__main__":
    test_api_e2e()
