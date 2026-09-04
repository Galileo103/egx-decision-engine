"""Best-setups aggregation — checklist monkeypatched, offline."""
from __future__ import annotations

import os
import tempfile

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_su_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import setups  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean():
    for t in ("setups", "watchlist", "positions", "scanner_hits", "rs_leaders"):
        db.execute(f"DELETE FROM {t}")  # noqa: S608
    yield


def _fake_checklist(table):
    def ck(symbol):
        spec = table.get(symbol)
        if spec is None:
            return {"symbol": symbol, "error": "no history"}
        score, verdict = spec
        pillars = [{"key": k, "label": k, "status": "pass" if i < score else "warn", "text": "t"}
                   for i, k in enumerate(("trend", "support_resistance", "volume", "price_action", "patterns", "risk"))]
        return {"symbol": symbol, "score": score, "verdict": verdict, "headline": f"{symbol} {verdict}",
                "missing": [p["label"] for p in pillars if p["status"] != "pass"], "price": 10.0,
                "pillars": pillars, "risk_plan": {"rr": 2.0}, "levels_position": "mid-range", "as_of": "2026-09-03"}
    return ck


class TestSetups:
    def test_candidate_symbols_union_with_sources(self) -> None:
        db.execute("INSERT INTO watchlist (symbol, note, added_at) VALUES ('AAA', '', 'x')")
        db.execute("INSERT INTO positions (symbol, side, qty, entry, stop, opened_at, note, status) "
                   "VALUES ('BBB','long',1,1,0.9,'2026-09-01T10:00:00','n','open')")
        db.execute("INSERT INTO scanner_hits (date, scanner, symbol, payload_json, created_at) "
                   "VALUES ('2026-09-02','momentum','AAA','{}','x')")
        src = setups.candidate_symbols()
        assert set(src["AAA"]) == {"candidates", "watchlist"}
        assert src["BBB"] == ["held"]

    def test_compute_ranks_persists_and_latest_reads_back(self, monkeypatch) -> None:
        from app.services import checklist

        db.execute("INSERT INTO watchlist (symbol, note, added_at) VALUES ('AAA', '', 'x')")
        db.execute("INSERT INTO watchlist (symbol, note, added_at) VALUES ('BBB', '', 'x')")
        db.execute("INSERT INTO watchlist (symbol, note, added_at) VALUES ('CCC', '', 'x')")
        db.execute("INSERT INTO watchlist (symbol, note, added_at) VALUES ('DDD', '', 'x')")
        monkeypatch.setattr(checklist, "checklist", _fake_checklist({
            "AAA": (3, "watch"), "BBB": (6, "setup"), "CCC": (1, "no_setup"),  # DDD → error
        }))
        monkeypatch.setattr(setups, "_FETCH_PAUSE", 0.0)
        out = setups.compute(persist=True)
        assert "error" not in out
        assert [r["symbol"] for r in out["rows"]] == ["BBB", "AAA", "CCC"]   # setup, watch, no_setup
        assert out["errors"] == 1 and out["counts"] == {"setup": 1, "watch": 1, "no_setup": 1}
        assert out["rows"][0]["pillars"]["risk"] == "pass" and out["rows"][1]["missing"]
        stored = setups.latest()
        assert stored["stored"] is True and stored["rows"][0]["symbol"] == "BBB"
        assert setups.latest(min_score=5)["rows"][0]["symbol"] == "BBB" and setups.latest(min_score=5)["total"] == 1
        # Same day re-run replaces rather than duplicates.
        setups.compute(persist=True)
        assert len(db.query("SELECT 1 FROM setups")) == 3

    def test_latest_empty(self) -> None:
        assert setups.latest() == {"rows": [], "date": None, "stored": False, "counts": {}}
