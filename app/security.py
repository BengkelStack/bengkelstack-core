import os
import re
import secrets
import time
from collections import defaultdict, deque
from typing import Dict, Tuple, Optional

# Institutional Constraint: 1MB maximum payload
MAX_PAYLOAD_SIZE = 1024 * 1024


def sanitize_input_str(val: str) -> str:
    # ponytail: stdlib clean regex tag stripping
    if not isinstance(val, str):
        return ""
    no_tags = re.sub(r"<[^>]+>", "", val)
    return " ".join(no_tags.strip().split())


def verify_auth(headers: Dict[str, str], client_ip: str) -> Tuple[bool, int, str]:
    # ponytail: constant-time token comparison with loopback fail-safe
    configured_key = os.environ.get("BENGKELSTACK_API_KEY")

    auth_header = headers.get("Authorization") or headers.get("authorization", "")
    
    if configured_key:
        if not auth_header.startswith("Bearer "):
            return False, 401, "Unauthorized: Bearer token required"
        provided_token = auth_header[7:].strip()
        if not secrets.compare_digest(provided_token, configured_key):
            return False, 401, "Unauthorized: Invalid token"
        return True, 200, "Authorized"

    # When no API key is configured, local machine loopback and private Tailscale network are permitted
    is_loopback = client_ip in ("127.0.0.1", "::1", "localhost", "testclient")
    is_tailscale = client_ip.startswith("100.")
    if is_loopback or is_tailscale:
        return True, 200, "Authorized"
    
    return False, 403, "Forbidden: External connection requires configured BENGKELSTACK_API_KEY"


class RateLimiter:
    def __init__(self, max_requests: int = 120, window_seconds: float = 60.0):
        # ponytail: sliding window with collections.deque
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = defaultdict(deque)

    def is_allowed(self, client_ip: str) -> bool:
        now = time.time()
        q = self.requests[client_ip]

        # Purge entries outside window
        while q and q[0] <= now - self.window_seconds:
            q.popleft()

        if len(q) >= self.max_requests:
            return False

        q.append(now)
        return True


def get_security_headers() -> Dict[str, str]:
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com;"
        )
    }
