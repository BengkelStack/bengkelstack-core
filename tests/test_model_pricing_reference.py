import unittest
import sqlite3
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import run_migrations
from app.repositories import create_motor_model, create_part, create_service
from app.custom_fee_repository import set_custom_install_fee
from app.work_order_service import (
    create_work_order,
    get_model_pricing_reference,
)


class TestModelPricingReference(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

        self.model_aerox = create_motor_model(self.conn, "Yamaha", "Aerox 155")
        self.model_beat = create_motor_model(self.conn, "Honda", "Beat 110")

        self.part_oli = create_part(self.conn, "OIL-YML", "Yamalube Power Matic", 45000.0, 60000.0, 5000.0)
        self.part_roller = create_part(self.conn, "ROL-12G", "Roller CVT 12g", 60000.0, 85000.0, 15000.0)
        self.svc_cvt = create_service(self.conn, "Servis CVT Lengkap", 45000.0)

        # Set custom fee for roller on Aerox (25.000 instead of default 15.000)
        set_custom_install_fee(self.conn, self.part_roller["id"], self.model_aerox["id"], 25000.0)

    def tearDown(self):
        self.conn.close()

    def test_get_model_pricing_reference_with_history_and_custom_fees(self):
        # Transaksi pada kendaraan Aerox
        create_work_order(
            self.conn,
            plate_number="B 1111 ARX",
            motor_model_id=self.model_aerox["id"],
            customer_name="Rico",
            items=[
                {"item_type": "part", "item_id": self.part_roller["id"], "action_type": "installed"},
                {"item_type": "service", "item_id": self.svc_cvt["id"], "action_type": "installed"}
            ]
        )

        ref = get_model_pricing_reference(self.conn, self.model_aerox["id"])
        self.assertIsNotNone(ref)
        self.assertEqual(ref["motor_model"]["id"], self.model_aerox["id"])
        self.assertEqual(ref["motor_model"]["model_name"], "Aerox 155")

        # 1. Historical items
        hist_items = ref["historical_items"]
        self.assertEqual(len(hist_items), 2)
        roller_hist = next(i for i in hist_items if i["item_type"] == "part" and i["item_id"] == self.part_roller["id"])
        self.assertEqual(roller_hist["usage_count"], 1)
        self.assertEqual(roller_hist["latest_install_fee"], 25000.0)

        # 2. Custom install fees configured
        custom_fees = ref["custom_install_fees"]
        self.assertEqual(len(custom_fees), 1)
        self.assertEqual(custom_fees[0]["part_id"], self.part_roller["id"])
        self.assertEqual(custom_fees[0]["custom_install_fee"], 25000.0)

        # 3. Estimated catalog pricing for this model
        catalog_est = ref["catalog_estimates"]
        roller_est = next(p for p in catalog_est["parts"] if p["id"] == self.part_roller["id"])
        self.assertEqual(roller_est["applicable_install_fee"], 25000.0)
        self.assertTrue(roller_est["is_custom_fee"])
        # Installed subtotal = 85.000 + 25.000 = 110.000
        self.assertEqual(roller_est["installed_estimate"], 110000.0)

        oli_est = next(p for p in catalog_est["parts"] if p["id"] == self.part_oli["id"])
        self.assertEqual(oli_est["applicable_install_fee"], 5000.0)  # default
        self.assertFalse(oli_est["is_custom_fee"])
        self.assertEqual(oli_est["installed_estimate"], 65000.0)

    def test_get_model_pricing_reference_non_existent_model(self):
        ref = get_model_pricing_reference(self.conn, 99999)
        self.assertIsNone(ref)


if __name__ == "__main__":
    unittest.main()
