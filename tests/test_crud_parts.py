import unittest
import sqlite3
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import run_migrations
from app.repositories import (
    create_part,
    get_part,
    get_part_by_code,
    list_parts,
    update_part,
    delete_part,
)


class TestCrudParts(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_create_and_get_part(self):
        created = create_part(
            self.conn,
            part_code="OIL-MPX2-08",
            name="Ahm Oil MPX2 0.8L",
            cost_price=42000.0,
            retail_price=54000.0,
            default_install_fee=5000.0
        )
        self.assertIsNotNone(created["id"])
        self.assertEqual(created["part_code"], "OIL-MPX2-08")
        self.assertEqual(created["name"], "Ahm Oil MPX2 0.8L")
        self.assertEqual(created["cost_price"], 42000.0)
        self.assertEqual(created["retail_price"], 54000.0)
        self.assertEqual(created["default_install_fee"], 5000.0)

        by_id = get_part(self.conn, created["id"])
        self.assertEqual(by_id["name"], "Ahm Oil MPX2 0.8L")

        by_code = get_part_by_code(self.conn, "OIL-MPX2-08")
        self.assertIsNotNone(by_code)
        self.assertEqual(by_code["id"], created["id"])

    def test_duplicate_part_code_rejected(self):
        create_part(self.conn, "BRK-PAD-01", "Kampas Rem Depan", 25000.0, 35000.0, 10000.0)
        with self.assertRaises(sqlite3.IntegrityError):
            create_part(self.conn, "BRK-PAD-01", "Kampas Rem Lain", 28000.0, 40000.0, 10000.0)

    def test_list_parts_and_search(self):
        create_part(self.conn, "P-01", "Busi NGK CPR9EA", 18000.0, 25000.0, 5000.0)
        create_part(self.conn, "P-02", "Busi Denso U24", 17000.0, 24000.0, 5000.0)
        create_part(self.conn, "P-03", "V-Belt K44", 65000.0, 85000.0, 20000.0)

        all_parts = list_parts(self.conn)
        self.assertEqual(len(all_parts), 3)

        busi = list_parts(self.conn, search="Busi")
        self.assertEqual(len(busi), 2)

        code_match = list_parts(self.conn, search="P-03")
        self.assertEqual(len(code_match), 1)
        self.assertEqual(code_match[0]["name"], "V-Belt K44")

    def test_update_part(self):
        part = create_part(self.conn, "FLT-01", "Filter Udara", 30000.0, 42000.0, 5000.0)
        updated = update_part(
            self.conn,
            part["id"],
            part_code="FLT-01",
            name="Filter Udara Ori Honda",
            cost_price=32000.0,
            retail_price=45000.0,
            default_install_fee=7000.0
        )
        self.assertEqual(updated["name"], "Filter Udara Ori Honda")
        self.assertEqual(updated["cost_price"], 32000.0)
        self.assertEqual(updated["retail_price"], 45000.0)
        self.assertEqual(updated["default_install_fee"], 7000.0)

    def test_delete_part(self):
        part = create_part(self.conn, "ACC-01", "Spion Standar", 20000.0, 30000.0, 5000.0)
        ok = delete_part(self.conn, part["id"])
        self.assertTrue(ok)
        self.assertIsNone(get_part(self.conn, part["id"]))

    def test_validation_negative_prices_rejected(self):
        with self.assertRaises(ValueError):
            create_part(self.conn, "BAD-01", "Part Minus", -100.0, 5000.0, 1000.0)
        with self.assertRaises(ValueError):
            create_part(self.conn, "BAD-02", "Part Minus", 1000.0, -500.0, 1000.0)
        with self.assertRaises(ValueError):
            create_part(self.conn, "BAD-03", "Part Minus", 1000.0, 5000.0, -200.0)


if __name__ == "__main__":
    unittest.main()
