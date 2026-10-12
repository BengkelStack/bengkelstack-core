import hashlib
import hmac
import secrets
import time
from typing import Dict, Set, Tuple, Optional
from collections import defaultdict

# =====================================================================
# 1. PASSWORD HASHING (OWASP PBKDF2-HMAC-SHA256)
# =====================================================================
OWASP_RECOMMENDED_ITERATIONS = 600000
SALT_BYTES = 16


def hash_password(password: str, iterations: int = OWASP_RECOMMENDED_ITERATIONS) -> str:
    # ponytail: stdlib PBKDF2-HMAC-SHA256 zero-dependency; upgrade to argon2id when cffi/compiled wheels permitted
    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string")
    salt = secrets.token_bytes(SALT_BYTES)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"$pbkdf2-sha256$i={iterations}$s={salt.hex()}$h={derived.hex()}"


def verify_password(password: str, hashed_record: str) -> bool:
    # ponytail: constant-time digest comparison to prevent timing side-channel
    if not isinstance(password, str) or not isinstance(hashed_record, str):
        return False
    parts = hashed_record.split("$")
    # Expected format: ['', 'pbkdf2-sha256', 'i=600000', 's=<hex>', 'h=<hex>']
    if len(parts) != 5 or parts[1] != "pbkdf2-sha256":
        return False
    try:
        iter_str = parts[2]
        if not iter_str.startswith("i="):
            return False
        iterations = int(iter_str[2:])

        salt_str = parts[3]
        if not salt_str.startswith("s="):
            return False
        salt = bytes.fromhex(salt_str[2:])

        hash_str = parts[4]
        if not hash_str.startswith("h="):
            return False
        expected_hash = bytes.fromhex(hash_str[2:])

        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(candidate, expected_hash)
    except (ValueError, TypeError):
        return False


def needs_rehash(hashed_record: str, target_iterations: int = OWASP_RECOMMENDED_ITERATIONS) -> bool:
    try:
        parts = hashed_record.split("$")
        if len(parts) != 5:
            return True
        iterations = int(parts[2][2:])
        return iterations < target_iterations
    except Exception:
        return True


# =====================================================================
# 2. TOKEN & SESSION MANAGEMENT (OPAQUE 256-BIT TOKENS)
# =====================================================================
def generate_session_token() -> Tuple[str, str]:
    # ponytail: opaque random token with SHA-256 DB index; skip JWT parsing bugs & revocation lists
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


# =====================================================================
# 3. EDGE-TO-CLOUD SYNC SECURITY (HMAC-SHA256 SIGNING & REPLAY GUARD)
# =====================================================================
def generate_device_credentials() -> Tuple[str, str, str]:
    # Returns (device_id, raw_device_secret, secret_hash_for_db)
    device_id = f"dev_{secrets.token_hex(8)}"
    raw_secret = f"bs_sec_{secrets.token_urlsafe(32)}"
    secret_hash = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
    return device_id, raw_secret, secret_hash


