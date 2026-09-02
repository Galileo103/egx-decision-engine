"""Smoke tests for the EGX Decision Engine API.

Environment is overridden BEFORE app.main is imported: the scheduler is disabled
and the database points at a temp file. No test hits the network — the watchlist
price enrichment is monkeypatched out.
"""
from __future__ import annotations

import os
import tempfile

# Must happen before any `app.*` import.
os.environ["SCHEDULER_ENABLED"] = "0"
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix="egx_smoke_"), "test_egx.db")
os.environ["DB_PATH"] = _TMP_DB
os.environ["EGX_DB_PATH"] = _TMP_DB  # tolerate either env-var name in config

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """TestClient with lifespan (init_db) run; scheduler stays off via env."""
    from app.main import app  # imported here so env overrides above apply

    with TestClient(app) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "session" in data


def test_screener_list(client: TestClient) -> None:
    resp = client.get("/api/screener/list")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert data, "scanner registry must not be empty"
    assert "error" not in data


def test_backtest_strategies(client: TestClient) -> None:
    resp = client.get("/api/backtest/strategies")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert all(isinstance(name, str) for name in data)


def test_portfolio_size_math(client: TestClient) -> None:
    resp = client.post(
        "/api/portfolio/size",
        json={"account": 100000, "risk_pct": 1.0, "entry": 100.0, "stop": 95.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "error" not in data
    # risk 1% of 100k = 1000 EGP; 5 EGP risk/share -> 200 shares
    assert data["shares"] == 200
    assert abs(float(data["risk_amount"]) - 1000.0) < 1e-6


def test_portfolio_size_rejects_bad_stop(client: TestClient) -> None:
    resp = client.post(
        "/api/portfolio/size",
        json={"account": 100000, "risk_pct": 1.0, "entry": 100.0, "stop": 105.0},
    )
    assert resp.status_code == 200
    data = resp.json()
    # A long stop above entry is invalid: expect an error (or at least no positive size)
    assert "error" in data or data.get("shares", 0) <= 0


def test_watchlist_crud(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Keep the GET enrichment off the network.
    import tradingview_mcp.core.services.yahoo_finance_service as yf

    monkeypatch.setattr(yf, "get_prices_bulk", lambda symbols: [])

    # Add
    resp = client.post("/api/watchlist", json={"symbol": "COMI", "note": "smoke"})
    assert resp.status_code == 200
    assert resp.json().get("ok") is True

    # List contains it
    resp = client.get("/api/watchlist")
    assert resp.status_code == 200
    rows = resp.json()["watchlist"]
    assert any(row["symbol"] == "COMI" for row in rows)

    # Delete
    resp = client.delete("/api/watchlist/COMI")
    assert resp.status_code == 200
    assert resp.json().get("ok") is True

    # Gone
    resp = client.get("/api/watchlist")
    assert resp.status_code == 200
    rows = resp.json()["watchlist"]
    assert not any(row["symbol"] == "COMI" for row in rows)
