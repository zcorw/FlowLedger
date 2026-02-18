from datetime import datetime

from starlette.requests import Request

from app.time_range import normalize_datetime_range


def _request(query_string: bytes) -> Request:
    return Request({"type": "http", "query_string": query_string})


def test_normalize_datetime_range_date_only_to_is_next_day() -> None:
    request = _request(b"from=2026-02-01&to=2026-02-28")
    from_dt = datetime(2026, 2, 1, 15, 30, 0)
    to_dt = datetime(2026, 2, 28, 0, 0, 0)

    normalized_from, normalized_to = normalize_datetime_range(request, from_dt, to_dt)

    assert normalized_from == datetime(2026, 2, 1, 0, 0, 0)
    assert normalized_to == datetime(2026, 3, 1, 0, 0, 0)


def test_normalize_datetime_range_datetime_input_keeps_original() -> None:
    request = _request(b"from=2026-02-01T12:00:00&to=2026-02-28T23:59:59")
    from_dt = datetime(2026, 2, 1, 12, 0, 0)
    to_dt = datetime(2026, 2, 28, 23, 59, 59)

    normalized_from, normalized_to = normalize_datetime_range(request, from_dt, to_dt)

    assert normalized_from == from_dt
    assert normalized_to == to_dt
