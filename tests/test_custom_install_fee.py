import unittest
import sqlite3
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import run_migrations
from app.repositories import create_part, create_motor_model
from app.custom_fee_repository import (
    set_custom_install_fee,
    get_custom_install_fee,
    delete_custom_install_fee,
    list_custom_fees_for_model,
)
from app.pricing_engine import calculate_item_pricing


class TestCustomInstallFee(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

        # Seed master data
        self.motor_beat = create_motor_model(self.conn, "Honda", "Beat 110")
        self.motor_nmax = create_motor_model(self.conn, "Yamaha", "NMAX 155")

        # Part: V-Belt (Default pasang 15.000, tapi untuk NMAX lebih rumit bongkar CVT)
        self.part_vbelt = create_part(
            self.conn,
            part_code="BELT-GEN",
            name="V-Belt Racing",
            cost_price=70000.0,
            retail_price=95000.0,
            default_install_fee=15000.0
        )

    def tearDown(self):
        self.conn.close()

    def test_set_and_get_custom_install_fee(self):
        saved = set_custom_install_fee(
            self.conn,
            part_id=self.part_vbelt["id"],
            motor_model_id=self.motor_nmax["id"],
            custom_install_fee=35000.0
        )
        self.assertIsNotNone(saved["id"])
        self.assertEqual(saved["custom_install_fee"], 35000.0)

        fetched = get_custom_install_fee(
            self.conn,
            part_id=self.part_vbelt["id"],
            motor_model_id=self.motor_nmax["id"]
        )
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["custom_install_fee"], 35000.0)

    def test_pricing_uses_custom_fee_when_present(self):
        # Set custom fee for NMAX
        set_custom_install_fee(
            self.conn,
            part_id=self.part_vbelt["id"],
            motor_model_id=self.motor_nmax["id"],
            custom_install_fee=35000.0
        )

        pricing = calculate_item_pricing(
            self.conn,
            item_type="part",
            item_id=self.part_vbelt["id"],
            action_type="installed",
            motor_model_id=self.motor_nmax["id"]
        )
        self.assertEqual(pricing["price"], 95000.0)
        self.assertEqual(pricing["install_fee"], 35000.0)
        self.assertEqual(pricing["subtotal"], 130000.0)
        self.assertTrue(pricing["is_custom_fee"])

    def test_pricing_falls_back_to_default_fee_when_no_custom_fee(self):
        # Beat has no custom fee configured
        pricing = calculate_item_pricing(
            self.conn,
            item_type="part",
            item_id=self.part_vbelt["id"],
            action_type="installed",
            motor_model_id=self.motor_beat["id"]
        )
        self.assertEqual(pricing["price"], 95000.0)
        self.assertEqual(pricing["install_fee"], 15000.0)  # default fee
        self.assertEqual(pricing["subtotal"], 110000.0)
        self.assertFalse(pricing["is_custom_fee"])

    def test_takeaway_ignores_custom_fee(self):
        set_custom_install_fee(
            self.conn,
            part_id=self.part_vbelt["id"],
            motor_model_id=self.motor_nmax["id"],
            custom_install_fee=35000.0
        )
        pricing = calculate_item_pricing(
            self.conn,
            item_type="part",
            item_id=self.part_vbelt["id"],
            action_type="takeaway",
            motor_model_id=self.motor_nmax["id"]
        )
        self.assertEqual(pricing["price"], 95000.0)
        self.assertEqual(pricing["install_fee"], 0.0)
        self.assertEqual(pricing["subtotal"], 95000.0)
        self.assertFalse(pricing["is_custom_fee"])

    def test_upsert_modifies_existing_custom_fee(self):
        set_custom_install_fee(self.conn, self.part_vbelt["id"], self.motor_nmax["id"], 30000.0)
        # Update via upsert
        updated = set_custom_install_fee(self.conn, self.part_vbelt["id"], self.motor_nmax["id"], 40000.0)
        self.assertEqual(updated["custom_install_fee"], 40000.0)

        pricing = calculate_item_pricing(
            self.conn,
            item_type="part",
            item_id=self.part_vbelt["id"],
            action_type="installed",
            motor_model_id=self.motor_nmax["id"]
        )
        self.assertEqual(pricing["install_fee"], 40000.0)

    def test_delete_custom_fee_reverts_to_default(self):
        set_custom_install_fee(self.conn, self.part_vbelt["id"], self.motor_nmax["id"], 35000.0)
        deleted = delete_custom_install_fee(self.conn, self.part_vbelt["id"], self.motor_nmax["id"])
        self.assertTrue(deleted)

        # After delete, should revert to default 15000
        pricing = calculate_item_pricing(
            self.conn,
            item_type="part",
            item_id=self.part_vbelt["id"],
            action_type="installed",
            motor_model_id=self.motor_nmax["id"]
        )
        self.assertEqual(pricing["install_fee"], 15000.0)
        self.assertFalse(pricing["is_custom_fee"])


if __name__ == "__main__":
    unittest.main()
