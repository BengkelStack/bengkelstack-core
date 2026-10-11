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
    conn.commit()

    if close_after:
        conn.close()

    return conn


if __name__ == "__main__":
    conn = run_migrations()
    print("Database migrations applied successfully to:", DEFAULT_DB_PATH)
    conn.close()
