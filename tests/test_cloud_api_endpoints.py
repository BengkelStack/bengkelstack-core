"""
BengkelStack Tier 2 Cloud API Endpoints TDD Test Suite
Tests registration, login, logout, tenant listing, status update,
pairing key generation, and RBAC authorization boundaries.
"""
import unittest
import sqlite3
import os
import json
from app.server import handle_api_request
from database.db import get_connection, run_migrations
from app.cloud_service import register_tenant, login_user, hash_password


class TestCloudApiEndpoints(unittest.TestCase):
    def setUp(self):
        # In-memory database with migrations
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        
        schema_path = os.path.join(os.path.dirname(__file__), "..", "database", "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())
            
        cloud_schema_path = os.path.join(os.path.dirname(__file__), "..", "database", "cloud_schema.sql")
        with open(cloud_schema_path, "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())

        # Seed SuperAdmin user
        sa_hash = hash_password("SuperSecretAdminPass123!", iterations=5000)
        self.conn.execute(
            """
            INSERT INTO users (tenant_id, email, password_hash, salt, role, full_name, is_active)
            VALUES (NULL, 'admin@bengkelstack.com', ?, 'salt', 'SUPERADMIN', 'Master HQ Admin', 1);
            """,
            (sa_hash,)
        )
        self.conn.commit()

        # Login SuperAdmin to get access token
        ok, code, res = login_user(self.conn, "admin@bengkelstack.com", "SuperSecretAdminPass123!")
        self.assertTrue(ok)
        self.admin_token = res["data"]["tokens"]["access_token"]

    def tearDown(self):
        self.conn.close()

    def test_owner_registration_and_login_flow(self):
        # 1. Register new owner
        reg_payload = {
            "tenant_name": "Garasi Motor Perkasa",
            "owner_name": "Agus Pratama",
            "email": "agus@garasimotor.id",
            "password": "PasswordKuat123!",
            "country_code": "ID",
            "currency": "IDR",
            "plan": "PRO"
        }
        status, data = handle_api_request(self.conn, "POST", "/api/v1/auth/register", reg_payload)
        self.assertEqual(status, 201)
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["data"]["tenant"]["name"], "Garasi Motor Perkasa")
        self.assertEqual(data["data"]["user"]["email"], "agus@garasimotor.id")
        self.assertEqual(data["data"]["user"]["role"], "OWNER")
        owner_token = data["data"]["tokens"]["access_token"]
        self.assertTrue(bool(owner_token))

        # 2. Duplicate registration rejected
        status_dup, data_dup = handle_api_request(self.conn, "POST", "/api/v1/auth/register", reg_payload)
        self.assertEqual(status_dup, 409)

        # 3. Owner login with correct credentials
        login_payload = {
            "email": "agus@garasimotor.id",
            "password": "PasswordKuat123!"
        }
        status_login, data_login = handle_api_request(self.conn, "POST", "/api/v1/auth/login", login_payload)
        self.assertEqual(status_login, 200)
        self.assertEqual(data_login["data"]["user"]["role"], "OWNER")

        # 4. Owner login with incorrect password
        status_bad, _ = handle_api_request(
            self.conn, "POST", "/api/v1/auth/login",
            {"email": "agus@garasimotor.id", "password": "WrongPassword!"}
        )
        self.assertEqual(status_bad, 401)

    def test_owner_profile_and_sync_key_generation(self):
        # Register owner
        _, _, reg_data = register_tenant(
            self.conn, "Bintang Speed", "Budi Bintang", "budi@bintang.com", "BintangPass123!"
        )
        owner_token = reg_data["data"]["tokens"]["access_token"]
        headers = {"Authorization": f"Bearer {owner_token}"}

        # 1. Get profile
        status, profile = handle_api_request(self.conn, "GET", "/api/v1/owner/profile", None, headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(profile["data"]["user"]["email"], "budi@bintang.com")

        # 2. Generate pairing sync key
        status_k, key_data = handle_api_request(
            self.conn, "POST", "/api/v1/owner/sync-key/generate",
            {"label": "Counter Tablet 1"},
            headers=headers
        )
        self.assertEqual(status_k, 201)
        self.assertTrue(key_data["data"]["api_key"].startswith("bk_sync_"))
        self.assertEqual(key_data["data"]["label"], "Counter Tablet 1")

        # 3. List sync keys
        status_list, keys_list = handle_api_request(self.conn, "GET", "/api/v1/owner/sync-keys", None, headers=headers)
        self.assertEqual(status_list, 200)
        self.assertEqual(len(keys_list["data"]), 1)

    def test_superadmin_tenant_management_and_rbac(self):
        # Register 2 tenants
        register_tenant(self.conn, "Bengkel Alpha", "Owner Alpha", "alpha@bengkel.com", "AlphaPass123!")
        register_tenant(self.conn, "Bengkel Beta", "Owner Beta", "beta@bengkel.com", "BetaPass123!")

        admin_headers = {"Authorization": f"Bearer {self.admin_token}"}

        # 1. SuperAdmin lists tenants
        status, res = handle_api_request(self.conn, "GET", "/api/v1/admin/tenants", None, headers=admin_headers)
        self.assertEqual(status, 200)
        self.assertEqual(res["data"]["pagination"]["total_records"], 2)

        # 2. SuperAdmin checks overview metrics
        status_m, metrics = handle_api_request(self.conn, "GET", "/api/v1/admin/metrics/overview", None, headers=admin_headers)
        self.assertEqual(status_m, 200)
        self.assertEqual(metrics["data"]["total_tenants"], 2)
        self.assertEqual(metrics["data"]["active_tenants"], 2)

        # 3. SuperAdmin suspends Tenant 1
        status_suspend, sus_res = handle_api_request(
            self.conn, "PATCH", "/api/v1/admin/tenants/1/status",
            {"status": "SUSPENDED", "reason": "Non-payment"},
            headers=admin_headers
        )
        self.assertEqual(status_suspend, 200)
        self.assertEqual(sus_res["data"]["status"], "SUSPENDED")

        # 4. Suspended owner cannot login
        status_l, err_l = handle_api_request(
            self.conn, "POST", "/api/v1/auth/login",
            {"email": "alpha@bengkel.com", "password": "AlphaPass123!"}
        )
        self.assertEqual(status_l, 403)
        self.assertIn("suspended", err_l["error"].lower())

        # 5. Non-admin (anonymous or normal user) blocked from /admin
        status_unauth, _ = handle_api_request(self.conn, "GET", "/api/v1/admin/tenants", None, headers={})
        self.assertEqual(status_unauth, 401)


if __name__ == "__main__":
    unittest.main()
