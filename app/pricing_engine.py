import sqlite3
from typing import List, Optional, Dict, Any
from app.repositories import get_part, get_service


def calculate_item_pricing(
    conn: sqlite3.Connection,
    item_type: str,
    item_id: int,
    action_type: str,
    motor_model_id: Optional[int] = None
) -> Dict[str, Any]:
    # ponytail: direct rule evaluation, zero extra abstraction
    if item_type not in ("part", "service"):
        raise ValueError(f"Invalid item_type: {item_type}. Must be 'part' or 'service'")
    if action_type not in ("takeaway", "installed"):
        raise ValueError(f"Invalid action_type: {action_type}. Must be 'takeaway' or 'installed'")

    if item_type == "part":
        part = get_part(conn, item_id)
        if not part:
            raise ValueError(f"Part with id {item_id} not found")

        price = float(part["retail_price"])
        name = part["name"]
        part_code = part["part_code"]
        is_custom_fee = False

        if action_type == "takeaway":
            install_fee = 0.0
        else:
            # Check model-specific custom fee first
            install_fee = float(part["default_install_fee"])
            if motor_model_id:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT custom_install_fee FROM part_motor_installations "
                    "WHERE part_id = ? AND motor_model_id = ?;",
                    (item_id, motor_model_id)
                )
                row = cursor.fetchone()
                if row is not None:
                    install_fee = float(row["custom_install_fee"])
                    is_custom_fee = True

        subtotal = price + install_fee

        return {
            "item_type": "part",
            "item_id": item_id,
            "part_code": part_code,
            "name": name,
            "action_type": action_type,
            "price": price,
            "install_fee": install_fee,
            "subtotal": subtotal,
            "is_custom_fee": is_custom_fee,
        }

    else:  # service
        service = get_service(conn, item_id)
        if not service:
            raise ValueError(f"Service with id {item_id} not found")

        price = float(service["standard_fee"])
        name = service["service_name"]
        install_fee = 0.0
        subtotal = price

        return {
            "item_type": "service",
            "item_id": item_id,
            "part_code": None,
            "name": name,
            "action_type": action_type,
            "price": price,
            "install_fee": install_fee,
            "subtotal": subtotal,
            "is_custom_fee": False,
        }


def calculate_cart_pricing(
    conn: sqlite3.Connection,
    items: List[Dict[str, Any]],
    motor_model_id: Optional[int] = None
) -> Dict[str, Any]:
    calculated_items = []
    total_amount = 0.0

    for item in items:
        qty = int(item.get("qty", item.get("quantity", 1)))
        calc = calculate_item_pricing(
            conn,
            item_type=item["item_type"],
            item_id=item["item_id"],
            action_type=item.get("action_type", "installed"),
            motor_model_id=motor_model_id
        )
        item_subtotal = round(calc["subtotal"] * qty, 2)
        calc_entry = dict(calc)
        calc_entry["quantity"] = qty
        calc_entry["subtotal"] = item_subtotal
        calculated_items.append(calc_entry)
        total_amount += item_subtotal

    return {
        "items": calculated_items,
        "total_amount": round(total_amount, 2),
    }
