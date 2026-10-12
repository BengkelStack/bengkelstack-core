"""
BengkelStack Cloud Multi-Tenant & Central Admin Service
Zero external dependencies: 100% Python standard library.
Handles user registration, authentication, RBAC, tenant lifecycle,
edge pairing keys, and fleet telemetry.
"""
import sqlite3
import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional, List
from app.tier2_auth import (
    hash_password,
    verify_password,
    generate_session_token,
    hash_token,
    generate_device_credentials,
    ROLE_SUPERADMIN,
    ROLE_TENANT_OWNER,
    ROLE_TENANT_OPERATOR,
    ROLE_DEVICE_AGENT
)


def slugify(text: str) -> str:
    # ponytail: simple regex slug generator
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-") or f"tenant-{secrets.token_hex(4)}"


def register_tenant(
    conn: sqlite3.Connection,
    tenant_name: str,
    owner_name: str,
    email: str,
    password: str,
    country_code: str = "ID",
    currency: str = "IDR",
    plan: str = "FREE",
    slug: Optional[str] = None
) -> Tuple[bool, int, Dict[str, Any]]:
    if not tenant_name or not email or not password:
        return False, 400, {"error": "Missing required fields: tenant_name, email, password"}

    if len(password) > 1024:
        return False, 400, {"error": "Password exceeds maximum allowable length of 1024 characters"}
    if len(email) > 255:
        return False, 400, {"error": "Email exceeds maximum allowable length of 255 characters"}
    if len(tenant_name) > 255:
        return False, 400, {"error": "Tenant name exceeds maximum allowable length of 255 characters"}

    email = email.lower().strip()
    if "@" not in email:
        return False, 400, {"error": "Invalid email address"}

    if len(password) < 8:
        return False, 400, {"error": "Password must be at least 8 characters"}

    tenant_slug = slugify(slug or tenant_name)
    cur = conn.cursor()

    # Check email duplicate
    cur.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cur.fetchone():
        return False, 409, {"error": "Email address already registered"}

    # Ensure unique slug
    base_slug = tenant_slug
    counter = 1
    while True:
        cur.execute("SELECT id FROM tenants WHERE slug = ?", (tenant_slug,))
        if not cur.fetchone():
            break
        tenant_slug = f"{base_slug}-{counter}"
        counter += 1

    try:
        cur.execute("BEGIN TRANSACTION;")
        # 1. Insert Tenant
        cur.execute(
            """
            INSERT INTO tenants (slug, name, country_code, currency, plan, status)
            VALUES (?, ?, ?, ?, ?, 'ACTIVE');
            """,
            (tenant_slug, tenant_name.strip(), country_code.upper(), currency.upper(), plan.upper())
        )
        tenant_id = cur.lastrowid

        # 2. Insert Owner User
        # Using 10,000 iterations for test/runtime responsiveness, standard format
        hashed_pw = hash_password(password, iterations=10000)
        salt_placeholder = "salt_in_hash"
        cur.execute(
            """
            INSERT INTO users (tenant_id, email, password_hash, salt, role, full_name, is_active)
            VALUES (?, ?, ?, ?, 'OWNER', ?, 1);
            """,
            (tenant_id, email, hashed_pw, salt_placeholder, owner_name.strip())
        )
        user_id = cur.lastrowid

        # 3. Insert Subscription
        valid_until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        cur.execute(
            """
            INSERT INTO tenant_subscriptions (tenant_id, plan_id, billing_cycle, valid_until)
            VALUES (?, ?, 'MONTHLY', ?);
            """,
            (tenant_id, plan.upper(), valid_until)
        )

        # 4. Create Session Token
        raw_token, token_hash = generate_session_token()
        session_expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        cur.execute(
            """
            INSERT INTO user_sessions (user_id, token_hash, expires_at)
            VALUES (?, ?, ?);
            """,
            (user_id, token_hash, session_expires)
        )

        conn.commit()

        return True, 201, {
            "status": "success",
            "data": {
                "tenant": {
                    "id": tenant_id,
                    "slug": tenant_slug,
                    "name": tenant_name,
                    "plan": plan.upper(),
                    "status": "ACTIVE"
                },
                "user": {
                    "id": user_id,
                    "email": email,
                    "full_name": owner_name,
                    "role": "OWNER"
                },
                "tokens": {
                    "access_token": raw_token,
                    "expires_in": 86400
                }
            }
        }
    except Exception as e:
        conn.rollback()
        return False, 500, {"error": f"Failed to register tenant: {str(e)}"}


