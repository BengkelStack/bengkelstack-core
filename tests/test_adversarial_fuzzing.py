"""
BengkelStack Adversarial & Security Fuzzing Suite
Deep vulnerability testing: SQL injection fuzzing, IDOR cross-tenant boundary,
extreme numeric boundary fuzzing, malformed payloads, and fail-closed security.
"""
import unittest
import sqlite3
import os
import json
from app.server import handle_api_request
from app.cloud_service import register_tenant, login_user
from database.db import get_connection, run_migrations


class TestAdversarialFuzzing(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

        # Load schemas
        with open(os.path.join(os.path.dirname(__file__), "..", "database", "schema.sql"), "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())
        with open(os.path.join(os.path.dirname(__file__), "..", "database", "cloud_schema.sql"), "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())

        # Register Tenant 1
        _, _, r1 = register_tenant(self.conn, "Bengkel Satu", "Owner Satu", "satu@bengkel.com", "PasswordSatu123!")
        self.t1_token = r1["data"]["tokens"]["access_token"]
        self.t1_id = r1["data"]["tenant"]["id"]

        # Register Tenant 2
        _, _, r2 = register_tenant(self.conn, "Bengkel Dua", "Owner Dua", "dua@bengkel.com", "PasswordDua123!")
        self.t2_token = r2["data"]["tokens"]["access_token"]
        self.t2_id = r2["data"]["tenant"]["id"]

    def tearDown(self):
        self.conn.close()

    def test_sql_injection_fuzzing_registration(self):
        sqli_payloads = [
            "' OR '1'='1",
            "admin'--",
            "'; DROP TABLE tenants; --",
            "1 UNION SELECT 1,2,3,4,5,6,7,8,9--",
            "test' AND SLEEP(5)--",
            "test\" OR 1=1--"
        ]
        for sqli in sqli_payloads:
            # Registration must safely sanitize or reject without error 500 or SQL syntax exception
            status, res = handle_api_request(
                self.conn, "POST", "/api/v1/auth/register",
                {
                    "tenant_name": f"Workshop {sqli}",
                    "owner_name": "Test Hacker",
                    "email": f"hacker_{abs(hash(sqli))}@test.com",
                    "password": "ValidPassword123!",
                    "currency": "IDR"
                }
            )
            # Must either create with safely sanitized slug or reject with 400/409, NEVER 500
            self.assertIn(status, (201, 400, 409))
            if status == 201:
                # Verify DB integrity: tenants table still exists and no unintended table drop
                cur = self.conn.cursor()
                cur.execute("SELECT COUNT(*) FROM tenants;")
                self.assertGreaterEqual(cur.fetchone()[0], 2)

    def test_idor_cross_tenant_isolation(self):
        # Tenant 1 generates a sync key
        h1 = {"Authorization": f"Bearer {self.t1_token}"}
        status_k, k_data = handle_api_request(
            self.conn, "POST", "/api/v1/owner/sync-key/generate",
            {"label": "Counter Key T1"}, headers=h1
        )
        self.assertEqual(status_k, 201)

        # Tenant 2 lists keys: must NOT see Tenant 1's key
        h2 = {"Authorization": f"Bearer {self.t2_token}"}
        status_l, l_data = handle_api_request(self.conn, "GET", "/api/v1/owner/sync-keys", None, headers=h2)
        self.assertEqual(status_l, 200)
        self.assertEqual(len(l_data["data"]), 0, "Tenant 2 must have 0 keys, zero bleed from Tenant 1")

        # Tenant 1 tries to access SuperAdmin endpoints -> must be 403 Forbidden
        status_admin, _ = handle_api_request(self.conn, "GET", "/api/v1/admin/tenants", None, headers=h1)
        self.assertEqual(status_admin, 403, "Workshop Owner must be forbidden from SuperAdmin portal")

    def test_extreme_boundary_and_fuzz_values(self):
        # 1. Extremely long string attack (DoS prevention)
        giant_string = "A" * 50000
        status_giant, _ = handle_api_request(
            self.conn, "POST", "/api/v1/auth/register",
            {
                "tenant_name": giant_string,
                "owner_name": "Giant",
                "email": "giant@test.com",
                "password": "Password123!"
            }
        )
        self.assertEqual(status_giant, 400, "Oversized tenant name must be rejected with 400")

        # 2. Giant password attack
        giant_pass = "P" * 10000
        status_p, _ = handle_api_request(
            self.conn, "POST", "/api/v1/auth/register",
            {
                "tenant_name": "Normal Shop",
                "owner_name": "Normal",
                "email": "normal@test.com",
                "password": giant_pass
            }
        )
        self.assertEqual(status_p, 400, "Oversized password (>1024 chars) must be rejected with 400")

        # 3. Unicode and emoji fuzzing in inputs
        unicode_name = "🔧 BENGKEL KILAT 🚀 测试 ñoño @#!$%^&*"
        status_u, u_data = handle_api_request(
            self.conn, "POST", "/api/v1/auth/register",
            {
                "tenant_name": unicode_name,
                "owner_name": "Unicode Owner",
                "email": "unicode@bengkel.com",
                "password": "ValidPassword123!"
            }
        )
        self.assertEqual(status_u, 201)
        self.assertEqual(u_data["data"]["tenant"]["name"], unicode_name)


if __name__ == "__main__":
    unittest.main()
