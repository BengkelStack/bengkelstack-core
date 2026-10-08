import sqlite3
from typing import List, Optional, Dict, Any


def _dict_row(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


# ==========================================
# MASTER MOTOR (motor_models)
# ==========================================

def create_motor_model(conn: sqlite3.Connection, brand: str, model_name: str) -> Dict[str, Any]:
    # ponytail: minimal parameter validation, direct stdlib insert
    if not brand.strip() or not model_name.strip():
        raise ValueError("Brand and model_name cannot be empty")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO motor_models (brand, model_name) VALUES (?, ?);",
        (brand.strip(), model_name.strip())
    )
    conn.commit()
    model_id = cursor.lastrowid
    return get_motor_model(conn, model_id)


def get_motor_model(conn: sqlite3.Connection, model_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT id, brand, model_name FROM motor_models WHERE id = ?;", (model_id,))
    return _dict_row(cursor.fetchone())


def list_motor_models(conn: sqlite3.Connection, search: Optional[str] = None) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    if search:
        query = "%" + search.strip() + "%"
        cursor.execute(
            "SELECT id, brand, model_name FROM motor_models WHERE brand LIKE ? OR model_name LIKE ? ORDER BY brand, model_name;",
            (query, query)
        )
    else:
        cursor.execute("SELECT id, brand, model_name FROM motor_models ORDER BY brand, model_name;")
    return [dict(row) for row in cursor.fetchall()]


def update_motor_model(conn: sqlite3.Connection, model_id: int, brand: str, model_name: str) -> Optional[Dict[str, Any]]:
    if not brand.strip() or not model_name.strip():
        raise ValueError("Brand and model_name cannot be empty")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE motor_models SET brand = ?, model_name = ? WHERE id = ?;",
        (brand.strip(), model_name.strip(), model_id)
    )
    conn.commit()
    return get_motor_model(conn, model_id)


def delete_motor_model(conn: sqlite3.Connection, model_id: int) -> bool:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM motor_models WHERE id = ?;", (model_id,))
    conn.commit()
    return cursor.rowcount > 0


# ==========================================
# MASTER JASA SERVIS (services)
# ==========================================

def create_service(conn: sqlite3.Connection, service_name: str, standard_fee: float) -> Dict[str, Any]:
    if not service_name.strip():
        raise ValueError("Service name cannot be empty")
    if standard_fee < 0:
        raise ValueError("Standard fee cannot be negative")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO services (service_name, standard_fee) VALUES (?, ?);",
        (service_name.strip(), float(standard_fee))
    )
    conn.commit()
    service_id = cursor.lastrowid
    return get_service(conn, service_id)


def get_service(conn: sqlite3.Connection, service_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute("SELECT id, service_name, standard_fee FROM services WHERE id = ?;", (service_id,))
    return _dict_row(cursor.fetchone())


def list_services(conn: sqlite3.Connection, search: Optional[str] = None) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    if search:
        query = "%" + search.strip() + "%"
        cursor.execute(
            "SELECT id, service_name, standard_fee FROM services WHERE service_name LIKE ? ORDER BY service_name;",
            (query,)
        )
    else:
        cursor.execute("SELECT id, service_name, standard_fee FROM services ORDER BY service_name;")
    return [dict(row) for row in cursor.fetchall()]


def update_service(conn: sqlite3.Connection, service_id: int, service_name: str, standard_fee: float) -> Optional[Dict[str, Any]]:
    if not service_name.strip():
        raise ValueError("Service name cannot be empty")
    if standard_fee < 0:
        raise ValueError("Standard fee cannot be negative")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE services SET service_name = ?, standard_fee = ? WHERE id = ?;",
        (service_name.strip(), float(standard_fee), service_id)
    )
    conn.commit()
    return get_service(conn, service_id)


def delete_service(conn: sqlite3.Connection, service_id: int) -> bool:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM services WHERE id = ?;", (service_id,))
    conn.commit()
    return cursor.rowcount > 0


# ==========================================
# MASTER SUKU CADANG (parts)
# ==========================================

def create_part(
    conn: sqlite3.Connection,
    part_code: str,
    name: str,
    cost_price: float,
    retail_price: float,
    default_install_fee: float
) -> Dict[str, Any]:
    # ponytail: direct constraint check & insert
    if not part_code.strip() or not name.strip():
        raise ValueError("part_code and name cannot be empty")
    if cost_price < 0 or retail_price < 0 or default_install_fee < 0:
        raise ValueError("Prices and fees cannot be negative")

    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO parts (part_code, name, cost_price, retail_price, default_install_fee) "
        "VALUES (?, ?, ?, ?, ?);",
        (part_code.strip().upper(), name.strip(), float(cost_price), float(retail_price), float(default_install_fee))
    )
    conn.commit()
    return get_part(conn, cursor.lastrowid)


def get_part(conn: sqlite3.Connection, part_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, part_code, name, cost_price, retail_price, default_install_fee FROM parts WHERE id = ?;",
        (part_id,)
    )
    return _dict_row(cursor.fetchone())


def get_part_by_code(conn: sqlite3.Connection, part_code: str) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, part_code, name, cost_price, retail_price, default_install_fee FROM parts WHERE part_code = ?;",
        (part_code.strip().upper(),)
    )
    return _dict_row(cursor.fetchone())


def list_parts(conn: sqlite3.Connection, search: Optional[str] = None) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    if search:
        query = "%" + search.strip() + "%"
        cursor.execute(
            "SELECT id, part_code, name, cost_price, retail_price, default_install_fee "
            "FROM parts WHERE part_code LIKE ? OR name LIKE ? ORDER BY name;",
            (query, query)
        )
    else:
        cursor.execute(
            "SELECT id, part_code, name, cost_price, retail_price, default_install_fee "
            "FROM parts ORDER BY name;"
        )
    return [dict(row) for row in cursor.fetchall()]


def update_part(
    conn: sqlite3.Connection,
    part_id: int,
    part_code: str,
    name: str,
    cost_price: float,
    retail_price: float,
    default_install_fee: float
) -> Optional[Dict[str, Any]]:
    if not part_code.strip() or not name.strip():
        raise ValueError("part_code and name cannot be empty")
    if cost_price < 0 or retail_price < 0 or default_install_fee < 0:
        raise ValueError("Prices and fees cannot be negative")

    cursor = conn.cursor()
    cursor.execute(
        "UPDATE parts SET part_code = ?, name = ?, cost_price = ?, retail_price = ?, default_install_fee = ? "
        "WHERE id = ?;",
        (part_code.strip().upper(), name.strip(), float(cost_price), float(retail_price), float(default_install_fee), part_id)
    )
    conn.commit()
    return get_part(conn, part_id)


def delete_part(conn: sqlite3.Connection, part_id: int) -> bool:
    cursor = conn.cursor()
    cursor.execute("DELETE FROM parts WHERE id = ?;", (part_id,))
    conn.commit()
    return cursor.rowcount > 0

