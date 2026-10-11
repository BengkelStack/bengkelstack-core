import unittest
import sqlite3
import threading
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import get_connection, run_migrations
from app.repositories import create_motor_model, create_part, create_service
from app.work_order_service import create_work_order
from app.pricing_engine import calculate_cart_pricing


class TestConcurrencyAndWALResilience(unittest.TestCase):
    def setUp(self):
        # Create a file-backed temp db to test real WAL multi-process/thread concurrency
        import tempfile
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "concurrent_workshop.db")
        
        conn = get_connection(self.db_path)
        run_migrations(conn)

        self.motor = create_motor_model(conn, "Honda", "Vario 160")
        self.part = create_part(conn, "OIL-CONC", "Oli Full Synthetic", 65000.0, 90000.0, 10000.0)
        conn.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_concurrent_work_order_writes_under_wal(self):
        num_threads = 15
        errors = []

        def worker(thread_idx: int):
            try:
                t_conn = get_connection(self.db_path)
                order = create_work_order(
                    t_conn,
                    plate_number=f"B {1000 + thread_idx} CONC",
                    motor_model_id=self.motor["id"],
                    customer_name=f"Customer {thread_idx}",
                    items=[
                        {"item_type": "part", "item_id": self.part["id"], "action_type": "installed"}
                    ]
                )
                if not order or order["total_amount"] != 100000.0:
                    errors.append(f"Thread {thread_idx} order total mismatch: {order}")
                t_conn.close()
            except Exception as e:
                errors.append(f"Thread {thread_idx} exception: {e}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent write errors encountered: {errors}")

        # Verify all 15 orders exist and DB integrity is pristine
        v_conn = get_connection(self.db_path)
        cur = v_conn.cursor()
        total_orders = cur.execute("SELECT COUNT(*) FROM work_orders;").fetchone()[0]
        integrity = cur.execute("PRAGMA integrity_check;").fetchone()[0]
        v_conn.close()

        self.assertEqual(total_orders, num_threads)
        self.assertEqual(integrity, "ok")


if __name__ == "__main__":
    unittest.main()
