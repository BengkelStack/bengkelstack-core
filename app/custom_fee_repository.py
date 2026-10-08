import sqlite3
from typing import List, Optional, Dict, Any


def set_custom_install_fee(
    conn: sqlite3.Connection,
    part_id: int,
    motor_model_id: int,
    custom_install_fee: float
) -> Dict[str, Any]:
    # ponytail: native SQLite ON CONFLICT upsert handles atomic set/update
    if custom_install_fee < 0:
        raise ValueError("custom_install_fee cannot be negative")

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO part_motor_installations (part_id, motor_model_id, custom_install_fee)
        VALUES (?, ?, ?)
        ON CONFLICT(part_id, motor_model_id)
        DO UPDATE SET custom_install_fee = excluded.custom_install_fee;
        """,
        (part_id, motor_model_id, float(custom_install_fee))
    )
    conn.commit()
    return get_custom_install_fee(conn, part_id, motor_model_id)


def get_custom_install_fee(
    conn: sqlite3.Connection,
    part_id: int,
    motor_model_id: int
) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, part_id, motor_model_id, custom_install_fee
        FROM part_motor_installations
        WHERE part_id = ? AND motor_model_id = ?;
        """,
        (part_id, motor_model_id)
    )
    row = cursor.fetchone()
    return dict(row) if row is not None else None


def delete_custom_install_fee(
    conn: sqlite3.Connection,
    part_id: int,
    motor_model_id: int
) -> bool:
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM part_motor_installations WHERE part_id = ? AND motor_model_id = ?;",
        (part_id, motor_model_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def list_custom_fees_for_model(
    conn: sqlite3.Connection,
    motor_model_id: int
) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT pmi.id, pmi.part_id, pmi.motor_model_id, pmi.custom_install_fee,
               p.part_code, p.name AS part_name, p.retail_price, p.default_install_fee
        FROM part_motor_installations pmi
        JOIN parts p ON pmi.part_id = p.id
        WHERE pmi.motor_model_id = ?
        ORDER BY p.name;
        """,
        (motor_model_id,)
    )
    return [dict(row) for row in cursor.fetchall()]
