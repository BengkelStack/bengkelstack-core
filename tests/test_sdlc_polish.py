import unittest
import sqlite3
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import get_connection, run_migrations
from app.repositories import (
    create_motor_model,
    create_part,
    get_workshop_settings,
    update_workshop_settings
)
from app.work_order_service import create_work_order, format_thermal_receipt


class TestSdlcPolish(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

        self.motor = create_motor_model(self.conn, "Honda", "Vario 125")
        self.part = create_part(self.conn, "PART-OIL", "Oli MPX2", 40000.0, 55000.0, 5000.0)

    def tearDown(self):
        self.conn.close()

    def test_schema_migrations_tracked(self):
        cur = self.conn.cursor()
        cur.execute("SELECT version FROM schema_migrations ORDER BY version;")
        versions = [r[0] for r in cur.fetchall()]
        self.assertIn("001_initial_schema", versions)
        self.assertIn("002_settings_and_payments", versions)

    def test_workshop_settings_default_and_update(self):
        settings = get_workshop_settings(self.conn)
        self.assertEqual(settings["currency_symbol"], "Rp")
        self.assertEqual(settings["currency_code"], "IDR")
        self.assertEqual(settings["workshop_name"], "BENGKELSTACK WORKSHOP OS")

        # Update settings to international (Vietnam: VND, ₫)
        update_workshop_settings(
            self.conn,
            workshop_name="Saigon Moto Repair",
            currency_symbol="₫",
            currency_code="VND",
            receipt_header="DICH VU SUA CHUA XE MAY",
            receipt_footer="Bao Hanh 7 Ngay",
            min_margin_pct=30.0
        )

        updated = get_workshop_settings(self.conn)
        self.assertEqual(updated["currency_symbol"], "₫")
        self.assertEqual(updated["currency_code"], "VND")
        self.assertEqual(updated["workshop_name"], "Saigon Moto Repair")
        self.assertEqual(updated["min_margin_pct"], 30.0)

    def test_work_order_with_cash_and_change(self):
        # 1 part installed = 55.000 + 5.000 = 60.000
        # Cash given = 100.000 -> Change = 40.000
        order = create_work_order(
            self.conn,
            plate_number="B 1234 POLISH",
            motor_model_id=self.motor["id"],
            customer_name="Pak Joko",
            items=[{"item_type": "part", "item_id": self.part["id"], "action_type": "installed"}],
            status="COMPLETED",
            payment_method="CASH",
            cash_received=100000.0
        )

        self.assertEqual(order["total_amount"], 60000.0)
        self.assertEqual(order["payment_method"], "CASH")
        self.assertEqual(order["cash_received"], 100000.0)
        self.assertEqual(order["change_amount"], 40000.0)

    def test_format_thermal_receipt_international_currency(self):
        # Set settings to USD ($)
        update_workshop_settings(
            self.conn,
            workshop_name="Austin Moto Garage",
            currency_symbol="$",
            currency_code="USD",
            receipt_header="PREMIUM MOTORCYCLE SERVICE",
            receipt_footer="30 Days / 500 Miles Warranty"
        )

        order = create_work_order(
            self.conn,
            plate_number="TX-9988-USA",
            motor_model_id=self.motor["id"],
            customer_name="John Doe",
            items=[{"item_type": "part", "item_id": self.part["id"], "action_type": "installed"}],
            payment_method="CARD",
            cash_received=60000.0
        )

        receipt = format_thermal_receipt(order, conn=self.conn)
        self.assertIn("Austin Moto Garage", receipt)
        self.assertIn("PREMIUM MOTORCYCLE SERVICE", receipt)
        self.assertIn("METHOD     : CARD", receipt)
        self.assertIn("$", receipt)
        self.assertNotIn("Rp", receipt)


if __name__ == "__main__":
    unittest.main()
