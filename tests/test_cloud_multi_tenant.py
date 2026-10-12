"""
BengkelStack Cloud Multi-Tenant Architecture Self-Check
Zero external dependencies: uses Python stdlib sqlite3, hashlib, hmac, secrets, json.
"""
import unittest
import sqlite3
import hashlib
import hmac
import secrets
import json
import os
from datetime import datetime, timezone, timedelta

# ponytail: stdlib password hashing with PBKDF2-HMAC-SHA256
def hash_password(password: str, salt: bytes = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_bytes(16)
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return hashed.hex(), salt.hex()

def verify_password(password: str, password_hash: str, salt_hex: str) -> bool:
    salt = bytes.fromhex(salt_hex)
    test_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000).hex()
    return hmac.compare_digest(test_hash, password_hash)

# ponytail: sync key token format bk_sync_{prefix}_{random_entropy}
def generate_sync_key() -> tuple[str, str, str]:
    prefix = secrets.token_hex(4)
    raw_secret = secrets.token_urlsafe(32)
    full_key = f"bk_sync_{prefix}_{raw_secret}"
    key_hash = hashlib.sha256(full_key.encode("utf-8")).hexdigest()
    return full_key, prefix, key_hash

def hash_payload(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

class TestCloudMultiTenant(unittest.TestCase):
    def test_multi_tenant_lifecycle(self):
        # 1. Connect in-memory SQLite and apply schema
        conn = sqlite3.connect(":memory:")
        conn.execute("PRAGMA foreign_keys = ON;")
        
        schema_path = os.path.join(os.path.dirname(__file__), "..", "database", "cloud_schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)

        # 2. Register SuperAdmin (tenant_id IS NULL)
        sa_hash, sa_salt = hash_password("SuperSecretAdminPass123!")
        conn.execute(
            "INSERT INTO users (tenant_id, email, password_hash, salt, role, full_name, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (None, "admin@bengkelstack.com", sa_hash, sa_salt, "SUPERADMIN", "Master System Admin", 1)
        )
        self.assertTrue(verify_password("SuperSecretAdminPass123!", sa_hash, sa_salt))
        self.assertFalse(verify_password("WrongPass", sa_hash, sa_salt))

        # 3. Register Tenant 1 (Bengkel Maju Motor)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tenants (slug, name, country_code, currency, plan, status) VALUES (?, ?, ?, ?, ?, ?)",
            ("maju-motor", "Bengkel Maju Motor", "ID", "IDR", "FREE", "ACTIVE")
        )
        t1_id = cur.lastrowid
        self.assertEqual(t1_id, 1)

        # Create Owner for Tenant 1
        t1_hash, t1_salt = hash_password("OwnerMaju2026")
        cur.execute(
            "INSERT INTO users (tenant_id, email, password_hash, salt, role, full_name, is_active) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (t1_id, "budi@majumotor.id", t1_hash, t1_salt, "OWNER", "Budi Santoso", 1)
        )

        # Add default Subscription
        valid_until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
        cur.execute(
            "INSERT INTO tenant_subscriptions (tenant_id, plan_id, billing_cycle, valid_until) VALUES (?, ?, ?, ?)",
            (t1_id, "FREE", "MONTHLY", valid_until)
        )

        # 4. Generate Sync Key for Tenant 1
        full_key, prefix, key_hash = generate_sync_key()
        cur.execute(
            "INSERT INTO tenant_sync_keys (tenant_id, api_key_hash, prefix, label) VALUES (?, ?, ?, ?)",
            (t1_id, key_hash, prefix, "Kasir PC Utama")
        )

        # Verify key lookup
        cur.execute(
            "SELECT tenant_id, is_revoked FROM tenant_sync_keys WHERE api_key_hash = ?",
            (key_hash,)
        )
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], t1_id)
        self.assertEqual(row[1], 0)

        # 5. Ingest Sync Event with Idempotency
        sample_payload = {
            "event": "WORK_ORDER_COMPLETED",
            "order_number": "WO-20261012-001",
            "grand_total": 125000,
            "items": 2
        }
        p_hash = hash_payload(sample_payload)

        cur.execute(
            """
            INSERT INTO sync_events_log (tenant_id, event_type, payload_hash, payload_json, sync_status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (t1_id, "WORK_ORDER_COMPLETED", p_hash, json.dumps(sample_payload), "PROCESSED")
        )

        # Attempt duplicate insert -> must raise IntegrityError due to UNIQUE(tenant_id, payload_hash)
        with self.assertRaises(sqlite3.IntegrityError):
            cur.execute(
                """
                INSERT INTO sync_events_log (tenant_id, event_type, payload_hash, payload_json, sync_status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (t1_id, "WORK_ORDER_COMPLETED", p_hash, json.dumps(sample_payload), "PROCESSED")
            )

        # 6. Tenant 2 Isolation Check
        cur.execute(
            "INSERT INTO tenants (slug, name, country_code, currency, plan, status) VALUES (?, ?, ?, ?, ?, ?)",
            ("jaya-abadi", "Bengkel Jaya Abadi", "ID", "IDR", "PRO", "ACTIVE")
        )
        t2_id = cur.lastrowid
        self.assertEqual(t2_id, 2)

        # Scoped query for Tenant 2 returns 0 sync keys and 0 events
        cur.execute("SELECT COUNT(*) FROM tenant_sync_keys WHERE tenant_id = ?", (t2_id,))
        self.assertEqual(cur.fetchone()[0], 0)

        cur.execute("SELECT COUNT(*) FROM sync_events_log WHERE tenant_id = ?", (t2_id,))
        self.assertEqual(cur.fetchone()[0], 0)

        # 7. SuperAdmin Tenant Status Toggle
        cur.execute("UPDATE tenants SET status = ? WHERE id = ?", ("SUSPENDED", t1_id))
        cur.execute("SELECT status FROM tenants WHERE id = ?", (t1_id,))
        self.assertEqual(cur.fetchone()[0], "SUSPENDED")

if __name__ == "__main__":
    unittest.main()
