import unittest
import sqlite3
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from database.db import run_migrations
from app.repositories import create_part, get_part
from app.invoice_vision import InvoiceDocument, InvoiceItem
from app.catalog_matcher import (
    match_part_in_catalog,
    reconcile_invoice_document,
    calculate_retail_with_margin,
    CatalogMatchResult
)


class TestCatalogMatcher(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON;")
        run_migrations(self.conn)

        # Seed catalog
        self.part1 = create_part(self.conn, "08232-2MB-K00", "AHM Oil MPX2 0.8L", 38000.0, 52000.0, 5000.0)
        self.part2 = create_part(self.conn, "2DP-E7641-00", "V-Belt NMAX 155", 85000.0, 115000.0, 20000.0)
        self.part3 = create_part(self.conn, "U24EPR9", "Busi Denso Standard", 12000.0, 18000.0, 5000.0)

    def tearDown(self):
        self.conn.close()

    def test_calculate_retail_with_margin(self):
        # 40000 cost with min 25% margin -> at least 50000
        # If current price is 45000 (< 25%), must suggest 50000
        suggested, is_violation = calculate_retail_with_margin(cost_price=40000.0, current_retail=45000.0, min_margin_pct=25.0)
        self.assertTrue(is_violation)
        self.assertEqual(suggested, 50000.0)

        # If current price is 55000 (> 25%), keep current price
        suggested2, is_violation2 = calculate_retail_with_margin(cost_price=40000.0, current_retail=55000.0, min_margin_pct=25.0)
        self.assertFalse(is_violation2)
        self.assertEqual(suggested2, 55000.0)

    def test_exact_sku_match(self):
        item = InvoiceItem(
            sku="08232-2MB-K00",
            description="OLI MPX2 AHM 0.8L",
            qty=10,
            unit_price=40000.0,
            subtotal=400000.0
        )
        match = match_part_in_catalog(self.conn, item)
        self.assertIsInstance(match, CatalogMatchResult)
        self.assertEqual(match.part_id, self.part1["id"])
        self.assertEqual(match.match_type, "EXACT_SKU")
        self.assertEqual(match.confidence, 1.0)
        self.assertEqual(match.cost_delta, 2000.0)  # 40000 new vs 38000 old
        self.assertEqual(match.suggested_retail, 52000.0)

    def test_fuzzy_sku_and_desc_match(self):
        # OCR typo in SKU: "08232 2MB K00" (spaces instead of dashes)
        item = InvoiceItem(
            sku="08232 2MB K00",
            description="AHM OIL MPX2",
            qty=5,
            unit_price=39000.0,
            subtotal=195000.0
        )
        match = match_part_in_catalog(self.conn, item)
        self.assertEqual(match.part_id, self.part1["id"])
        self.assertIn(match.match_type, ("FUZZY_SKU", "FUZZY_DESC"))
        self.assertGreaterEqual(match.confidence, 0.8)

    def test_unmatched_part(self):
        item = InvoiceItem(
            sku="UNKNOWN-999",
            description="BARANG TIDAK DIKENAL GUDANG",
            qty=1,
            unit_price=10000.0,
            subtotal=10000.0
        )
        match = match_part_in_catalog(self.conn, item)
        self.assertIsNone(match.part_id)
        self.assertEqual(match.match_type, "UNMATCHED")
        self.assertEqual(match.confidence, 0.0)

    def test_reconcile_invoice_document(self):
        inv = InvoiceDocument(
            vendor="Yamaha Genuine Parts",
            invoice_number="INV-YGP-11",
            date="2026-10-10",
            items=[
                InvoiceItem(sku="2DP-E7641-00", description="V-BELT NMAX", qty=4, unit_price=90000.0, subtotal=360000.0),
                InvoiceItem(sku="U24EPR9", description="BUSI DENSO", qty=10, unit_price=13000.0, subtotal=130000.0)
            ],
            subtotal=490000.0,
            tax_amount=53900.0,
            grand_total=543900.0
        )
        results = reconcile_invoice_document(self.conn, inv, apply_update=True)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].match_type, "EXACT_SKU")
        self.assertEqual(results[1].match_type, "EXACT_SKU")

        # Verify DB cost_price was updated
        updated_part1 = get_part(self.conn, self.part2["id"])
        self.assertEqual(updated_part1["cost_price"], 90000.0)


if __name__ == "__main__":
    unittest.main()
