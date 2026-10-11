import sqlite3
from typing import List, Optional, Dict, Any
from app.pricing_engine import calculate_item_pricing, calculate_cart_pricing
from app.repositories import (
    get_motor_model,
    get_part,
    get_service,
    update_part,
    update_service,
    list_parts,
    list_services,
)
from app.custom_fee_repository import (
    set_custom_install_fee,
    list_custom_fees_for_model,
)
from app.security import sanitize_input_str


def normalize_plate(plate: str) -> str:
    return " ".join(plate.strip().upper().split())


def find_vehicle_by_plate(conn: sqlite3.Connection, plate_number: str) -> Optional[Dict[str, Any]]:
    norm_plate = normalize_plate(plate_number)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT v.id, v.plate_number, v.motor_model_id, v.customer_name,
               m.brand, m.model_name
        FROM vehicles v
        JOIN motor_models m ON v.motor_model_id = m.id
        WHERE v.plate_number = ?;
        """,
        (norm_plate,)
    )
    row = cursor.fetchone()
    return dict(row) if row is not None else None


def get_or_create_vehicle(
    conn: sqlite3.Connection,
    plate_number: str,
    motor_model_id: int,
    customer_name: str
) -> Dict[str, Any]:
    # ponytail: clean find-or-create logic with strict input sanitization
    norm_plate = normalize_plate(plate_number)
    clean_name = sanitize_input_str(customer_name)
    if not norm_plate:
        raise ValueError("plate_number cannot be empty")
    if not clean_name:
        raise ValueError("customer_name cannot be empty")

    existing = find_vehicle_by_plate(conn, norm_plate)
    if existing:
        # Update motor_model_id or customer_name if changed
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE vehicles SET motor_model_id = ?, customer_name = ? WHERE id = ?;",
            (motor_model_id, clean_name, existing["id"])
        )
        conn.commit()
        return find_vehicle_by_plate(conn, norm_plate)

    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO vehicles (plate_number, motor_model_id, customer_name) VALUES (?, ?, ?);",
        (norm_plate, motor_model_id, clean_name)
    )
    conn.commit()
    return find_vehicle_by_plate(conn, norm_plate)


def quick_update_master_price(
    conn: sqlite3.Connection,
    item_type: str,
    item_id: int,
    new_price: Optional[float] = None,
    new_install_fee: Optional[float] = None,
    motor_model_id: Optional[int] = None,
    save_as_model_custom: bool = False
) -> Dict[str, Any]:
    # ponytail: atomic update directly to existing master records
    if item_type == "part":
        part = get_part(conn, item_id)
        if not part:
            raise ValueError(f"Part with id {item_id} not found")

        updated_retail = float(new_price) if new_price is not None else float(part["retail_price"])
        updated_default_fee = float(new_install_fee) if (new_install_fee is not None and not save_as_model_custom) else float(part["default_install_fee"])

        update_part(
            conn,
            part_id=item_id,
            part_code=part["part_code"],
            name=part["name"],
            cost_price=part["cost_price"],
            retail_price=updated_retail,
            default_install_fee=updated_default_fee
        )

        if save_as_model_custom and motor_model_id is not None and new_install_fee is not None:
            set_custom_install_fee(
                conn,
                part_id=item_id,
                motor_model_id=motor_model_id,
                custom_install_fee=float(new_install_fee)
            )

        return {"success": True, "item_type": "part", "item_id": item_id}

    elif item_type == "service":
        svc = get_service(conn, item_id)
        if not svc:
            raise ValueError(f"Service with id {item_id} not found")

        updated_fee = float(new_price) if new_price is not None else float(svc["standard_fee"])
        update_service(
            conn,
            service_id=item_id,
            service_name=svc["service_name"],
            standard_fee=updated_fee
        )
        return {"success": True, "item_type": "service", "item_id": item_id}

    else:
        raise ValueError(f"Invalid item_type: {item_type}")


def create_work_order(
    conn: sqlite3.Connection,
    plate_number: str,
    motor_model_id: int,
    customer_name: str,
    items: List[Dict[str, Any]],
    status: str = "COMPLETED",
    payment_method: str = "CASH",
    cash_received: Optional[float] = None
) -> Dict[str, Any]:
    if not items:
        raise ValueError("Cart items cannot be empty")

    # 1. Ensure vehicle exists
    vehicle = get_or_create_vehicle(conn, plate_number, motor_model_id, customer_name)
    vehicle_id = vehicle["id"]

    # 2. Process items (handle manual overrides and quick master update)
    processed_items = []
    total_amount = 0.0

    for item in items:
        # Check if caller wants to save manual price as standard in master tables
        save_as_std = item.get("save_as_standard", False)
        save_as_custom = item.get("save_as_model_custom", False)

        item_type = item["item_type"]
        item_id = item["item_id"]
        action_type = item.get("action_type", "installed")
        qty = int(item.get("qty", item.get("quantity", 1)))

        # Base calculation from pricing engine
        calc = calculate_item_pricing(conn, item_type, item_id, action_type, motor_model_id=motor_model_id)

        # Allow manual price override if provided in item dict
        actual_price = float(item["price"]) if "price" in item else calc["price"]
        actual_install_fee = float(item["install_fee"]) if "install_fee" in item else calc["install_fee"]

        if action_type == "takeaway":
            actual_install_fee = 0.0

        subtotal = round((actual_price + actual_install_fee) * qty, 2)

        if save_as_std:
            quick_update_master_price(
                conn,
                item_type=item_type,
                item_id=item_id,
                new_price=actual_price,
                new_install_fee=actual_install_fee if action_type == "installed" else None,
                motor_model_id=motor_model_id,
                save_as_model_custom=save_as_custom
            )

        processed_items.append({
            "item_type": item_type,
            "item_id": item_id,
            "action_type": action_type,
            "price": actual_price,
            "install_fee": actual_install_fee,
            "subtotal": subtotal,
        })
        total_amount += subtotal

    total_amount = round(total_amount, 2)

    # Calculate cash and change
    pay_method = payment_method.strip().upper() if payment_method else "CASH"
    if pay_method == "CASH":
        cash = float(cash_received) if cash_received is not None else total_amount
        change = round(max(0.0, cash - total_amount), 2)
    else:
        cash = total_amount
        change = 0.0

    # 3. Insert work order
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO work_orders
            (vehicle_id, status, total_amount, payment_method, cash_received, change_amount)
        VALUES (?, ?, ?, ?, ?, ?);
        """,
        (vehicle_id, status, total_amount, pay_method, cash, change)
    )
    order_id = cursor.lastrowid

    # 4. Insert work order items
    for p_item in processed_items:
        cursor.execute(
            """
            INSERT INTO work_order_items
                (work_order_id, item_type, item_id, action_type, price, install_fee, subtotal)
            VALUES (?, ?, ?, ?, ?, ?, ?);
            """,
            (
                order_id,
                p_item["item_type"],
                p_item["item_id"],
                p_item["action_type"],
                p_item["price"],
                p_item["install_fee"],
                p_item["subtotal"],
            )
        )

    conn.commit()
    return get_work_order(conn, order_id)


