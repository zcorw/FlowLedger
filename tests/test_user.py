from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.main import app
from app.models import Currency, User
from app.routers import currency as currency_router
from app.routers import user as user_router


def _seed_currency(session, code: str):
    now = datetime.now(timezone.utc)
    if session.get(Currency, code):
        return
    cur = Currency(code=code, name=code, symbol=code, scale=2, created_at=now, updated_at=now)
    session.add(cur)
    session.commit()


@pytest.fixture()
def client():
    user_router._idem_cache.clear()
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
    test_client = TestClient(app)
    try:
        yield test_client, session
    finally:
        session.close()
        engine.dispose()
        app.dependency_overrides.clear()
        user_router._idem_cache.clear()


def test_register_user_returns_defaults(client):
    test_client, _session = client
    resp = test_client.post(
        "/v1/auth/register",
        headers={"Idempotency-Key": "abc"},
        json={"username": "alice", "password": "strongpass123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["user"]["id"] > 0
    assert data["user"]["username"] == "alice"
    assert data["preferences"]["base_currency"] == user_router.DEFAULT_BASE_CURRENCY
    assert data["preferences"]["timezone"] == user_router.DEFAULT_TIMEZONE
    assert data["preferences"]["language"] == user_router.DEFAULT_LANGUAGE
    assert data["access_token"]

    resp2 = test_client.post(
        "/v1/auth/register",
        headers={"Idempotency-Key": "abc"},
        json={"username": "alice", "password": "strongpass123"},
    )
    assert resp2.status_code == 201
    assert resp2.json() == data


def test_login_with_credentials(client):
    test_client, session = client
    test_client.post(
        "/v1/auth/register",
        json={"username": "bob", "password": "strongpass123"},
    )

    resp_ok = test_client.post(
        "/v1/auth/login",
        json={"username": "bob", "password": "strongpass123"},
    )
    assert resp_ok.status_code == 200
    token = resp_ok.json()["access_token"]
    assert token

    resp_bad = test_client.post(
        "/v1/auth/login",
        json={"username": "bob", "password": "wrongpass"},
    )
    assert resp_bad.status_code == 401


def test_update_preferences_validation(client):
    test_client, session = client
    reg = test_client.post(
        "/v1/auth/register",
        json={"username": "cindy", "password": "strongpass123"},
    ).json()
    token = reg["access_token"]
    u = reg["user"]
    _seed_currency(session, "CNY")

    # valid update
    resp = test_client.patch(
        "/v1/users/me/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"base_currency": "CNY", "timezone": "Asia/Shanghai", "language": "zh-CN"},
    )
    assert resp.status_code == 200
    assert resp.json()["base_currency"] == "CNY"

    # invalid timezone
    resp_bad_tz = test_client.patch(
        "/v1/users/me/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"timezone": "Not/AZone"},
    )
    assert resp_bad_tz.status_code == 422

    # invalid currency not in table
    resp_bad_cur = test_client.patch(
        "/v1/users/me/preferences",
        headers={"Authorization": f"Bearer {token}"},
        json={"base_currency": "ZZZ"},
    )
    assert resp_bad_cur.status_code == 422


def test_link_telegram_conflict(client):
    test_client, session = client
    user1 = test_client.post("/v1/users").json()["user"]
    user2 = test_client.post("/v1/users").json()["user"]

    resp_ok = test_client.post(
        "/v1/users/link-telegram",
        headers={"X-User-Id": str(user1["id"])},
        json={"telegram_user_id": 12345},
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["telegram_user_id"] == 12345

    resp_conflict = test_client.post(
        "/v1/users/link-telegram",
        headers={"X-User-Id": str(user2["id"])},
        json={"telegram_user_id": 12345},
    )
    assert resp_conflict.status_code == 409
