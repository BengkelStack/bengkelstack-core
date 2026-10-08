import unittest
import sqlite3
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import run_migrations
from app.repositories import create_part, create_service, create_motor_model
from app.pricing_engine import calculate_item_pricing, calculate_cart_pricing


class TestPricingEngine(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

        # Seed master data
        self.part_oli = create_part(
            self.conn,
            part_code="OIL-MPX2",
            name="Oli MPX2 0.8L",
            cost_price=40000.0,
            retail_price=55000.0,
            default_install_fee=5000.0
        )
        self.part_ban = create_part(
            self.conn,
            part_code="TIRE-80-90",
            name="Ban Luar Tubeless 80/90-14",
            cost_price=160000.0,
            retail_price=210000.0,
            default_install_fee=20000.0
        )
        self.svc_tuneup = create_service(
            self.conn,
            service_name="Tune Up Injeksi",
            standard_fee=50000.0
        )
        self.motor_beat = create_motor_model(self.conn, "Honda", "Beat ESP")

    def tearDown(self):
        self.conn.close()

    def test_part_takeaway_pricing(self):
        # Rule: Jika action_type = 'takeaway': subtotal = retail_price
        result = calculate_item_pricing(
            self.conn,
            item_type="part",
            item_id=self.part_oli["id"],
            action_type="takeaway",
            motor_model_id=self.motor_beat["id"]
        )
        self.assertEqual(result["price"], 55000.0)
        self.assertEqual(result["install_fee"], 0.0)
        self.assertEqual(result["subtotal"], 55000.0)
        self.assertEqual(result["action_type"], "takeaway")

    def test_part_installed_default_fee(self):
        # Rule: Jika action_type = 'installed' & belum ada custom fee:
        # subtotal = retail_price + default_install_fee
        result = calculate_item_pricing(
            self.conn,
            item_type="part",
            item_id=self.part_oli["id"],
            action_type="installed",
            motor_model_id=self.motor_beat["id"]
        )
        self.assertEqual(result["price"], 55000.0)
        self.assertEqual(result["install_fee"], 5000.0)
        self.assertEqual(result["subtotal"], 60000.0)
        self.assertEqual(result["action_type"], "installed")

    def test_service_pricing(self):
        # Service standard fee
        result = calculate_item_pricing(
            self.conn,
            item_type="service",
            item_id=self.svc_tuneup["id"],
            action_type="installed",
            motor_model_id=self.motor_beat["id"]
        )
        self.assertEqual(result["price"], 50000.0)
        self.assertEqual(result["install_fee"], 0.0)
        self.assertEqual(result["subtotal"], 50000.0)

    def test_cart_total_calculation(self):
        cart_items = [
            # 1 Oli takeaway (55.000)
            {"item_type": "part", "item_id": self.part_oli["id"], "action_type": "takeaway"},
            # 1 Ban installed (210.000 + 20.000 = 230.000)
            {"item_type": "part", "item_id": self.part_ban["id"], "action_type": "installed"},
            # 1 Servis (50.000)
            {"item_type": "service", "item_id": self.svc_tuneup["id"], "action_type": "installed"},
        ]
        cart = calculate_cart_pricing(self.conn, cart_items, motor_model_id=self.motor_beat["id"])
        
        self.assertEqual(len(cart["items"]), 3)
        self.assertEqual(cart["items"][0]["subtotal"], 55000.0)
        self.assertEqual(cart["items"][1]["subtotal"], 230000.0)
        self.assertEqual(cart["items"][2]["subtotal"], 50000.0)
        # Total = 55.000 + 230.000 + 50.000 = 335.000
        self.assertEqual(cart["total_amount"], 335000.0)

    def test_invalid_action_type_raises_value_error(self):
        with self.assertRaises(ValueError):
            calculate_item_pricing(
                self.conn,
                item_type="part",
                item_id=self.part_oli["id"],
                action_type="invalid_type"
            )

    def test_item_not_found_raises_value_error(self):
        with self.assertRaises(ValueError):
            calculate_item_pricing(
                self.conn,
                item_type="part",
                item_id=9999,
                action_type="installed"
            )


if __name__ == "__main__":
    unittest.main()
