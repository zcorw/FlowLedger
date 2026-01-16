from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile
from openpyxl import load_workbook
from pydantic import ValidationError

from ..schemas.deposit_import import (
    ImportBalanceItem,
    ImportDepositRequest,
    ImportInstitutionItem,
    ImportProductItem,
)


def _normalize_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _normalize_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return value
    if value is None or value == "":
        return None
    return value


def _read_sheet_rows(ws, headers: List[str]) -> List[Dict[str, Any]]:
    header_row = [cell.value for cell in ws[1]]
    header_map = {str(h).strip(): idx for idx, h in enumerate(header_row) if h is not None}
    missing = [h for h in headers if h not in header_map]
    if missing:
        missing_list = ",".join(missing)
        raise HTTPException(status_code=422, detail=f"missing_headers:{missing_list}")

    rows: List[Dict[str, Any]] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if all(cell is None or str(cell).strip() == "" for cell in row):
            continue
        item: Dict[str, Any] = {}
        for key in headers:
            idx = header_map[key]
            item[key] = row[idx] if idx < len(row) else None
        rows.append(item)
    return rows


def parse_deposit_import_file(upload: UploadFile) -> ImportDepositRequest:
    if not upload.filename or not upload.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=422, detail="invalid_file_type")

    content = upload.file.read()
    try:
        wb = load_workbook(BytesIO(content), data_only=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="invalid_excel") from exc

    if "institutions" not in wb.sheetnames:
        raise HTTPException(status_code=422, detail="missing_sheet:institutions")
    if "products" not in wb.sheetnames:
        raise HTTPException(status_code=422, detail="missing_sheet:products")
    if "product_balances" not in wb.sheetnames:
        raise HTTPException(status_code=422, detail="missing_sheet:product_balances")

    inst_rows = _read_sheet_rows(
        wb["institutions"],
        ["institution_key", "name", "type", "status"],
    )
    prod_rows = _read_sheet_rows(
        wb["products"],
        [
            "product_key",
            "institution_key",
            "name",
            "product_type",
            "currency",
            "status",
            "risk_level",
            "amount",
        ],
    )
    bal_rows = _read_sheet_rows(
        wb["product_balances"],
        ["product_key", "as_of", "amount"],
    )

    institutions: List[ImportInstitutionItem] = []
    for row in inst_rows:
        institutions.append(
            ImportInstitutionItem(
                institution_key=_normalize_str(row["institution_key"]),
                name=_normalize_str(row["name"]),
                type=_normalize_str(row["type"]),
                status=_normalize_str(row["status"]),
            )
        )

    products: List[ImportProductItem] = []
    for row in prod_rows:
        products.append(
            ImportProductItem(
                product_key=_normalize_str(row["product_key"]),
                institution_key=_normalize_str(row["institution_key"]),
                name=_normalize_str(row["name"]),
                product_type=_normalize_str(row["product_type"]) or "deposit",
                currency=_normalize_str(row["currency"]),
                status=_normalize_str(row["status"]) or "active",
                risk_level=_normalize_str(row["risk_level"]) or "stable",
                amount=_normalize_decimal(row["amount"]),
            )
        )

    balances: List[ImportBalanceItem] = []
    for row in bal_rows:
        balances.append(
            ImportBalanceItem(
                product_key=_normalize_str(row["product_key"]),
                as_of=_normalize_datetime(row["as_of"]),
                amount=_normalize_decimal(row["amount"]),
            )
        )

    try:
        return ImportDepositRequest(
            institutions=institutions,
            products=products,
            product_balances=balances,
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
