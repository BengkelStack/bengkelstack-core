import unittest
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from app.invoice_vision import parse_invoice_text, parse_invoice_json, InvoiceDocument


class TestInvoiceVision(unittest.TestCase):
    def test_parse_astra_otoparts_invoice(self):
        raw_text = """
        PT ASTRA OTOPARTS TBK
        FAKTUR PENJUALAN: INV-AOP-2026-9921
        TANGGAL: 10/10/2026
        08232-2MB-K00 OLI AHM OIL MPX2 0.8L 10 PCS @ 42.000 = 420.000
        45126-KZR-601 SELANG REM DEPAN VARIO 5 PCS @ 35.000 = 175.000
        SUBTOTAL: 595.000
        PPN 11%: 65.450
        TOTAL: 660.450
        """
        doc = parse_invoice_text(raw_text)
        self.assertIsInstance(doc, InvoiceDocument)
        self.assertEqual(doc.vendor, "Astra Otoparts")
        self.assertEqual(doc.invoice_number, "INV-AOP-2026-9921")
        self.assertEqual(len(doc.items), 2)

        # Check line items
        self.assertEqual(doc.items[0].sku, "08232-2MB-K00")
        self.assertEqual(doc.items[0].qty, 10)
        self.assertEqual(doc.items[0].unit_price, 42000.0)
        self.assertEqual(doc.items[0].subtotal, 420000.0)

        # Check financial determinism
        self.assertEqual(doc.subtotal, 595000.0)
        self.assertEqual(doc.tax_amount, 65450.0)
        self.assertEqual(doc.grand_total, 660450.0)
        self.assertTrue(doc.is_financially_reconciled)
        self.assertEqual(doc.reconciliation_delta, 0.0)

    def test_parse_yamaha_genuine_parts_invoice(self):
        raw_text = """
        YAMAHA INDONESIA MOTOR MFG
        INVOICE NO: YGP-JKT-8812
        TGL: 09/10/2026
        2DP-E7641-00 V-BELT NMAX 155 4 PCS @ 95000 = 380000
        B65-E4451-00 SARINGAN UDARA AEROX 6 PCS @ 38000 = 228000
        SUBTOTAL: 608000
        PPN: 66880
        GRAND TOTAL: 674880
        """
        doc = parse_invoice_text(raw_text)
        self.assertEqual(doc.vendor, "Yamaha Genuine Parts")
        self.assertEqual(doc.invoice_number, "YGP-JKT-8812")
        self.assertEqual(len(doc.items), 2)
        self.assertEqual(doc.items[0].sku, "2DP-E7641-00")
        self.assertEqual(doc.items[1].sku, "B65-E4451-00")
        self.assertTrue(doc.is_financially_reconciled)
        self.assertEqual(doc.grand_total, 674880.0)

    def test_parse_denso_invoice(self):
        raw_text = """
        DENSO INDONESIA SALES
        DELIVERY NOTE: DNS-2026-102
        DATE: 08/10/2026
        U24EPR9 BUSI NICKEL DENSO 20 PCS @ 14000 = 280000
        SUBTOTAL: 280000
        PPN: 30800
        GRAND TOTAL: 310800
        """
        doc = parse_invoice_text(raw_text)
        self.assertEqual(doc.vendor, "Denso")
        self.assertEqual(doc.invoice_number, "DNS-2026-102")
        self.assertEqual(len(doc.items), 1)
        self.assertEqual(doc.items[0].sku, "U24EPR9")
        self.assertTrue(doc.is_financially_reconciled)
        self.assertEqual(doc.grand_total, 310800.0)

    def test_financial_discrepancy_detection(self):
        # Grand total intentionally corrupted (tampered or OCR noise)
        raw_text = """
        PT ASTRA OTOPARTS TBK
        FAKTUR: INV-ERR-001
        TANGGAL: 10/10/2026
        PART-01 BUSI 1 PCS @ 10000 = 10000
        SUBTOTAL: 10000
        PPN: 1100
        TOTAL: 50000
        """
        doc = parse_invoice_text(raw_text)
        self.assertFalse(doc.is_financially_reconciled)
        self.assertEqual(doc.calculated_grand_total, 11100.0)
        self.assertEqual(doc.grand_total, 50000.0)
        self.assertEqual(doc.reconciliation_delta, -38900.0)

    def test_parse_structured_json_invoice(self):
        payload = {
            "vendor": "Astra Otoparts",
            "invoice_number": "JSON-INV-001",
            "date": "2026-10-10",
            "items": [
                {
                    "sku": "08232-2MB-K00",
                    "description": "AHM Oil MPX2 0.8L",
                    "qty": 5,
                    "unit_price": 42000,
                    "subtotal": 210000
                }
            ],
            "subtotal": 210000,
            "tax_amount": 23100,
            "grand_total": 233100
        }
        doc = parse_invoice_json(payload)
        self.assertEqual(doc.vendor, "Astra Otoparts")
        self.assertEqual(len(doc.items), 1)
        self.assertTrue(doc.is_financially_reconciled)
        self.assertEqual(doc.grand_total, 233100.0)

    def test_parse_empty_or_malformed_text(self):
        doc = parse_invoice_text("   \n   \n random text without format")
        self.assertEqual(doc.vendor, "Generic OEM Supplier")
        self.assertEqual(doc.invoice_number, "INV-UNKNOWN")
        self.assertEqual(len(doc.items), 0)
        self.assertEqual(doc.grand_total, 0.0)
        self.assertTrue(doc.is_financially_reconciled)


if __name__ == "__main__":
    unittest.main()
