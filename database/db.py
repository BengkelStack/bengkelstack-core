import os
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "workshop.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")


def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


def run_migrations(conn: Optional[sqlite3.Connection] = None, db_path: Optional[str] = None) -> sqlite3.Connection:
    # ponytail: stdlib sqlite3 executescript handles multi-statement schema cleanly
    close_after = False
    if conn is None:
        conn = get_connection(db_path)
        close_after = False

    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn.executescript(schema_sql)

    # Apply incremental migrations safely
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('001_initial_schema');")

    cursor.execute("PRAGMA table_info(work_orders);")
    wo_cols = {r[1] for r in cursor.fetchall()}
    if "payment_method" not in wo_cols:
        cursor.execute("ALTER TABLE work_orders ADD COLUMN payment_method TEXT NOT NULL DEFAULT 'CASH';")
    if "cash_received" not in wo_cols:
        cursor.execute("ALTER TABLE work_orders ADD COLUMN cash_received REAL NOT NULL DEFAULT 0;")
    if "change_amount" not in wo_cols:
        cursor.execute("ALTER TABLE work_orders ADD COLUMN change_amount REAL NOT NULL DEFAULT 0;")

    cursor.execute("INSERT OR IGNORE INTO workshop_settings (id, workshop_name, currency_symbol, currency_code, min_margin_pct) VALUES (1, 'BENGKELSTACK WORKSHOP OS', 'Rp', 'IDR', 25.0);")
    cursor.execute("INSERT OR IGNORE INTO schema_migrations (version) VALUES ('002_settings_and_payments');")
    conn.commit()

    if close_after:
        conn.close()

    return conn


if __name__ == "__main__":
    conn = run_migrations()
    print("Database migrations applied successfully to:", DEFAULT_DB_PATH)
    conn.close()
