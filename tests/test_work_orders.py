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
    get_or_create_vehicle,
    find_vehicle_by_plate,
    create_work_order,
    get_work_order,
)


class TestWorkOrders(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

        self.model_vario = create_motor_model(self.conn, "Honda", "Vario 150")
        self.model_nmax = create_motor_model(self.conn, "Yamaha", "NMAX 155")

        self.part_oli = create_part(
            self.conn, "OIL-SPX2", "Oli SPX2 0.8L", 50000.0, 68000.0, 5000.0
        )
        self.part_kampas = create_part(
            self.conn, "PAD-FR", "Kampas Rem Depan", 30000.0, 45000.0, 10000.0
        )
        # Custom fee on NMAX for kampas
        set_custom_install_fee(self.conn, self.part_kampas["id"], self.model_nmax["id"], 18000.0)

        self.svc_cvt = create_service(self.conn, "Servis CVT", 40000.0)

    def tearDown(self):
        self.conn.close()

    def test_get_or_create_vehicle(self):
        veh1 = get_or_create_vehicle(
            self.conn,
            plate_number="b 1234 abc",
            motor_model_id=self.model_vario["id"],
            customer_name="Agus"
        )
        self.assertEqual(veh1["plate_number"], "B 1234 ABC")
        self.assertEqual(veh1["customer_name"], "Agus")

        # Lookup same plate returns existing record without duplicate
        veh2 = get_or_create_vehicle(
            self.conn,
            plate_number="B 1234 ABC",
            motor_model_id=self.model_vario["id"],
            customer_name="Agus Updated"
        )
        self.assertEqual(veh1["id"], veh2["id"])

    def test_create_work_order_with_takeaway_and_installed(self):
        items = [
            # Takeaway oil: 68.000 + 0 = 68.000
            {"item_type": "part", "item_id": self.part_oli["id"], "action_type": "takeaway"},
            # Installed kampas on NMAX: custom fee 18.000 -> 45.000 + 18.000 = 63.000
            {"item_type": "part", "item_id": self.part_kampas["id"], "action_type": "installed"},
            # Service CVT: 40.000
            {"item_type": "service", "item_id": self.svc_cvt["id"], "action_type": "installed"},
        ]

        order = create_work_order(
            self.conn,
            plate_number="B 9999 NMX",
            motor_model_id=self.model_nmax["id"],
            customer_name="Dimas",
            items=items,
            status="COMPLETED"
        )

        self.assertIsNotNone(order["id"])
        # Total: 68000 + 63000 + 40000 = 171000
        self.assertEqual(order["total_amount"], 171000.0)
        self.assertEqual(len(order["items"]), 3)

        fetched = get_work_order(self.conn, order["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["total_amount"], 171000.0)
        self.assertEqual(len(fetched["items"]), 3)
        self.assertEqual(fetched["vehicle"]["plate_number"], "B 9999 NMX")

    def test_empty_items_raises_value_error(self):
        with self.assertRaises(ValueError):
            create_work_order(
                self.conn,
                plate_number="B 1111 ZZZ",
                motor_model_id=self.model_vario["id"],
                customer_name="Budi",
                items=[]
            )


if __name__ == "__main__":
    unittest.main()