def login_user(
    conn: sqlite3.Connection,
    email: str,
    password: str
) -> Tuple[bool, int, Dict[str, Any]]:
    if not email or not password:
        return False, 400, {"error": "Missing email or password"}

    email = email.lower().strip()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT u.id, u.tenant_id, u.email, u.password_hash, u.role, u.full_name, u.is_active,
               t.slug, t.name as tenant_name, t.plan, t.status as tenant_status
        FROM users u
        LEFT JOIN tenants t ON u.tenant_id = t.id
        WHERE u.email = ?;
        """,
        (email,)
    )
    row = cur.fetchone()
    if not row:
        return False, 401, {"error": "Invalid email or password"}

    user_dict = dict(row)
    if not user_dict["is_active"]:
        return False, 403, {"error": "User account is disabled"}

    # Verify password
    if not verify_password(password, user_dict["password_hash"]):
        return False, 401, {"error": "Invalid email or password"}

    # Check tenant status (SuperAdmin has tenant_id=None)
    if user_dict["role"] != "SUPERADMIN" and user_dict["tenant_status"] == "SUSPENDED":
        return False, 403, {"error": "Tenant account is suspended. Contact support."}

    # Generate session
    raw_token, token_hash = generate_session_token()
    session_expires = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    cur.execute(
        """
        INSERT INTO user_sessions (user_id, token_hash, expires_at)
        VALUES (?, ?, ?);
        """,
        (user_dict["id"], token_hash, session_expires)
    )
    conn.commit()

    return True, 200, {
        "status": "success",
        "data": {
            "user": {
                "id": user_dict["id"],
                "email": user_dict["email"],
                "role": user_dict["role"],
                "full_name": user_dict["full_name"],
                "tenant_id": user_dict["tenant_id"]
            },
            "tenant": {
                "id": user_dict["tenant_id"],
                "slug": user_dict["slug"],
                "name": user_dict["tenant_name"],
                "plan": user_dict["plan"],
                "status": user_dict["tenant_status"]
            } if user_dict["tenant_id"] else None,
            "tokens": {
                "access_token": raw_token,
                "expires_in": 86400
            }
        }
    }


def get_authenticated_user(
    conn: sqlite3.Connection,
    token: str
) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    token_h = hash_token(token)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT s.id as session_id, s.expires_at,
               u.id as user_id, u.tenant_id, u.email, u.role, u.full_name, u.is_active,
               t.slug as tenant_slug, t.name as tenant_name, t.plan as tenant_plan, t.status as tenant_status
        FROM user_sessions s
        JOIN users u ON s.user_id = u.id
        LEFT JOIN tenants t ON u.tenant_id = t.id
        WHERE s.token_hash = ?;
        """,
        (token_h,)
    )
    row = cur.fetchone()
    if not row:
        return None

    data = dict(row)
    # Check expiry
    try:
        exp = datetime.fromisoformat(data["expires_at"])
        if datetime.now(timezone.utc) > exp:
            return None
    except Exception:
        pass

    return data


def logout_user(conn: sqlite3.Connection, token: str) -> bool:
    if not token:
        return False
    token_h = hash_token(token)
    cur = conn.cursor()
    cur.execute("DELETE FROM user_sessions WHERE token_hash = ?", (token_h,))
    conn.commit()
    return cur.rowcount > 0


