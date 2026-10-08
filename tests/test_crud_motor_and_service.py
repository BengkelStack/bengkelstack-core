import unittest
import sqlite3
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import run_migrations
from app.repositories import (
    create_motor_model,
    get_motor_model,
    list_motor_models,
    update_motor_model,
    delete_motor_model,
    create_service,
    get_service,
    list_services,
    update_service,
    delete_service,
)


class TestCrudMotorAndService(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

    def tearDown(self):
        self.conn.close()

    # --- MOTOR MODELS ---
    def test_create_and_get_motor_model(self):
        created = create_motor_model(self.conn, brand="Honda", model_name="Vario 160")
        self.assertIsNotNone(created["id"])
        self.assertEqual(created["brand"], "Honda")
        self.assertEqual(created["model_name"], "Vario 160")

        fetched = get_motor_model(self.conn, created["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["brand"], "Honda")
        self.assertEqual(fetched["model_name"], "Vario 160")

    def test_list_motor_models_filter(self):
        create_motor_model(self.conn, "Honda", "Beat Deluxe")
        create_motor_model(self.conn, "Yamaha", "NMAX 155")
        create_motor_model(self.conn, "Honda", "PCX 160")

        all_models = list_motor_models(self.conn)
        self.assertEqual(len(all_models), 3)

        honda_only = list_motor_models(self.conn, search="Honda")
        self.assertEqual(len(honda_only), 2)

        nmax_only = list_motor_models(self.conn, search="NMAX")
        self.assertEqual(len(nmax_only), 1)
        self.assertEqual(nmax_only[0]["model_name"], "NMAX 155")

    def test_update_motor_model(self):
        created = create_motor_model(self.conn, "Yamaha", "Aerox")
        updated = update_motor_model(self.conn, created["id"], brand="Yamaha", model_name="Aerox 155 Connected")
        self.assertEqual(updated["model_name"], "Aerox 155 Connected")

        fetched = get_motor_model(self.conn, created["id"])
        self.assertEqual(fetched["model_name"], "Aerox 155 Connected")

    def test_delete_motor_model(self):
        created = create_motor_model(self.conn, "Suzuki", "Satria F150")
        ok = delete_motor_model(self.conn, created["id"])
        self.assertTrue(ok)
        self.assertIsNone(get_motor_model(self.conn, created["id"]))

    def test_delete_motor_model_blocked_if_vehicle_exists(self):
        motor = create_motor_model(self.conn, "Honda", "Vario 125")
        # Insert a vehicle referencing this motor_model
        self.conn.execute(
            "INSERT INTO vehicles (plate_number, motor_model_id, customer_name) VALUES (?, ?, ?);",
            ("B3333XYZ", motor["id"], "Rian")
        )
        self.conn.commit()

        # Delete must raise IntegrityError due to ON DELETE RESTRICT
        with self.assertRaises(sqlite3.IntegrityError):
            delete_motor_model(self.conn, motor["id"])

    # --- SERVICES ---
    def test_create_and_get_service(self):
        svc = create_service(self.conn, service_name="Ganti Oli Mesin", standard_fee=15000.0)
        self.assertIsNotNone(svc["id"])
        self.assertEqual(svc["service_name"], "Ganti Oli Mesin")
        self.assertEqual(svc["standard_fee"], 15000.0)

        fetched = get_service(self.conn, svc["id"])
        self.assertEqual(fetched["standard_fee"], 15000.0)

    def test_list_services_filter(self):
        create_service(self.conn, "Servis Ringan", 45000.0)
        create_service(self.conn, "Servis CVT", 60000.0)
        create_service(self.conn, "Ganti Ban Luar", 25000.0)

        all_svc = list_services(self.conn)
        self.assertEqual(len(all_svc), 3)

        cvt = list_services(self.conn, search="CVT")
        self.assertEqual(len(cvt), 1)
        self.assertEqual(cvt[0]["service_name"], "Servis CVT")

    def test_update_service(self):
        svc = create_service(self.conn, "Tune Up", 50000.0)
        updated = update_service(self.conn, svc["id"], service_name="Tune Up Injeksi", standard_fee=55000.0)
        self.assertEqual(updated["service_name"], "Tune Up Injeksi")
        self.assertEqual(updated["standard_fee"], 55000.0)

    def test_delete_service(self):
        svc = create_service(self.conn, "Cuci Salju", 20000.0)
        ok = delete_service(self.conn, svc["id"])
        self.assertTrue(ok)
        self.assertIsNone(get_service(self.conn, svc["id"]))

    def test_validation_non_negative_fee(self):
        with self.assertRaises(ValueError):
            create_service(self.conn, "Servis Error", -1000.0)


if __name__ == "__main__":
    unittest.main()
