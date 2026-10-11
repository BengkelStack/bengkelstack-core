import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


@dataclass
class InvoiceItem:
    sku: str
    description: str
    qty: int
    unit_price: float
    subtotal: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sku": self.sku,
            "description": self.description,
            "qty": self.qty,
            "unit_price": self.unit_price,
            "subtotal": self.subtotal,
        }


@dataclass
class InvoiceDocument:
    vendor: str
    invoice_number: str
    date: str
    items: List[InvoiceItem] = field(default_factory=list)
    subtotal: float = 0.0
    tax_amount: float = 0.0
    grand_total: float = 0.0

    @property
    def calculated_items_subtotal(self) -> float:
        return round(sum(it.subtotal for it in self.items), 2)

    @property
    def calculated_grand_total(self) -> float:
        return round(self.calculated_items_subtotal + self.tax_amount, 2)

    @property
    def is_financially_reconciled(self) -> bool:
        # Financial Determinism Invariant
        return abs(self.calculated_grand_total - self.grand_total) < 0.01

    @property
    def reconciliation_delta(self) -> float:
        return round(self.calculated_grand_total - self.grand_total, 2)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vendor": self.vendor,
            "invoice_number": self.invoice_number,
            "date": self.date,
            "items": [it.to_dict() for it in self.items],
            "subtotal": self.subtotal,
            "tax_amount": self.tax_amount,
            "grand_total": self.grand_total,
            "calculated_grand_total": self.calculated_grand_total,
            "is_financially_reconciled": self.is_financially_reconciled,
            "reconciliation_delta": self.reconciliation_delta,
        }


def _clean_num(val: str) -> float:
    # ponytail: parse Indonesian formatted numbers (42.000 -> 42000.0)
    cleaned = val.strip().replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def parse_invoice_text(text: str) -> InvoiceDocument:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]

    # 1. Vendor Identification
    upper_text = text.upper()
    if "ASTRA OTOPARTS" in upper_text or "AHM OIL" in upper_text:
        vendor = "Astra Otoparts"
    elif "YAMAHA" in upper_text:
        vendor = "Yamaha Genuine Parts"
    elif "DENSO" in upper_text:
        vendor = "Denso"
    else:
        vendor = "Generic OEM Supplier"

    # 2. Invoice Number
    inv_no = "INV-UNKNOWN"
    inv_match = re.search(r"(?:FAKTUR(?:\s+PENJUALAN)?|INVOICE(?:\s+NO)?|DELIVERY(?:\s+NOTE)?)\s*[:=]\s*([A-Z0-9\-]+)", text, re.IGNORECASE)
    if inv_match:
        inv_no = inv_match.group(1).strip()

    # 3. Date
    date_str = ""
    date_match = re.search(r"(?:TANGGAL|TGL|DATE)\s*[:=]\s*([0-9\/\-]+)", text, re.IGNORECASE)
    if date_match:
        date_str = date_match.group(1).strip()

    # 4. Line Items
    items: List[InvoiceItem] = []
    # Pattern: SKU (alphanumeric with hyphen) + Description + QTY + @ UnitPrice = Subtotal
    item_pattern = re.compile(
        r"^([A-Z0-9\-]{4,20})\s+(.+?)\s+(\d+)\s*(?:PCS|SET|BUAH|UNIT)?\s*@\s*([0-9\.,]+)\s*=\s*([0-9\.,]+)",
        re.IGNORECASE
    )

    subtotal_val = 0.0
    tax_val = 0.0
    grand_total_val = 0.0

    for line in lines:
        # Check subtotal
        sub_m = re.match(r"^SUBTOTAL\s*[:=]\s*([0-9\.,]+)", line, re.IGNORECASE)
        if sub_m:
            subtotal_val = _clean_num(sub_m.group(1))
            continue

        # Check tax / PPN
        tax_m = re.match(r"^PPN(?:\s*\d+%)?\s*[:=]\s*([0-9\.,]+)", line, re.IGNORECASE)
        if tax_m:
            tax_val = _clean_num(tax_m.group(1))
            continue

        # Check grand total
        tot_m = re.match(r"^(?:GRAND\s+TOTAL|TOTAL)\s*[:=]\s*([0-9\.,]+)", line, re.IGNORECASE)
        if tot_m:
            grand_total_val = _clean_num(tot_m.group(1))
            continue

        # Try match line item
        it_m = item_pattern.match(line)
        if it_m:
            sku = it_m.group(1).strip()
            desc = it_m.group(2).strip()
            qty = int(it_m.group(3))
            u_price = _clean_num(it_m.group(4))
            sub = _clean_num(it_m.group(5))
            items.append(InvoiceItem(sku=sku, description=desc, qty=qty, unit_price=u_price, subtotal=sub))

    if subtotal_val == 0.0 and items:
        subtotal_val = sum(it.subtotal for it in items)

    if grand_total_val == 0.0:
        grand_total_val = subtotal_val + tax_val

    return InvoiceDocument(
        vendor=vendor,
        invoice_number=inv_no,
        date=date_str,
        items=items,
        subtotal=subtotal_val,
        tax_amount=tax_val,
        grand_total=grand_total_val
    )


def parse_invoice_json(data: Dict[str, Any]) -> InvoiceDocument:
    # ponytail: clean JSON converter
    items = [
        InvoiceItem(
            sku=it.get("sku", ""),
            description=it.get("description", ""),
            qty=int(it.get("qty", 1)),
            unit_price=float(it.get("unit_price", 0.0)),
            subtotal=float(it.get("subtotal", 0.0))
        )
        for it in data.get("items", [])
    ]
    return InvoiceDocument(
        vendor=data.get("vendor", "Generic OEM Supplier"),
        invoice_number=data.get("invoice_number", "INV-UNKNOWN"),
        date=data.get("date", ""),
        items=items,
        subtotal=float(data.get("subtotal", sum(it.subtotal for it in items))),
        tax_amount=float(data.get("tax_amount", 0.0)),
        grand_total=float(data.get("grand_total", 0.0))
    )
