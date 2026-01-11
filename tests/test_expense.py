from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.main import app
from app.models import Currency
from app.routers import currency as currency_router
from app.routers import expense as expense_router
from app.routers import user as user_router


def _seed_currency(session, code: str):
    now = datetime.now(timezone.utc)
    if session.get(Currency, code):
        return
    cur = Currency(code=code, name=code, symbol=code, scale=2, created_at=now, updated_at=now)
    session.add(cur)
    session.commit()


def _create_user(test_client: TestClient) -> dict:
    return test_client.post("/v1/users").json()["user"]


@pytest.fixture()
def client():
    user_router._idem_cache.clear()
    expense_router._idem_cache.clear()
    currency_router._idem_cache.clear()

    engine = create_engine(
        "sqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    engine = engine.execution_options(
        schema_translate_map={"currency": None, "user": None, "expense": None, "deposit": None}
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(bind=conn)
    session = TestingSessionLocal()
    _seed_currency(session, user_router.DEFAULT_BASE_CURRENCY)

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[user_router.get_db] = override_get_db
    app.dependency_overrides[currency_router.get_db] = override_get_db
    app.dependency_overrides[expense_router.get_db] = override_get_db
    test_client = TestClient(app)
    try:
        yield test_client, session
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        user_router._idem_cache.clear()
        expense_router._idem_cache.clear()
        currency_router._idem_cache.clear()


def test_create_category_idempotent_and_conflict(client):
    test_client, _session = client
    user = _create_user(test_client)
    headers = {"X-User-Id": str(user["id"]), "Idempotency-Key": "cat-key"}

    resp1 = test_client.post("/v1/categories", headers=headers, json={"name": "  Groceries  "})
    assert resp1.status_code == 201
    cat = resp1.json()
    assert cat["id"] > 0
    assert cat["name"] == "Groceries"

    resp2 = test_client.post("/v1/categories", headers=headers, json={"name": "  Groceries  "})
    assert resp2.status_code == 201
    assert resp2.json() == cat

    resp_conflict = test_client.post(
        "/v1/categories",
        headers={"X-User-Id": str(user["id"])},
        json={"name": "Groceries"},
    )
    assert resp_conflict.status_code == 409
    assert resp_conflict.json()["detail"] == "category_exists"

    list_resp = test_client.get("/v1/categories", headers={"X-User-Id": str(user["id"])})
    assert list_resp.status_code == 200
    cats = list_resp.json()["data"]
    assert len(cats) == 1
    assert cats[0]["name"] == "Groceries"


def test_create_expense_with_category_and_idempotency(client):
    test_client, session = client
    user = _create_user(test_client)
    headers = {"X-User-Id": str(user["id"])}
    cat = test_client.post(
        "/v1/categories",
        headers={**headers, "Idempotency-Key": "cat-exp"},
        json={"name": "Transport"},
    ).json()

    occurred_at = datetime(2024, 1, 1, 8, 30, tzinfo=timezone.utc).isoformat()
    expected_occurred = datetime.fromisoformat(occurred_at).replace(tzinfo=None).isoformat()
    payload = {
        "amount": "12.34",
        "currency": user_router.DEFAULT_BASE_CURRENCY.lower(),
        "category_id": cat["id"],
        "merchant": "  Uber  ",
        "occurred_at": occurred_at,
        "source_ref": "ride-001",
        "note": "  airport drop ",
    }
    resp = test_client.post(
        "/v1/expenses",
        headers={**headers, "Idempotency-Key": "exp-1"},
        json=payload,
    )
    assert resp.status_code == 201
    exp = resp.json()
    assert exp["id"] > 0
    assert Decimal(exp["amount"]) == Decimal("12.340000")
    assert exp["currency"] == user_router.DEFAULT_BASE_CURRENCY
    assert exp["category_id"] == cat["id"]
    assert exp["merchant"] == "Uber"
    assert exp["note"] == "airport drop"
    assert exp["occurred_at"] == expected_occurred

    resp2 = test_client.post(
        "/v1/expenses",
        headers={**headers, "Idempotency-Key": "exp-1"},
        json=payload,
    )
    assert resp2.status_code == 201
    assert resp2.json() == exp


def test_expense_validation_and_conflicts(client):
    test_client, session = client
    user1 = _create_user(test_client)
    headers1 = {"X-User-Id": str(user1["id"])}

    cat1 = test_client.post("/v1/categories", headers=headers1, json={"name": "Dining"}).json()

    bad_currency = test_client.post(
        "/v1/expenses",
        headers=headers1,
        json={
            "amount": "5",
            "currency": "ZZZ",
            "occurred_at": datetime(2024, 2, 1, tzinfo=timezone.utc).isoformat(),
        },
    )
    assert bad_currency.status_code == 422
    assert bad_currency.json()["detail"] == "unknown_currency"

    first = test_client.post(
        "/v1/expenses",
        headers=headers1,
        json={
            "amount": "20",
            "currency": user_router.DEFAULT_BASE_CURRENCY,
            "category_id": cat1["id"],
            "occurred_at": datetime(2024, 2, 2, tzinfo=timezone.utc).isoformat(),
            "source_ref": "ord-1",
        },
    )
    assert first.status_code == 201

    dup_source = test_client.post(
        "/v1/expenses",
        headers=headers1,
        json={
            "amount": "25",
            "currency": user_router.DEFAULT_BASE_CURRENCY,
            "category_id": cat1["id"],
            "occurred_at": datetime(2024, 2, 3, tzinfo=timezone.utc).isoformat(),
            "source_ref": "ord-1",
        },
    )
    assert dup_source.status_code == 409
    assert dup_source.json()["detail"] == "duplicate_source_ref"

    user2 = _create_user(test_client)
    headers2 = {"X-User-Id": str(user2["id"])}
    invalid_category = test_client.post(
        "/v1/expenses",
        headers=headers2,
        json={
            "amount": "10",
            "currency": user_router.DEFAULT_BASE_CURRENCY,
            "category_id": cat1["id"],
            "occurred_at": datetime(2024, 2, 4, tzinfo=timezone.utc).isoformat(),
        },
    )
    assert invalid_category.status_code == 422
    assert invalid_category.json()["detail"] == "invalid_category"


def test_list_expenses_pagination_and_isolation(client):
    test_client, session = client
    user = _create_user(test_client)
    headers = {"X-User-Id": str(user["id"])}

    times = [
        datetime(2024, 3, 1, tzinfo=timezone.utc),
        datetime(2024, 4, 1, tzinfo=timezone.utc),
        datetime(2024, 5, 1, tzinfo=timezone.utc),
    ]
    amounts = ["30", "40", "50"]
    for ts, amt in zip(times, amounts):
        resp = test_client.post(
            "/v1/expenses",
            headers=headers,
            json={
                "amount": amt,
                "currency": user_router.DEFAULT_BASE_CURRENCY,
                "occurred_at": ts.isoformat(),
            },
        )
        assert resp.status_code == 201

    other_user = _create_user(test_client)
    test_client.post(
        "/v1/expenses",
        headers={"X-User-Id": str(other_user["id"])},
        json={
            "amount": "99",
            "currency": user_router.DEFAULT_BASE_CURRENCY,
            "occurred_at": datetime(2024, 6, 1, tzinfo=timezone.utc).isoformat(),
        },
    )

    page1 = test_client.get(
        "/v1/expenses",
        headers=headers,
        params={"page": 1, "page_size": 2},
    )
    assert page1.status_code == 200
    data1 = page1.json()
    assert data1["total"] == 3
    assert data1["has_next"] is True
    expected_page1 = [t.replace(tzinfo=None).isoformat() for t in (times[2], times[1])]
    assert [item["occurred_at"] for item in data1["data"]] == expected_page1

    page2 = test_client.get(
        "/v1/expenses",
        headers=headers,
        params={"page": 2, "page_size": 2},
    )
    assert page2.status_code == 200
    data2 = page2.json()
    assert data2["total"] == 3
    assert data2["has_next"] is False
    expected_page2 = [times[0].replace(tzinfo=None).isoformat()]
    assert [item["occurred_at"] for item in data2["data"]] == expected_page2
