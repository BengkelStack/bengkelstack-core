import unittest
import time
from app.tier2_auth import (
    hash_password,
    verify_password,
    needs_rehash,
    generate_session_token,
    hash_token,
    generate_device_credentials,
    sign_sync_request,
    verify_sync_request,
    ReplayGuard,
    ROLE_SUPERADMIN,
    ROLE_TENANT_OWNER,
    ROLE_TENANT_OPERATOR,
    ROLE_DEVICE_AGENT,
    PERM_TENANT_MANAGE,
    PERM_TENANT_BILLING,
    PERM_POS_TRANSACT,
    PERM_POS_VOID_COMPLETED,
    PERM_CATALOG_WRITE_COST,
    PERM_CATALOG_READ,
    PERM_REPORTS_MARGIN,
    PERM_SYNC_PUSH,
    has_permission,
    BruteForceProtector,
    enforce_tenant_predicate,
)


class TestTier2AuthSecurity(unittest.TestCase):

    def test_password_hashing_and_verification(self):
        # Use smaller iteration in unit test for execution speed, test standard format
        raw_pw = "BengkelRahasia#2026!"
        h = hash_password(raw_pw, iterations=5000)
        self.assertTrue(h.startswith("$pbkdf2-sha256$i=5000$s="))
        self.assertTrue(verify_password(raw_pw, h))
        self.assertFalse(verify_password("SalahPassword", h))
        self.assertFalse(verify_password("", h))
        self.assertFalse(verify_password(raw_pw, "invalid_format"))
        self.assertTrue(needs_rehash(h, target_iterations=600000))
        self.assertFalse(needs_rehash(h, target_iterations=5000))

    def test_opaque_session_token(self):
        token, token_hash = generate_session_token()
        self.assertGreater(len(token), 32)
        self.assertEqual(token_hash, hash_token(token))
        # Hash must differ for different tokens
        token2, hash2 = generate_session_token()
        self.assertNotEqual(token, token2)
        self.assertNotEqual(token_hash, hash2)

    def test_edge_to_cloud_hmac_sync(self):
        dev_id, secret, secret_hash = generate_device_credentials()
        self.assertTrue(dev_id.startswith("dev_"))
        self.assertTrue(secret.startswith("bs_sec_"))
        self.assertEqual(secret_hash, hash_token(secret))

        now = 1700000000.0
        timestamp = 1700000000
        nonce = "nonce_abc123456789"
        body = b'{"transactions": [{"id": 1, "total": 150000}]}'

        sig = sign_sync_request(secret, "POST", "/api/v1/sync/push", timestamp, nonce, body)
        guard = ReplayGuard(max_drift_seconds=300)

        # 1. Valid signature and fresh nonce
        ok, msg = verify_sync_request(
            secret, "POST", "/api/v1/sync/push", timestamp, nonce, body, sig, guard, now=now
        )
        self.assertTrue(ok, msg)

        # 2. Replay with same nonce rejected
        ok, msg = verify_sync_request(
            secret, "POST", "/api/v1/sync/push", timestamp, nonce, body, sig, guard, now=now
        )
        self.assertFalse(ok)
        self.assertIn("replay", msg.lower())

        # 3. Tampered payload rejected
        tampered_body = b'{"transactions": [{"id": 1, "total": 99999999}]}'
        nonce2 = "nonce_2"
        sig2 = sign_sync_request(secret, "POST", "/api/v1/sync/push", timestamp, nonce2, tampered_body)
        ok, msg = verify_sync_request(
            secret, "POST", "/api/v1/sync/push", timestamp, nonce2, body, sig2, guard, now=now
        )
        self.assertFalse(ok)
        self.assertIn("invalid signature", msg.lower())

        # 4. Expired timestamp rejected
        nonce3 = "nonce_3"
        expired_ts = timestamp - 301
        sig3 = sign_sync_request(secret, "POST", "/api/v1/sync/push", expired_ts, nonce3, body)
        ok, msg = verify_sync_request(
            secret, "POST", "/api/v1/sync/push", expired_ts, nonce3, body, sig3, guard, now=now
        )
        self.assertFalse(ok)
        self.assertIn("drift", msg.lower())

    def test_rbac_matrix_enforcement(self):
        # TENANT_OPERATOR can transact and read catalog, but NOT see margin or edit cost or void completed
        self.assertTrue(has_permission(ROLE_TENANT_OPERATOR, PERM_POS_TRANSACT))
        self.assertTrue(has_permission(ROLE_TENANT_OPERATOR, PERM_CATALOG_READ))
        self.assertFalse(has_permission(ROLE_TENANT_OPERATOR, PERM_REPORTS_MARGIN))
        self.assertFalse(has_permission(ROLE_TENANT_OPERATOR, PERM_CATALOG_WRITE_COST))
        self.assertFalse(has_permission(ROLE_TENANT_OPERATOR, PERM_POS_VOID_COMPLETED))
        self.assertFalse(has_permission(ROLE_TENANT_OPERATOR, PERM_TENANT_MANAGE))

        # TENANT_OWNER has business rights in their tenant
        self.assertTrue(has_permission(ROLE_TENANT_OWNER, PERM_REPORTS_MARGIN))
        self.assertTrue(has_permission(ROLE_TENANT_OWNER, PERM_CATALOG_WRITE_COST))
        self.assertTrue(has_permission(ROLE_TENANT_OWNER, PERM_POS_VOID_COMPLETED))
        self.assertTrue(has_permission(ROLE_TENANT_OWNER, PERM_TENANT_BILLING))
        self.assertFalse(has_permission(ROLE_TENANT_OWNER, PERM_TENANT_MANAGE))

        # SUPERADMIN manages tenants across the platform
        self.assertTrue(has_permission(ROLE_SUPERADMIN, PERM_TENANT_MANAGE))
        self.assertFalse(has_permission(ROLE_SUPERADMIN, PERM_CATALOG_WRITE_COST))

        # DEVICE_AGENT is limited to sync push and catalog read
        self.assertTrue(has_permission(ROLE_DEVICE_AGENT, PERM_SYNC_PUSH))
        self.assertFalse(has_permission(ROLE_DEVICE_AGENT, PERM_TENANT_BILLING))

    def test_brute_force_protection(self):
        bf = BruteForceProtector(max_attempts=5, lockout_seconds=900.0)
        client_ip = "192.168.1.100"
        t0 = 1000.0

        for _ in range(4):
            locked = bf.record_failure(client_ip, now=t0)
            self.assertFalse(locked)
            is_locked, _ = bf.is_locked(client_ip, now=t0)
            self.assertFalse(is_locked)

        # 5th attempt locks out
        locked = bf.record_failure(client_ip, now=t0)
        self.assertTrue(locked)
        is_locked, remaining = bf.is_locked(client_ip, now=t0)
        self.assertTrue(is_locked)
        self.assertEqual(remaining, 900.0)

        # Still locked at 1500s
        is_locked, rem = bf.is_locked(client_ip, now=t0 + 500)
        self.assertTrue(is_locked)
        self.assertEqual(rem, 400.0)

        # Unlocked after 901s
        is_locked, _ = bf.is_locked(client_ip, now=t0 + 901)
        self.assertFalse(is_locked)

    def test_tenant_isolation_invariant(self):
        # Valid query with tenant clause
        valid_sql = "SELECT * FROM work_orders WHERE tenant_id = ? AND id = ?"
        enforce_tenant_predicate(valid_sql, tenant_param_present=True)

        # Missing parameter must raise
        with self.assertRaises(PermissionError):
            enforce_tenant_predicate(valid_sql, tenant_param_present=False)

        # Missing tenant_id in SQL must raise
        invalid_sql = "SELECT * FROM work_orders WHERE id = ?"
        with self.assertRaises(PermissionError):
            enforce_tenant_predicate(invalid_sql, tenant_param_present=True)


if __name__ == "__main__":
    unittest.main()