def build_canonical_payload(method: str, path: str, timestamp: int, nonce: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
    return canonical.encode("utf-8")


def sign_sync_request(
    device_secret: str,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    body: bytes = b""
) -> str:
    # Fail-closed guard: prevent HMAC calculation with empty or unconfigured secret
    if not device_secret or not isinstance(device_secret, str) or not device_secret.strip():
        raise ValueError("device_secret must be a non-empty string (fail-closed guard)")
    canonical = build_canonical_payload(method, path, timestamp, nonce, body)
    return hmac.new(device_secret.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


class ReplayGuard:
    def __init__(self, max_drift_seconds: int = 300):
        # ponytail: in-memory sliding nonce cache; upgrade to Redis SETNX when distributed
        self.max_drift_seconds = max_drift_seconds
        self.seen_nonces: Dict[str, float] = {}

    def is_valid_and_record(self, nonce: str, timestamp: int, now: Optional[float] = None) -> Tuple[bool, str]:
        if now is None:
            now = time.time()

        # 1. Clock drift check
        if abs(now - timestamp) > self.max_drift_seconds:
            return False, "Clock drift exceeded threshold (replay window expired)"

        # 2. Cleanup expired nonces
        cutoff = now - self.max_drift_seconds
        expired = [n for n, ts in self.seen_nonces.items() if ts < cutoff]
        for n in expired:
            del self.seen_nonces[n]

        # 3. Replay check
        if nonce in self.seen_nonces:
            return False, "Nonce has already been used (replay detected)"

        self.seen_nonces[nonce] = float(timestamp)
        return True, "OK"


def verify_sync_request(
    device_secret: str,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    body: bytes,
    signature: str,
    replay_guard: Optional[ReplayGuard] = None,
    now: Optional[float] = None
) -> Tuple[bool, str]:
    # Fail-closed guard: empty secret, signature, or nonce must be rejected immediately
    if not device_secret or not isinstance(device_secret, str) or not device_secret.strip():
        return False, "Fail-closed rejection: device_secret is empty or unconfigured"
    if not signature or not isinstance(signature, str) or not signature.strip():
        return False, "Fail-closed rejection: signature is empty or invalid"
    if not nonce or not isinstance(nonce, str) or not nonce.strip():
        return False, "Fail-closed rejection: nonce is empty or invalid"

    if replay_guard:
        ok, msg = replay_guard.is_valid_and_record(nonce, timestamp, now)
        if not ok:
            return False, f"Replay rejection: {msg}"

    expected_sig = sign_sync_request(device_secret, method, path, timestamp, nonce, body)
    if not secrets.compare_digest(signature, expected_sig):
        return False, "Invalid signature"

    return True, "Authorized"


# =====================================================================
# 4. ROLE-BASED ACCESS CONTROL (RBAC MATRIX)
# =====================================================================
ROLE_SUPERADMIN = "SUPERADMIN"
ROLE_TENANT_OWNER = "TENANT_OWNER"
ROLE_TENANT_OPERATOR = "TENANT_OPERATOR"
ROLE_DEVICE_AGENT = "DEVICE_AGENT"

PERM_TENANT_MANAGE = "tenant:manage"
PERM_TENANT_BILLING = "tenant:billing"
PERM_DEVICE_PAIR = "device:pair"
PERM_DEVICE_REVOKE = "device:revoke"
PERM_USER_MANAGE = "user:manage"
PERM_CATALOG_READ = "catalog:read"
PERM_CATALOG_WRITE_PRICE = "catalog:write_price"
PERM_CATALOG_WRITE_COST = "catalog:write_cost"
PERM_POS_TRANSACT = "pos:transact"
PERM_POS_VOID_COMPLETED = "pos:void_completed"
PERM_REPORTS_MARGIN = "reports:financial_margin"
PERM_SYNC_PUSH = "sync:push"

ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    ROLE_SUPERADMIN: {
        PERM_TENANT_MANAGE,
        PERM_DEVICE_REVOKE,
    },
    ROLE_TENANT_OWNER: {
        PERM_TENANT_BILLING,
        PERM_DEVICE_PAIR,
        PERM_DEVICE_REVOKE,
        PERM_USER_MANAGE,
        PERM_CATALOG_READ,
        PERM_CATALOG_WRITE_PRICE,
        PERM_CATALOG_WRITE_COST,
        PERM_POS_TRANSACT,
        PERM_POS_VOID_COMPLETED,
        PERM_REPORTS_MARGIN,
        PERM_SYNC_PUSH,
    },
    ROLE_TENANT_OPERATOR: {
        PERM_CATALOG_READ,
        PERM_POS_TRANSACT,
    },
    ROLE_DEVICE_AGENT: {
        PERM_SYNC_PUSH,
        PERM_CATALOG_READ,
    },
}


def has_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    return permission in perms


# =====================================================================
# 5. THREAT MITIGATION (BRUTE FORCE & TENANT ISOLATION)
# =====================================================================
class BruteForceProtector:
    def __init__(self, max_attempts: int = 5, lockout_seconds: float = 900.0):
        # ponytail: in-memory failure counter with lockout timestamp
        self.max_attempts = max_attempts
        self.lockout_seconds = lockout_seconds
        self.failures = defaultdict(list)
        self.lockouts: Dict[str, float] = {}

    def is_locked(self, key: str, now: Optional[float] = None) -> Tuple[bool, float]:
        if now is None:
            now = time.time()
        lock_until = self.lockouts.get(key, 0.0)
        if now < lock_until:
            return True, lock_until - now
        return False, 0.0

    def record_failure(self, key: str, now: Optional[float] = None) -> bool:
        if now is None:
            now = time.time()
        window_start = now - self.lockout_seconds
        recent = [t for t in self.failures[key] if t >= window_start]
        recent.append(now)
        self.failures[key] = recent
        if len(recent) >= self.max_attempts:
            self.lockouts[key] = now + self.lockout_seconds
            return True  # locked out
        return False

    def record_success(self, key: str):
        self.failures.pop(key, None)
        self.lockouts.pop(key, None)


def enforce_tenant_predicate(sql: str, tenant_param_present: bool) -> None:
    # ponytail: runtime barrier preventing cross-tenant leakage in multi-tenant queries
    if not tenant_param_present:
        raise PermissionError("Multi-tenant query invariant violated: tenant_id predicate missing")
    if "tenant_id" not in sql.lower():
        raise PermissionError("Multi-tenant query invariant violated: SQL text lacks tenant_id clause")