def list_tenants(
    conn: sqlite3.Connection,
    page: int = 1,
    limit: int = 20,
    status_filter: Optional[str] = None,
    search: Optional[str] = None
) -> Dict[str, Any]:
    cur = conn.cursor()
    conditions = []
    params: List[Any] = []

    if status_filter and status_filter.upper() != "ALL":
        conditions.append("status = ?")
        params.append(status_filter.upper())

    if search:
        search_like = f"%{search.strip()}%"
        conditions.append("(name LIKE ? OR slug LIKE ?)")
        params.extend([search_like, search_like])

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # Count total
    cur.execute(f"SELECT COUNT(*) FROM tenants {where_clause};", tuple(params))
    total_records = cur.fetchone()[0]

    # Fetch rows
    offset = max(0, (page - 1) * limit)
    query = f"""
        SELECT id, slug, name, country_code, currency, plan, status, created_at, updated_at
        FROM tenants
        {where_clause}
        ORDER BY id DESC
        LIMIT ? OFFSET ?;
    """
    cur.execute(query, tuple(params + [limit, offset]))
    items = [dict(row) for row in cur.fetchall()]

    total_pages = (total_records + limit - 1) // limit if limit > 0 else 1

    return {
        "items": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total_records": total_records,
            "total_pages": total_pages
        }
    }


def update_tenant_status(
    conn: sqlite3.Connection,
    tenant_id: int,
    new_status: str,
    reason: Optional[str] = None
) -> Tuple[bool, int, Dict[str, Any]]:
    new_status = new_status.upper().strip()
    if new_status not in ("ACTIVE", "SUSPENDED", "TRIAL", "CANCELLED"):
        return False, 400, {"error": "Invalid status value"}

    cur = conn.cursor()
    cur.execute("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
    if not cur.fetchone():
        return False, 404, {"error": "Tenant not found"}

    now_iso = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "UPDATE tenants SET status = ?, updated_at = ? WHERE id = ?;",
        (new_status, now_iso, tenant_id)
    )
    conn.commit()

    return True, 200, {
        "status": "success",
        "data": {
            "id": tenant_id,
            "status": new_status,
            "updated_at": now_iso
        }
    }


def generate_tenant_sync_key(
    conn: sqlite3.Connection,
    tenant_id: int,
    label: str = "Edge Terminal"
) -> Tuple[bool, int, Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute("SELECT id FROM tenants WHERE id = ?", (tenant_id,))
    if not cur.fetchone():
        return False, 404, {"error": "Tenant not found"}

    prefix = secrets.token_hex(4)
    raw_secret = secrets.token_urlsafe(32)
    full_api_key = f"bk_sync_{prefix}_{raw_secret}"
    key_hash = hash_token(full_api_key)

    cur.execute(
        """
        INSERT INTO tenant_sync_keys (tenant_id, api_key_hash, prefix, label)
        VALUES (?, ?, ?, ?);
        """,
        (tenant_id, key_hash, prefix, label.strip())
    )
    key_id = cur.lastrowid
    conn.commit()

    return True, 201, {
        "status": "success",
        "data": {
            "key_id": key_id,
            "prefix": prefix,
            "api_key": full_api_key,
            "label": label,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "warning": "Save this API key now. It will not be shown again."
        }
    }


def list_tenant_sync_keys(
    conn: sqlite3.Connection,
    tenant_id: int
) -> List[Dict[str, Any]]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, prefix, label, last_sync_at, is_revoked, created_at
        FROM tenant_sync_keys
        WHERE tenant_id = ?
        ORDER BY id DESC;
        """,
        (tenant_id,)
    )
    return [dict(row) for row in cur.fetchall()]


def get_fleet_metrics(conn: sqlite3.Connection) -> Dict[str, Any]:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM tenants;")
    total_tenants = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM tenants WHERE status = 'ACTIVE';")
    active_tenants = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM tenants WHERE status = 'TRIAL';")
    trial_tenants = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM tenants WHERE status = 'SUSPENDED';")
    suspended_tenants = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM sync_events_log;")
    total_sync_events = cur.fetchone()[0]

    return {
        "total_tenants": total_tenants,
        "active_tenants": active_tenants,
        "trial_tenants": trial_tenants,
        "suspended_tenants": suspended_tenants,
        "total_sync_events": total_sync_events,
        "active_ratio_pct": round((active_tenants / total_tenants * 100), 1) if total_tenants > 0 else 0.0
    }
