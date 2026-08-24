import hmac
import hashlib
import time
from pathlib import Path
from typing import Optional, Dict, Tuple
from collections import defaultdict
from config import SECRET_KEY, FILE_TTL_SECONDS, RATE_LIMIT_PER_MINUTE, STORAGE_DIR


# In-memory IP rate limiter tracking (timestamp lists)
_rate_limits: Dict[str, list] = defaultdict(list)


def check_rate_limit(client_ip: str) -> bool:
    """
    Sliding window rate limit check per IP address.
    Returns True if allowed, False if limit exceeded.
    """
    now = time.time()
    window_start = now - 60.0 # 1 minute window

    # Clean old records
    timestamps = [t for t in _rate_limits[client_ip] if t > window_start]
    if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
        _rate_limits[client_ip] = timestamps
        return False

    timestamps.append(now)
    _rate_limits[client_ip] = timestamps
    return True


def generate_signed_token(file_id: str, original_name: str, ttl_seconds: int = FILE_TTL_SECONDS) -> str:
    """
    Generates an HMAC-SHA256 signed download token with an expiration timestamp.
    Format: {file_id}.{expires_at}.{signature}
    """
    expires_at = int(time.time()) + ttl_seconds
    msg = f"{file_id}:{expires_at}:{original_name}".encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"{file_id}--{expires_at}--{sig}"


def verify_signed_token(token: str, original_name: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Verifies a download token signature and expiry.
    Returns (is_valid, file_id, error_message).
    """
    try:
        parts = token.split("--")
        if len(parts) != 3:
            return False, None, "Invalid token structure."

        file_id, expires_at_str, signature = parts
        expires_at = int(expires_at_str)

        # Check timestamp expiry
        if time.time() > expires_at:
            return False, None, "Download link has expired. Please convert your file again."

        # Verify HMAC
        msg = f"{file_id}:{expires_at}:{original_name}".encode("utf-8")
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return False, None, "Invalid signature or tampered token."

        return True, file_id, None
    except Exception as e:
        return False, None, f"Token verification error: {str(e)}"


def sanitize_safe_path(target_path: Path) -> Path:
    """
    Guarantees that a path does not escape the storage directory.
    """
    resolved = target_path.resolve()
    storage_resolved = STORAGE_DIR.resolve()
    if not str(resolved).startswith(str(storage_resolved)):
        raise PermissionError("Access denied: Path traversal attempted outside storage sandbox.")
    return resolved
