import unittest
import sqlite3
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import run_migrations
from app.repositories import create_motor_model, create_part
from app.work_order_service import create_work_order
from app.server import handle_api_request


class TestIdempotency(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

        self.motor = create_motor_model(self.conn, "Honda", "Beat Deluxe")
        self.part = create_part(self.conn, "OIL-BT", "Oli MPX2 Beat", 40000.0, 55000.0, 5000.0)

    def tearDown(self):
        self.conn.close()

    def test_create_work_order_with_idempotency_key(self):
        idem_key = "tx_client_unique_12345"

        # 1. First order submission
        order1 = create_work_order(
            self.conn,
            plate_number="B 8888 IDEM",
            motor_model_id=self.motor["id"],
            customer_name="Pak Idem",
            items=[{"item_type": "part", "item_id": self.part["id"], "action_type": "installed"}],
            idempotency_key=idem_key
        )
        self.assertEqual(order1["total_amount"], 60000.0)
        self.assertEqual(order1.get("idempotency_key"), idem_key)

        # 2. Second order submission (simulating double-click or network retry)
        order2 = create_work_order(
            self.conn,
            plate_number="B 8888 IDEM",
            motor_model_id=self.motor["id"],
            customer_name="Pak Idem",
            items=[{"item_type": "part", "item_id": self.part["id"], "action_type": "installed"}],
            idempotency_key=idem_key
        )

        # Both must return the identical order id
        self.assertEqual(order1["id"], order2["id"])

        # Check table row count - must be exactly 1
        cur = self.conn.cursor()
        total_orders = cur.execute("SELECT COUNT(*) FROM work_orders;").fetchone()[0]
        self.assertEqual(total_orders, 1, "Duplicate work order was created despite identical idempotency_key!")

    def test_api_idempotency_handling(self):
        idem_key = "api_client_req_9999"
        body = {
            "plate_number": "D 1111 RETRY",
            "motor_model_id": self.motor["id"],
            "customer_name": "Pak Retry",
            "items": [{"item_type": "part", "item_id": self.part["id"], "action_type": "takeaway"}],
            "idempotency_key": idem_key
        }

        # First request
        status1, data1 = handle_api_request(self.conn, "POST", "/api/work-orders", body)
        self.assertEqual(status1, 201)

        # Immediate retry
        status2, data2 = handle_api_request(self.conn, "POST", "/api/work-orders", body)
        self.assertIn(status2, (200, 201))
        self.assertEqual(data1["id"], data2["id"])


if __name__ == "__main__":
    unittest.main()