def get_work_order(conn: sqlite3.Connection, work_order_id: int) -> Optional[Dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT wo.id, wo.vehicle_id, wo.status, wo.total_amount,
               wo.payment_method, wo.cash_received, wo.change_amount, wo.created_at,
               v.plate_number, v.customer_name, v.motor_model_id,
               m.brand, m.model_name
        FROM work_orders wo
        JOIN vehicles v ON wo.vehicle_id = v.id
        JOIN motor_models m ON v.motor_model_id = m.id
        WHERE wo.id = ?;
        """,
        (work_order_id,)
    )
    wo_row = cursor.fetchone()
    if not wo_row:
        return None

    # Fetch items with names
    cursor.execute(
        """
        SELECT woi.id, woi.work_order_id, woi.item_type, woi.item_id, woi.action_type,
               woi.price, woi.install_fee, woi.subtotal,
               CASE
                 WHEN woi.item_type = 'part' THEN p.name
                 ELSE s.service_name
               END as item_name,
               CASE
                 WHEN woi.item_type = 'part' THEN p.part_code
                 ELSE NULL
               END as part_code
        FROM work_order_items woi
        LEFT JOIN parts p ON woi.item_type = 'part' AND woi.item_id = p.id
        LEFT JOIN services s ON woi.item_type = 'service' AND woi.item_id = s.id
        WHERE woi.work_order_id = ?
        ORDER BY woi.id;
        """,
        (work_order_id,)
    )
    items = [dict(r) for r in cursor.fetchall()]

    return {
        "id": wo_row["id"],
        "status": wo_row["status"],
        "total_amount": wo_row["total_amount"],
        "payment_method": wo_row["payment_method"] if "payment_method" in wo_row.keys() else "CASH",
        "cash_received": wo_row["cash_received"] if "cash_received" in wo_row.keys() else wo_row["total_amount"],
        "change_amount": wo_row["change_amount"] if "change_amount" in wo_row.keys() else 0.0,
        "created_at": wo_row["created_at"],
        "vehicle": {
            "id": wo_row["vehicle_id"],
            "plate_number": wo_row["plate_number"],
            "customer_name": wo_row["customer_name"],
            "motor_model_id": wo_row["motor_model_id"],
            "brand": wo_row["brand"],
            "model_name": wo_row["model_name"],
        },
        "items": items,
    }


def get_service_history_by_plate(conn: sqlite3.Connection, plate_number: str) -> Optional[Dict[str, Any]]:
    # ponytail: single join vehicle check followed by sorted order items assembly
    vehicle = find_vehicle_by_plate(conn, plate_number)
    if not vehicle:
        return None

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, vehicle_id, status, total_amount, created_at
        FROM work_orders
        WHERE vehicle_id = ?
        ORDER BY created_at DESC, id DESC;
        """,
        (vehicle["id"],)
    )
    wo_rows = cursor.fetchall()

    work_orders = []
    for wo in wo_rows:
        wo_id = wo["id"]
        cursor.execute(
            """
            SELECT woi.id, woi.item_type, woi.item_id, woi.action_type,
                   woi.price, woi.install_fee, woi.subtotal,
                   CASE
                     WHEN woi.item_type = 'part' THEN p.name
                     ELSE s.service_name
                   END as item_name,
                   CASE
                     WHEN woi.item_type = 'part' THEN p.part_code
                     ELSE NULL
                   END as part_code
            FROM work_order_items woi
            LEFT JOIN parts p ON woi.item_type = 'part' AND woi.item_id = p.id
            LEFT JOIN services s ON woi.item_type = 'service' AND woi.item_id = s.id
            WHERE woi.work_order_id = ?
            ORDER BY woi.id;
            """,
            (wo_id,)
        )
        items = [dict(r) for r in cursor.fetchall()]
        work_orders.append({
            "id": wo["id"],
            "status": wo["status"],
            "total_amount": wo["total_amount"],
            "created_at": wo["created_at"],
            "items": items
        })

    return {
        "vehicle_id": vehicle["id"],
        "plate_number": vehicle["plate_number"],
        "customer_name": vehicle["customer_name"],
        "motor_model_id": vehicle["motor_model_id"],
        "brand": vehicle["brand"],
        "model_name": vehicle["model_name"],
        "work_orders": work_orders,
    }


