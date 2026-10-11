import difflib
import re
import sqlite3
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

from app.invoice_vision import InvoiceItem, InvoiceDocument
from app.repositories import list_parts, update_part, get_part


@dataclass
class CatalogMatchResult:
    invoice_sku: str
    invoice_desc: str
    invoice_unit_cost: float
    part_id: Optional[int]
    db_sku: Optional[str]
    db_name: Optional[str]
    match_type: str  # EXACT_SKU, FUZZY_SKU, FUZZY_DESC, UNMATCHED
    confidence: float
    old_cost: float
    cost_delta: float
    current_retail: float
    suggested_retail: float
    markup_violation: bool
    auto_updated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "invoice_sku": self.invoice_sku,
            "invoice_desc": self.invoice_desc,
            "invoice_unit_cost": self.invoice_unit_cost,
            "part_id": self.part_id,
            "db_sku": self.db_sku,
            "db_name": self.db_name,
            "match_type": self.match_type,
            "confidence": round(self.confidence, 4),
            "old_cost": self.old_cost,
            "cost_delta": round(self.cost_delta, 2),
            "current_retail": self.current_retail,
            "suggested_retail": self.suggested_retail,
            "markup_violation": self.markup_violation,
            "auto_updated": self.auto_updated,
        }


def _norm_str(s: str) -> str:
    # Remove punctuation, extra spaces, uppercase
    return re.sub(r"[^A-Z0-9]", "", s.strip().upper())


def calculate_retail_with_margin(
    cost_price: float,
    current_retail: float,
    min_margin_pct: float = 25.0
) -> Tuple[float, bool]:
    # ponytail: protect minimum retail markup margin
    min_multiplier = 1.0 + (min_margin_pct / 100.0)
    required_retail = round(cost_price * min_multiplier, -2)

    if current_retail < required_retail:
        return required_retail, True
    return current_retail, False


def match_part_in_catalog(
    conn: sqlite3.Connection,
    item: InvoiceItem,
    min_margin_pct: float = 25.0
) -> CatalogMatchResult:
    parts = list_parts(conn)

    clean_item_sku = _norm_str(item.sku)
    upper_item_desc = item.description.strip().upper()

    best_part = None
    best_type = "UNMATCHED"
    best_confidence = 0.0

    # 1. Exact SKU check
    for p in parts:
        if p["part_code"].strip().upper() == item.sku.strip().upper():
            best_part = p
            best_type = "EXACT_SKU"
            best_confidence = 1.0
            break

    # 2. Normalized SKU check (ignoring hyphens/spaces)
    if not best_part:
        for p in parts:
            if _norm_str(p["part_code"]) == clean_item_sku:
                best_part = p
                best_type = "FUZZY_SKU"
                best_confidence = 0.95
                break

    # 3. Fuzzy SKU SequenceMatcher
    if not best_part and clean_item_sku:
        for p in parts:
            clean_db_sku = _norm_str(p["part_code"])
            ratio = difflib.SequenceMatcher(None, clean_item_sku, clean_db_sku).ratio()
            if ratio >= 0.80 and ratio > best_confidence:
                best_part = p
                best_type = "FUZZY_SKU"
                best_confidence = ratio

    # 4. Fuzzy Description SequenceMatcher
    if not best_part:
        for p in parts:
            db_name = p["name"].strip().upper()
            ratio = difflib.SequenceMatcher(None, upper_item_desc, db_name).ratio()
            if ratio >= 0.70 and ratio > best_confidence:
                best_part = p
                best_type = "FUZZY_DESC"
                best_confidence = ratio

    if best_part is None:
        suggested_retail, is_violation = calculate_retail_with_margin(item.unit_price, 0.0, min_margin_pct)
        return CatalogMatchResult(
            invoice_sku=item.sku,
            invoice_desc=item.description,
            invoice_unit_cost=item.unit_price,
            part_id=None,
            db_sku=None,
            db_name=None,
            match_type="UNMATCHED",
            confidence=0.0,
            old_cost=0.0,
            cost_delta=0.0,
            current_retail=0.0,
            suggested_retail=suggested_retail,
            markup_violation=False,
            auto_updated=False
        )

    old_cost = float(best_part["cost_price"])
    current_retail = float(best_part["retail_price"])
    cost_delta = round(item.unit_price - old_cost, 2)
    suggested_retail, is_violation = calculate_retail_with_margin(item.unit_price, current_retail, min_margin_pct)

    return CatalogMatchResult(
        invoice_sku=item.sku,
        invoice_desc=item.description,
        invoice_unit_cost=item.unit_price,
        part_id=best_part["id"],
        db_sku=best_part["part_code"],
        db_name=best_part["name"],
        match_type=best_type,
        confidence=best_confidence,
        old_cost=old_cost,
        cost_delta=cost_delta,
        current_retail=current_retail,
        suggested_retail=suggested_retail,
        markup_violation=is_violation,
        auto_updated=False
    )


def reconcile_invoice_document(
    conn: sqlite3.Connection,
    invoice_doc: InvoiceDocument,
    apply_update: bool = False,
    min_margin_pct: float = 25.0
) -> List[CatalogMatchResult]:
    results: List[CatalogMatchResult] = []

    for item in invoice_doc.items:
        match = match_part_in_catalog(conn, item, min_margin_pct=min_margin_pct)

        if apply_update and match.part_id and match.confidence >= 0.75:
            # Update part cost price and retail price if violation
            p = get_part(conn, match.part_id)
            if p:
                new_cost = item.unit_price
                new_retail = match.suggested_retail if match.markup_violation else float(p["retail_price"])
                update_part(
                    conn,
                    part_id=match.part_id,
                    part_code=p["part_code"],
                    name=p["name"],
                    cost_price=new_cost,
                    retail_price=new_retail,
                    default_install_fee=float(p["default_install_fee"])
                )
                match.auto_updated = True

        results.append(match)

    return results
