import asyncio
import os
import shutil
import time
from pathlib import Path
import subprocess

from config import UPLOAD_DIR, CONVERTED_DIR
from services.file_sniffer import sniff_file_header
from services.ffmpeg_engine import (
    get_ffmpeg_binary, probe_media_file, build_ffmpeg_command, execute_ffmpeg_conversion
)
from services.security import (
    generate_signed_token, verify_signed_token, sanitize_safe_path
)


import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

async def run_tests():
    print("==================================================")
    print("[TEST] RUNNING OMNICONVERT INTEGRATION TEST SUITE")
    print("==================================================")

    ffmpeg_bin = get_ffmpeg_binary()
    print(f"[*] Detected FFmpeg Binary: {ffmpeg_bin}")

    # 1. Test Security & Token Signing
    print("\n--- 1. Testing HMAC Signed Tokens & Expiration ---")
    test_file = "output_test_123.mp4"
    token = generate_signed_token(test_file, test_file, ttl_seconds=3600)
    is_valid, resolved, err = verify_signed_token(token, test_file)
    assert is_valid is True, f"Token validation failed: {err}"
    assert resolved == test_file
    print("  ✓ Signed token generation and validation: PASSED")

    # Expired token check
    expired_token = generate_signed_token(test_file, test_file, ttl_seconds=-10)
    is_valid, _, err = verify_signed_token(expired_token, test_file)
    assert is_valid is False
    assert "expired" in err.lower()
    print("  ✓ Expired token rejection: PASSED")

    # Tampered token check
    tampered_token = token[:-4] + "abcd"
    is_valid, _, err = verify_signed_token(tampered_token, test_file)
    assert is_valid is False
    print("  ✓ Tampered token rejection: PASSED")

    # 2. Test File Header Sniffing & Anti-Spoofing
    print("\n--- 2. Testing Magic Byte File Sniffer ---")
    fake_mp4 = UPLOAD_DIR / "fake_exploit.mp4"
    with open(fake_mp4, "w") as f:
        f.write("echo 'this is plain text disguised as an mp4 file'; system('malicious');")
    
    sniff_fake = sniff_file_header(fake_mp4)
    assert sniff_fake["valid"] is False, "Failed to reject fake spoofed MP4!"
    print(f"  ✓ Spoofed extension rejected correctly: {sniff_fake.get('error')}")
    fake_mp4.unlink(missing_ok=True)

    # 3. Synthetic Media Creation with FFmpeg
    print("\n--- 3. Generating Synthetic Test Video (2s testsrc + 440Hz sine wave) ---")
    test_src = UPLOAD_DIR / "test_sample.mp4"
    gen_cmd = [
        ffmpeg_bin, "-y",
        "-f", "lavfi", "-i", "testsrc=duration=2:size=640x360:rate=30",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-c:a", "aac",
        str(test_src)
    ]
    subprocess.run(gen_cmd, check=True, capture_output=True)
    assert test_src.exists() and test_src.stat().st_size > 0
    print(f"  ✓ Generated sample video: {test_src.stat().st_size} bytes")

    # Sniff genuine file
    sniff_real = sniff_file_header(test_src)
    assert sniff_real["valid"] is True
    print(f"  ✓ Real MP4 sniffed: MIME={sniff_real['detected_mime']}, Category={sniff_real['media_type']}")

    # Probe metadata
    probe = await probe_media_file(test_src)
    print(f"  ✓ Probed duration: {probe['duration']}s, video: {probe['video']['resolution']} @ {probe['video']['fps']} fps")

    # 4. Test Video to MP3 Conversion
    print("\n--- 4. Testing Transcoding: MP4 -> MP3 (320kbps) ---")
    mp3_out = CONVERTED_DIR / "test_audio.mp3"
    mp3_cmd = build_ffmpeg_command(
        input_path=test_src,
        output_path=mp3_out,
        target_format="mp3",
        options={"audio_bitrate": "320k", "audio_sample_rate": 44100, "strip_metadata": True}
    )
    res_mp3 = await execute_ffmpeg_conversion(mp3_cmd, total_duration_sec=probe['duration'])
    assert res_mp3["success"] is True, f"MP3 conversion failed: {res_mp3['error']}"
    assert mp3_out.exists() and mp3_out.stat().st_size > 0
    print(f"  ✓ MP3 Output generated: {mp3_out.stat().st_size} bytes")

    # 5. Test Video to Animated GIF
    print("\n--- 5. Testing Transcoding: MP4 -> High-Quality GIF ---")
    gif_out = CONVERTED_DIR / "test_anim.gif"
    gif_cmd = build_ffmpeg_command(
        input_path=test_src,
        output_path=gif_out,
        target_format="gif",
        options={"gif_width": 320, "gif_fps": 15}
    )
    res_gif = await execute_ffmpeg_conversion(gif_cmd, total_duration_sec=probe['duration'])
    assert res_gif["success"] is True, f"GIF conversion failed: {res_gif['error']}"
    assert gif_out.exists() and gif_out.stat().st_size > 0
    print(f"  ✓ GIF Output generated: {gif_out.stat().st_size} bytes")

    # 6. Test Video to WebM (VP9 + Opus)
    print("\n--- 6. Testing Transcoding: MP4 -> WebM (VP9) ---")
    webm_out = CONVERTED_DIR / "test_video.webm"
    webm_cmd = build_ffmpeg_command(
        input_path=test_src,
        output_path=webm_out,
        target_format="webm",
        options={"resolution": "480p", "strip_metadata": True}
    )
    res_webm = await execute_ffmpeg_conversion(webm_cmd, total_duration_sec=probe['duration'])
    assert res_webm["success"] is True, f"WebM conversion failed: {res_webm['error']}"
    assert webm_out.exists() and webm_out.stat().st_size > 0
    print(f"  ✓ WebM Output generated: {webm_out.stat().st_size} bytes")

    # Cleanup test files
    for p in [test_src, mp3_out, gif_out, webm_out]:
        p.unlink(missing_ok=True)

    print("\n==================================================")
    print("[SUCCESS] ALL INTEGRATION TESTS PASSED WITH 100% SUCCESS!")
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(run_tests())
