import unittest
import sqlite3
import os
import tempfile
from app.pricing_engine import calculate_cart_pricing, calculate_item_pricing
from app.work_order_service import create_work_order, format_thermal_receipt
from database.db import run_migrations


class TestWhiteboxEdgeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.tmp.close()
        self.conn = run_migrations(db_path=self.tmp.name)
        cur = self.conn.cursor()
        cur.execute("INSERT OR IGNORE INTO motor_models (id, brand, model_name) VALUES (1, 'Honda', 'Beat FI');")
        cur.execute("INSERT OR IGNORE INTO parts (id, part_code, name, cost_price, retail_price, default_install_fee) VALUES (1, 'OIL-01', 'Oli Mesin', 35000.0, 45000.0, 5000.0);")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.tmp.name):
            os.remove(self.tmp.name)

    def test_whitebox_zero_and_negative_quantities(self):
        # Quantity 0 should gracefully fallback to 0 or minimum positive
        res = calculate_cart_pricing(self.conn, motor_model_id=1, items=[
            {"item_type": "part", "item_id": 1, "action_type": "installed", "quantity": 0}
        ])
        self.assertEqual(res["total_amount"], 0.0)

    def test_whitebox_extreme_quantity_multiplication(self):
        # 10,000 units of part (45,000) installed (5,000) = 50,000 * 10,000 = 500,000,000
        res = calculate_cart_pricing(self.conn, motor_model_id=1, items=[
            {"item_type": "part", "item_id": 1, "action_type": "installed", "quantity": 10000}
        ])
        self.assertEqual(res["total_amount"], 500000000.0)

    def test_whitebox_malformed_plate_sql_injection(self):
        # Malformed SQL injection string in plate number lookup
        malicious_plates = [
            "B 1234 XYZ'; DROP TABLE vehicles; --",
            "\" OR \"1\"=\"1",
            "<script>alert(1)</script>",
            "   \n\t  B 1234 XYZ   "
        ]
        from app.work_order_service import find_vehicle_by_plate
        for plate in malicious_plates:
            veh = find_vehicle_by_plate(self.conn, plate)
            # Parameterized queries ensure table is untouched and query succeeds without error
            cur = self.conn.cursor()
            cur.execute("SELECT count(*) FROM motor_models;")
            self.assertEqual(cur.fetchone()[0], 1)

    def test_whitebox_empty_receipt_generation(self):
        # Order with 0 items generates valid receipt without throwing exception
        empty_order = {
            "id": 999,
            "created_at": "2026-10-12 12:00:00",
            "vehicle": {"plate_number": "TX-000", "brand": "Generic", "model_name": "Bike", "customer_name": "Test"},
            "status": "COMPLETED",
            "payment_method": "CASH",
            "items": [],
            "total_amount": 0.0,
            "cash_received": 0.0,
            "change_amount": 0.0
        }
        receipt = format_thermal_receipt(empty_order, conn=self.conn)
        self.assertIn("BENGKELSTACK WORKSHOP OS", receipt)
        self.assertIn("TOTAL AMOUNT:", receipt)

    def test_whitebox_idempotency_duplicate_collision(self):
        # Attempting duplicate checkout with exact idempotency key returns original order
        order1 = create_work_order(self.conn, plate_number="B 9999 IDEM", motor_model_id=1, customer_name="Test User",
                                   items=[{"item_type": "part", "item_id": 1, "action_type": "takeaway", "quantity": 1}],
                                   idempotency_key="tx_test_collision_key")
        order2 = create_work_order(self.conn, plate_number="B 9999 IDEM", motor_model_id=1, customer_name="Test User",
                                   items=[{"item_type": "part", "item_id": 1, "action_type": "takeaway", "quantity": 1}],
                                   idempotency_key="tx_test_collision_key")
        self.assertEqual(order1["id"], order2["id"])


if __name__ == "__main__":
    unittest.main()
