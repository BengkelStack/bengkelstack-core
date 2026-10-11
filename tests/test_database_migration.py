import unittest
import sqlite3
import os
import sys

# Ensure app package is importable
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import get_connection, run_migrations


class TestDatabaseMigration(unittest.TestCase):
    def setUp(self):
        # Use in-memory SQLite database for test isolation
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("PRAGMA foreign_keys = ON;")

    def tearDown(self):
        self.conn.close()

    def test_all_seven_core_tables_created(self):
        run_migrations(self.conn)
        cursor = self.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row[0] for row in cursor.fetchall()}
        
        expected_tables = {
            "motor_models",
            "parts",
            "services",
            "part_motor_installations",
            "vehicles",
            "work_orders",
            "work_order_items"
        }
        self.assertTrue(expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}")

    def test_table_columns_match_prd(self):
        run_migrations(self.conn)
        cursor = self.conn.cursor()

        def get_columns(table_name):
            cursor.execute(f"PRAGMA table_info({table_name});")
            return {row[1] for row in cursor.fetchall()}

        self.assertEqual(
            get_columns("motor_models"),
            {"id", "brand", "model_name"}
        )
        self.assertEqual(
            get_columns("parts"),
            {"id", "part_code", "name", "cost_price", "retail_price", "default_install_fee"}
        )
        self.assertEqual(
            get_columns("services"),
            {"id", "service_name", "standard_fee"}
        )
        self.assertEqual(
            get_columns("part_motor_installations"),
            {"id", "part_id", "motor_model_id", "custom_install_fee"}
        )
        self.assertEqual(
            get_columns("vehicles"),
            {"id", "plate_number", "motor_model_id", "customer_name"}
        )
        self.assertEqual(
            get_columns("work_orders"),
            {"id", "vehicle_id", "status", "total_amount", "payment_method", "cash_received", "change_amount", "created_at"}
        )
        self.assertEqual(
            get_columns("work_order_items"),
            {"id", "work_order_id", "item_type", "item_id", "action_type", "price", "install_fee", "subtotal"}
        )

    def test_foreign_key_constraints_enforced(self):
        run_migrations(self.conn)
        cursor = self.conn.cursor()

        # 1. Invalid vehicle -> motor_model_id
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO vehicles (plate_number, motor_model_id, customer_name) VALUES (?, ?, ?);",
                ("B1234XYZ", 999, "Budi")
            )
            self.conn.commit()

        # 2. Invalid part_motor_installations -> part_id & motor_model_id
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO part_motor_installations (part_id, motor_model_id, custom_install_fee) VALUES (?, ?, ?);",
                (999, 999, 15000.0)
            )
            self.conn.commit()

        # 3. Invalid work_orders -> vehicle_id
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO work_orders (vehicle_id, status, total_amount) VALUES (?, ?, ?);",
                (999, "COMPLETED", 50000.0)
            )
            self.conn.commit()

        # 4. Invalid work_order_items -> work_order_id
        with self.assertRaises(sqlite3.IntegrityError):
            cursor.execute(
                "INSERT INTO work_order_items (work_order_id, item_type, item_id, action_type, price, install_fee, subtotal) "
                "VALUES (?, ?, ?, ?, ?, ?, ?);",
                (999, "part", 1, "installed", 45000.0, 10000.0, 55000.0)
            )
            self.conn.commit()

    def test_migration_is_idempotent(self):
        # Running migrations multiple times must not raise or corrupt tables
        run_migrations(self.conn)
        run_migrations(self.conn)
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table';")
        count = cursor.fetchone()[0]
        self.assertGreaterEqual(count, 7)


if __name__ == "__main__":
    unittest.main()