def get_model_pricing_reference(conn: sqlite3.Connection, motor_model_id: int) -> Optional[Dict[str, Any]]:
    # ponytail: aggregate historical model usage and catalog install pricing in two fast queries
    motor = get_motor_model(conn, motor_model_id)
    if not motor:
        return None

    # 1. Historical parts & services applied to this motor model
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT 
            woi.item_type,
            woi.item_id,
            CASE WHEN woi.item_type = 'part' THEN p.name ELSE s.service_name END AS item_name,
            CASE WHEN woi.item_type = 'part' THEN p.part_code ELSE NULL END AS part_code,
            COUNT(woi.id) AS usage_count,
            ROUND(AVG(woi.price), 2) AS avg_price,
            ROUND(AVG(woi.install_fee), 2) AS avg_install_fee,
            MAX(wo.created_at) AS last_used_at,
            MAX(woi.price) AS latest_price,
            MAX(woi.install_fee) AS latest_install_fee
        FROM work_orders wo
        JOIN vehicles v ON wo.vehicle_id = v.id
        JOIN work_order_items woi ON wo.id = woi.work_order_id
        LEFT JOIN parts p ON woi.item_type = 'part' AND woi.item_id = p.id
        LEFT JOIN services s ON woi.item_type = 'service' AND woi.item_id = s.id
        WHERE v.motor_model_id = ?
        GROUP BY woi.item_type, woi.item_id
        ORDER BY usage_count DESC, last_used_at DESC;
        """,
        (motor_model_id,)
    )
    historical_items = [dict(r) for r in cursor.fetchall()]

    # 2. Configured custom install fees for this model
    custom_fees = list_custom_fees_for_model(conn, motor_model_id)
    custom_fee_map = {cf["part_id"]: cf["custom_install_fee"] for cf in custom_fees}

    # 3. Estimated catalog pricing for this model
    all_parts = list_parts(conn)
    parts_estimates = []
    for p in all_parts:
        is_custom = p["id"] in custom_fee_map
        applicable_fee = custom_fee_map[p["id"]] if is_custom else float(p["default_install_fee"])
        installed_estimate = round(float(p["retail_price"]) + applicable_fee, 2)
        parts_estimates.append({
            "id": p["id"],
            "part_code": p["part_code"],
            "name": p["name"],
            "retail_price": float(p["retail_price"]),
            "default_install_fee": float(p["default_install_fee"]),
            "applicable_install_fee": applicable_fee,
            "installed_estimate": installed_estimate,
            "is_custom_fee": is_custom,
        })

    all_services = list_services(conn)
    services_estimates = [
        {
            "id": s["id"],
            "service_name": s["service_name"],
            "standard_fee": float(s["standard_fee"])
        }
        for s in all_services
    ]

    return {
        "motor_model": motor,
        "historical_items": historical_items,
        "custom_install_fees": custom_fees,
        "catalog_estimates": {
            "parts": parts_estimates,
            "services": services_estimates,
        }
    }


def format_thermal_receipt(wo: Dict[str, Any], width: int = 40, conn: Optional[sqlite3.Connection] = None) -> str:
    # ponytail: stdlib clean mono-spaced formatting for 58mm/80mm thermal ESC/POS
    ws_name = "BENGKELSTACK WORKSHOP"
    ws_header = "LAYANAN SERVIS & SUKU CADANG"
    ws_footer = "Garansi Servis 7 Hari / 500 KM"
    curr_sym = "Rp"

    if conn is not None:
        try:
            from app.repositories import get_workshop_settings
            st = get_workshop_settings(conn)
            ws_name = st.get("workshop_name", ws_name)
            ws_header = st.get("receipt_header", ws_header)
            ws_footer = st.get("receipt_footer", ws_footer)
            curr_sym = st.get("currency_symbol", curr_sym)
        except Exception:
            pass

    def fmt_val(val: float) -> str:
        formatted = f"{val:,.0f}".replace(",", ".")
        return f"{curr_sym} {formatted}"

    lines = []
    lines.append("=" * width)
    lines.append(ws_name.center(width))
    lines.append(ws_header.center(width))
    lines.append("=" * width)

    v = wo.get("vehicle", {})
    lines.append(f"No. Nota : WO-{wo.get('id', 0):05d}")
    lines.append(f"Waktu    : {wo.get('created_at', '-')}")
    lines.append(f"Plat     : {v.get('plate_number', '-')} ({v.get('brand', '')} {v.get('model_name', '')})")
    lines.append(f"Pelanggan: {v.get('customer_name', '-')}")
    lines.append(f"Status   : {wo.get('status', 'COMPLETED')}")
    lines.append(f"METODE   : {wo.get('payment_method', 'CASH')}")
    lines.append("-" * width)
    lines.append(f"{'ITEM':<20} {'AKSI':<8} {'SUBTOTAL':>10}")
    lines.append("-" * width)

    for it in wo.get("items", []):
        name = (it.get("item_name") or "Item")[:19]
        action = "PASANG" if it.get("action_type") == "installed" else "BELI"
        subtotal = fmt_val(it.get("subtotal", 0))
        lines.append(f"{name:<20} {action:<8} {subtotal:>10}")
        if it.get("action_type") == "installed" and it.get("install_fee", 0) > 0 and it.get("item_type") == "part":
            part_p = fmt_val(it.get("price", 0))
            fee_p = fmt_val(it.get("install_fee", 0))
            lines.append(f"  Part: {part_p} | Ongkos: {fee_p}")

    lines.append("-" * width)
    total_str = fmt_val(wo.get("total_amount", 0))
    lines.append(f"{'TOTAL BAYAR:':<22} {total_str:>17}")

    if wo.get("payment_method") == "CASH" and wo.get("cash_received", 0) > 0:
        cash_str = fmt_val(wo.get("cash_received", 0))
        chg_str = fmt_val(wo.get("change_amount", 0))
        lines.append(f"{'TUNAI DITERIMA:':<22} {cash_str:>17}")
        lines.append(f"{'UANG KEMBALIAN:':<22} {chg_str:>17}")

    lines.append("=" * width)
    lines.append("Terima kasih atas kunjungan Anda!".center(width))
    lines.append(ws_footer.center(width))
    lines.append("=" * width)
    return "\n".join(lines)


