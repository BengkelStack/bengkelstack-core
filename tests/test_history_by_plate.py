import unittest
import sqlite3
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import run_migrations
from app.repositories import create_motor_model, create_part, create_service
from app.work_order_service import (
    create_work_order,
    get_service_history_by_plate,
)


class TestHistoryByPlate(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

        self.motor = create_motor_model(self.conn, "Honda", "Vario 150")
        self.part_oli = create_part(self.conn, "OIL-SPX2", "Oli SPX2", 50000.0, 68000.0, 5000.0)
        self.part_busi = create_part(self.conn, "SPK-01", "Busi NGK", 15000.0, 25000.0, 5000.0)
        self.svc_tuneup = create_service(self.conn, "Tune Up Injeksi", 50000.0)

    def tearDown(self):
        self.conn.close()

    def test_get_service_history_by_plate_chronological(self):
        # Transaksi 1: Ganti oli (takeaway)
        wo1 = create_work_order(
            self.conn,
            plate_number="B 1234 XYZ",
            motor_model_id=self.motor["id"],
            customer_name="Agus",
            items=[{"item_type": "part", "item_id": self.part_oli["id"], "action_type": "takeaway"}]
        )

        # Transaksi 2: Ganti busi + tune up (installed)
        wo2 = create_work_order(
            self.conn,
            plate_number="B 1234 XYZ",
            motor_model_id=self.motor["id"],
            customer_name="Agus",
            items=[
                {"item_type": "part", "item_id": self.part_busi["id"], "action_type": "installed"},
                {"item_type": "service", "item_id": self.svc_tuneup["id"], "action_type": "installed"}
            ]
        )

        # Fetch history for plate B 1234 XYZ (case insensitive & spacing tolerant)
        history = get_service_history_by_plate(self.conn, "b 1234 xyz")

        self.assertIsNotNone(history)
        self.assertEqual(history["plate_number"], "B 1234 XYZ")
        self.assertEqual(history["customer_name"], "Agus")
        self.assertEqual(history["model_name"], "Vario 150")
        self.assertEqual(len(history["work_orders"]), 2)

        # Chronological descending: newest first (wo2, then wo1)
        first_wo = history["work_orders"][0]
        second_wo = history["work_orders"][1]

        self.assertEqual(first_wo["id"], wo2["id"])
        self.assertEqual(len(first_wo["items"]), 2)
        # Busi subtotal: 25000 + 5000 = 30000; Tuneup: 50000; Total = 80000
        self.assertEqual(first_wo["total_amount"], 80000.0)

        self.assertEqual(second_wo["id"], wo1["id"])
        self.assertEqual(len(second_wo["items"]), 1)
        self.assertEqual(second_wo["total_amount"], 68000.0)

    def test_get_service_history_non_existent_plate_returns_none(self):
        history = get_service_history_by_plate(self.conn, "B 9999 NON")
        self.assertIsNone(history)


if __name__ == "__main__":
    unittest.main()
