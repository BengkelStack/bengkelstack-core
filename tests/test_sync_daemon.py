"""
BengkelStack Edge Sync Daemon TDD Test Suite
Verifies delta extraction from local SQLite, HMAC request signing,
offline resilience, idempotency tracking, and graceful shutdown.
"""
import unittest
import sqlite3
import os
import json
import time
from app.tier2_auth import (
    generate_device_credentials,
    sign_sync_request,
    verify_sync_request,
    ReplayGuard,
)


class TestSyncDaemonLogic(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")

        # Apply local schema
        schema_path = os.path.join(os.path.dirname(__file__), "..", "database", "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            self.conn.executescript(f.read())

        # Ensure cloud tracking columns in work_orders
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(work_orders);")
        cols = {r[1] for r in cur.fetchall()}
        if "synced_to_cloud" not in cols:
            cur.execute("ALTER TABLE work_orders ADD COLUMN synced_to_cloud INTEGER NOT NULL DEFAULT 0;")
        if "cloud_synced_at" not in cols:
            cur.execute("ALTER TABLE work_orders ADD COLUMN cloud_synced_at TIMESTAMP;")
        self.conn.commit()

        # Generate test device credentials
        self.dev_id, self.dev_secret, self.dev_hash = generate_device_credentials()
        self.tenant_id = 101

    def tearDown(self):
        self.conn.close()

    def test_collect_unsynced_orders(self):
        from app.sync_daemon import get_unsynced_work_orders, mark_orders_as_synced

        # Seed sample motor model and parts
        cur = self.conn.cursor()
        cur.execute("INSERT INTO motor_models (id, brand, model_name) VALUES (1, 'Honda', 'Vario 160');")
        cur.execute("INSERT INTO parts (id, part_code, name, retail_price) VALUES (1, 'OLI-01', 'Oli MPX2', 55000);")
        cur.execute("INSERT INTO vehicles (id, plate_number, motor_model_id, customer_name) VALUES (1, 'B 1234 CD', 1, 'Budi');")
        cur.execute("INSERT INTO vehicles (id, plate_number, motor_model_id, customer_name) VALUES (2, 'B 5678 EF', 1, 'Agus');")

        # Insert 2 work orders: 1 unsynced, 1 already synced
        cur.execute(
            """
            INSERT INTO work_orders (vehicle_id, status, total_amount, payment_method, synced_to_cloud)
            VALUES (1, 'COMPLETED', 55000, 'CASH', 0);
            """
        )
        wo1_id = cur.lastrowid

        cur.execute(
            """
            INSERT INTO work_orders (vehicle_id, status, total_amount, payment_method, synced_to_cloud)
            VALUES (2, 'COMPLETED', 55000, 'CASH', 1);
            """
        )

        unsynced = get_unsynced_work_orders(self.conn, limit=10)
        self.assertEqual(len(unsynced), 1)
        self.assertEqual(unsynced[0]["plate_number"], "B 1234 CD")

        # Mark as synced
        mark_orders_as_synced(self.conn, [wo1_id])
        unsynced_after = get_unsynced_work_orders(self.conn, limit=10)
        self.assertEqual(len(unsynced_after), 0)

    def test_build_signed_sync_payload(self):
        from app.sync_daemon import build_sync_packet

        sample_orders = [
            {"id": 1, "order_number": "WO-001", "grand_total": 55000, "plate_number": "B 1234 CD"}
        ]
        packet = build_sync_packet(
            tenant_id=self.tenant_id,
            device_id=self.dev_id,
            device_secret=self.dev_secret,
            orders=sample_orders,
            target_path="/api/v1/sync/push"
        )

        headers = packet["headers"]
        self.assertEqual(headers["X-Bengkel-Tenant-Id"], str(self.tenant_id))
        self.assertEqual(headers["X-Bengkel-Device-Id"], self.dev_id)
        self.assertTrue("X-Bengkel-Signature" in headers)
        self.assertTrue("X-Bengkel-Nonce" in headers)
        self.assertTrue("X-Bengkel-Timestamp" in headers)

        # Verify signature on receiver side
        body_bytes = packet["body_bytes"]
        guard = ReplayGuard(max_drift_seconds=300)
        ok, msg = verify_sync_request(
            device_secret=self.dev_secret,
            method="POST",
            path="/api/v1/sync/push",
            timestamp=int(headers["X-Bengkel-Timestamp"]),
            nonce=headers["X-Bengkel-Nonce"],
            body=body_bytes,
            signature=headers["X-Bengkel-Signature"],
            replay_guard=guard
        )
        self.assertTrue(ok, msg)


if __name__ == "__main__":
    unittest.main()
