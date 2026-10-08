import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import get_connection, run_migrations
from app.repositories import (
    create_motor_model,
    create_part,
    create_service,
)
from app.custom_fee_repository import set_custom_install_fee
from app.work_order_service import create_work_order


def seed():
    conn = run_migrations()
    cursor = conn.cursor()

    # Clear existing sample data if any
    cursor.execute("DELETE FROM work_order_items;")
    cursor.execute("DELETE FROM work_orders;")
    cursor.execute("DELETE FROM vehicles;")
    cursor.execute("DELETE FROM part_motor_installations;")
    cursor.execute("DELETE FROM parts;")
    cursor.execute("DELETE FROM services;")
    cursor.execute("DELETE FROM motor_models;")
    conn.commit()

    print("Seeding Master Motor Models...")
    m_beat = create_motor_model(conn, "Honda", "Beat 110 FI")
    m_vario125 = create_motor_model(conn, "Honda", "Vario 125 eSP")
    m_vario160 = create_motor_model(conn, "Honda", "Vario 160")
    m_pcx = create_motor_model(conn, "Honda", "PCX 160")
    m_nmax = create_motor_model(conn, "Yamaha", "NMAX 155 Connected")
    m_aerox = create_motor_model(conn, "Yamaha", "Aerox 155")
    m_mio = create_motor_model(conn, "Yamaha", "Mio M3 125")
    m_satria = create_motor_model(conn, "Suzuki", "Satria F150")

    print("Seeding Master Spare Parts...")
    p_mpx2 = create_part(conn, "OIL-MPX2", "Ahm Oil MPX2 0.8L", 42000, 54000, 5000)
    p_spx2 = create_part(conn, "OIL-SPX2", "Ahm Oil SPX2 0.8L", 52000, 68000, 5000)
    p_yml = create_part(conn, "OIL-YML", "Yamalube Power Matic 0.8L", 43000, 56000, 5000)
    p_busi = create_part(conn, "SPK-NGK-CPR9", "Busi NGK CPR9EA-9", 18000, 25000, 5000)
    p_pad_fr = create_part(conn, "BRK-PAD-FR", "Kampas Rem Depan Cakram", 32000, 45000, 10000)
    p_vbelt_k44 = create_part(conn, "BLT-K44", "Drive Belt K44 Beat/Vario", 65000, 85000, 15000)
    p_vbelt_b65 = create_part(conn, "BLT-B65", "Drive Belt B65 NMAX/Aerox", 95000, 125000, 20000)
    p_roller = create_part(conn, "ROL-SET", "Roller CVT Set Original", 45000, 65000, 15000)
    p_ban_fr = create_part(conn, "TIRE-80-90", "Ban Tubeless 80/90-14 FDR", 165000, 215000, 15000)

    print("Seeding Master Services...")
    s_ringan = create_service(conn, "Servis Ringan / Tune Up Injeksi", 45000)
    s_cvt = create_service(conn, "Servis Pembersihan CVT & Pelumasan", 40000)
    s_ganti_ban = create_service(conn, "Jasa Bongkar Pasang Ban Tubeless", 20000)
    s_kuras_rem = create_service(conn, "Kuras & Bleeding Minyak Rem Depan/Belakang", 30000)

    print("Seeding Custom Install Fees (Model-Specific)...")
    # NMAX and Aerox CVT disassembly requires extra labor: 30.000 instead of 20.000 default
    set_custom_install_fee(conn, p_vbelt_b65["id"], m_nmax["id"], 30000)
    set_custom_install_fee(conn, p_vbelt_b65["id"], m_aerox["id"], 30000)
    set_custom_install_fee(conn, p_roller["id"], m_nmax["id"], 25000)
    set_custom_install_fee(conn, p_roller["id"], m_aerox["id"], 25000)

    print("Seeding Sample Historical Work Orders...")
    # Sample 1: Honda Vario B 1234 XYZ
    create_work_order(
        conn,
        plate_number="B 1234 XYZ",
        motor_model_id=m_vario125["id"],
        customer_name="Pak Rahmad",
        items=[
            {"item_type": "part", "item_id": p_mpx2["id"], "action_type": "installed"},
            {"item_type": "service", "item_id": s_ringan["id"], "action_type": "installed"}
        ]
    )

    create_work_order(
        conn,
        plate_number="B 1234 XYZ",
        motor_model_id=m_vario125["id"],
        customer_name="Pak Rahmad",
        items=[
            {"item_type": "part", "item_id": p_pad_fr["id"], "action_type": "installed"},
            {"item_type": "part", "item_id": p_busi["id"], "action_type": "takeaway"}
        ]
    )

    # Sample 2: Yamaha NMAX B 5678 NMX
    create_work_order(
        conn,
        plate_number="B 5678 NMX",
        motor_model_id=m_nmax["id"],
        customer_name="Mas Dimas",
        items=[
            {"item_type": "part", "item_id": p_yml["id"], "action_type": "installed"},
            {"item_type": "part", "item_id": p_vbelt_b65["id"], "action_type": "installed"},
            {"item_type": "service", "item_id": s_cvt["id"], "action_type": "installed"}
        ]
    )

    print("Seed complete! Total master data and sample transactions populated.")
    conn.close()


if __name__ == "__main__":
    seed()
