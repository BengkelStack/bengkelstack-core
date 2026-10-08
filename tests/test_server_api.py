import unittest
import sqlite3
import json
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import run_migrations
from app.repositories import create_motor_model, create_part, create_service
from app.server import handle_api_request


class TestServerApi(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

        self.motor = create_motor_model(self.conn, "Honda", "Vario 125")
        self.part = create_part(self.conn, "OIL-01", "Oli MPX2", 40000.0, 55000.0, 5000.0)
        self.svc = create_service(self.conn, "Ganti Oli", 10000.0)

    def tearDown(self):
        self.conn.close()

    def test_get_master_data(self):
        # 1. Motor models
        status, data = handle_api_request(self.conn, "GET", "/api/motor-models", None)
        self.assertEqual(status, 200)
        self.assertEqual(len(data), 1)

        # 2. Parts
        status, data = handle_api_request(self.conn, "GET", "/api/parts", None)
        self.assertEqual(status, 200)
        self.assertEqual(len(data), 1)

        # 3. Services
        status, data = handle_api_request(self.conn, "GET", "/api/services", None)
        self.assertEqual(status, 200)
        self.assertEqual(len(data), 1)

    def test_calculate_pricing_instant(self):
        body = {
            "motor_model_id": self.motor["id"],
            "items": [
                {"item_type": "part", "item_id": self.part["id"], "action_type": "takeaway"},
                {"item_type": "part", "item_id": self.part["id"], "action_type": "installed"}
            ]
        }
        status, data = handle_api_request(self.conn, "POST", "/api/calculate", body)
        self.assertEqual(status, 200)
        # item 1: takeaway 55000
        self.assertEqual(data["items"][0]["subtotal"], 55000.0)
        # item 2: installed 55000 + 5000 = 60000
        self.assertEqual(data["items"][1]["subtotal"], 60000.0)
        # total: 115000
        self.assertEqual(data["total_amount"], 115000.0)

    def test_create_work_order_api(self):
        body = {
            "plate_number": "B 1234 ABC",
            "motor_model_id": self.motor["id"],
            "customer_name": "Pak Eko",
            "items": [
                {"item_type": "part", "item_id": self.part["id"], "action_type": "installed"}
            ]
        }
        status, data = handle_api_request(self.conn, "POST", "/api/work-orders", body)
        self.assertEqual(status, 201)
        self.assertEqual(data["vehicle"]["plate_number"], "B 1234 ABC")
        self.assertEqual(data["total_amount"], 60000.0)

        # Lookup vehicle endpoint
        status, vdata = handle_api_request(self.conn, "GET", "/api/vehicle-lookup?plate=B 1234 ABC", None)
        self.assertEqual(status, 200)
        self.assertEqual(vdata["customer_name"], "Pak Eko")

    def test_quick_update_master_api(self):
        body = {
            "item_type": "part",
            "item_id": self.part["id"],
            "new_price": 58000.0,
            "new_install_fee": 8000.0,
            "save_as_model_custom": False
        }
        status, res = handle_api_request(self.conn, "POST", "/api/master/quick-update", body)
        self.assertEqual(status, 200)
        self.assertTrue(res["success"])

    def test_history_by_plate_api(self):
        # Create an order first
        body = {
            "plate_number": "D 8888 ABC",
            "motor_model_id": self.motor["id"],
            "customer_name": "Pak Deni",
            "items": [{"item_type": "part", "item_id": self.part["id"], "action_type": "takeaway"}]
        }
        handle_api_request(self.conn, "POST", "/api/work-orders", body)

        status, hist = handle_api_request(self.conn, "GET", "/api/history/plate?plate=D 8888 ABC", None)
        self.assertEqual(status, 200)
        self.assertIsNotNone(hist)
        self.assertEqual(hist["plate_number"], "D 8888 ABC")
        self.assertEqual(len(hist["work_orders"]), 1)

    def test_reference_by_model_api(self):
        status, ref = handle_api_request(self.conn, "GET", f"/api/reference/model?motor_model_id={self.motor['id']}", None)
        self.assertEqual(status, 200)
        self.assertIsNotNone(ref)
        self.assertEqual(ref["motor_model"]["id"], self.motor["id"])
        self.assertIn("catalog_estimates", ref)


if __name__ == "__main__":
    unittest.main()
