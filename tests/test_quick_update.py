import unittest
import sqlite3
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import run_migrations
from app.repositories import (
    create_motor_model,
    create_part,
    get_part,
    create_service,
    get_service,
)
from app.custom_fee_repository import get_custom_install_fee
from app.work_order_service import (
    quick_update_master_price,
    create_work_order,
)


class TestQuickUpdateMasterPrice(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

        self.motor = create_motor_model(self.conn, "Honda", "Beat Deluxe")
        self.part = create_part(
            self.conn,
            part_code="OIL-MPX1",
            name="Oli MPX1 0.8L",
            cost_price=38000.0,
            retail_price=50000.0,
            default_install_fee=5000.0
        )
        self.svc = create_service(self.conn, "Servis Ringan", 40000.0)

    def tearDown(self):
        self.conn.close()

    def test_quick_update_part_retail_and_default_install_fee(self):
        # Kasir mengubah harga retail jadi 55.000 dan ongkos pasang default jadi 7.000
        result = quick_update_master_price(
            self.conn,
            item_type="part",
            item_id=self.part["id"],
            new_price=55000.0,
            new_install_fee=7000.0,
            motor_model_id=None,
            save_as_model_custom=False
        )
        self.assertTrue(result["success"])

        updated_part = get_part(self.conn, self.part["id"])
        self.assertEqual(updated_part["retail_price"], 55000.0)
        self.assertEqual(updated_part["default_install_fee"], 7000.0)

    def test_quick_update_part_custom_fee_for_motor_model(self):
        # Kasir memilih "Simpan sebagai tarif khusus model ini"
        result = quick_update_master_price(
            self.conn,
            item_type="part",
            item_id=self.part["id"],
            new_price=52000.0,
            new_install_fee=12000.0,
            motor_model_id=self.motor["id"],
            save_as_model_custom=True
        )
        self.assertTrue(result["success"])

        # Master retail updated
        updated_part = get_part(self.conn, self.part["id"])
        self.assertEqual(updated_part["retail_price"], 52000.0)
        # Default fee stays original
        self.assertEqual(updated_part["default_install_fee"], 5000.0)

        # Custom fee on model is saved
        custom = get_custom_install_fee(self.conn, self.part["id"], self.motor["id"])
        self.assertIsNotNone(custom)
        self.assertEqual(custom["custom_install_fee"], 12000.0)

    def test_quick_update_service_standard_fee(self):
        result = quick_update_master_price(
            self.conn,
            item_type="service",
            item_id=self.svc["id"],
            new_price=45000.0
        )
        self.assertTrue(result["success"])

        updated_svc = get_service(self.conn, self.svc["id"])
        self.assertEqual(updated_svc["standard_fee"], 45000.0)

    def test_create_work_order_with_save_as_standard_flag(self):
        # Transaksi kasir dengan override harga manual dan checkbox "Simpan sebagai tarif standar"
        items = [
            {
                "item_type": "part",
                "item_id": self.part["id"],
                "action_type": "installed",
                "price": 53000.0,          # manual price override
                "install_fee": 8000.0,      # manual fee override
                "save_as_standard": True,   # quick update flag
                "save_as_model_custom": False,
            }
        ]

        order = create_work_order(
            self.conn,
            plate_number="B 7777 ABC",
            motor_model_id=self.motor["id"],
            customer_name="Pak Joko",
            items=items
        )

        # Subtotal: 53.000 + 8.000 = 61.000
        self.assertEqual(order["total_amount"], 61000.0)
        self.assertEqual(order["items"][0]["price"], 53000.0)
        self.assertEqual(order["items"][0]["install_fee"], 8000.0)

        # Verifikasi master part ter-update otomatis
        part_master = get_part(self.conn, self.part["id"])
        self.assertEqual(part_master["retail_price"], 53000.0)
        self.assertEqual(part_master["default_install_fee"], 8000.0)


if __name__ == "__main__":
    unittest.main()
