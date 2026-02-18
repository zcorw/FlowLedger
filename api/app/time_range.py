from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
import re

from fastapi import Request

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_date_only(raw: Optional[str]) -> bool:
    return bool(raw and _DATE_ONLY_RE.fullmatch(raw.strip()))


def normalize_datetime_range(
    request: Request,
    from_dt: Optional[datetime],
    to_dt: Optional[datetime],
) -> tuple[Optional[datetime], Optional[datetime]]:
    raw_from = request.query_params.get("from")
    raw_to = request.query_params.get("to")

    normalized_from = from_dt
    normalized_to = to_dt

    if _is_date_only(raw_from) and from_dt is not None:
        normalized_from = from_dt.replace(hour=0, minute=0, second=0, microsecond=0)

    if _is_date_only(raw_to) and to_dt is not None:
        normalized_to = (
            to_dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        )

    return normalized_from, normalized_to
