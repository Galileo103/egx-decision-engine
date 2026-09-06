"""Task 9 — investor-type flows: parsing the pasted EGX "Investor Type" page,
storing sessions, 5/20-session reads. Offline."""
from __future__ import annotations

import os
import tempfile

os.environ["SCHEDULER_ENABLED"] = "0"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="egx_flows_"), "t.db")

import pytest  # noqa: E402

from app import db  # noqa: E402
from app.services import flows  # noqa: E402

PAGE = """The Egyptian Exchange - Today's market watch - Investor Type
All Securities & Bonds   Securities Only   Bonds Only
Investor Type\tSell Value(LE)\tBuy Value(LE)\tNet Value(LE)
Egyptians\t1,234,567,890\t1,300,000,000\t65,432,110
Arab\t100,000,000\t80,000,000\t-20,000,000
Non-Arab Foreigners\t300,000,000\t254,567,890\t-45,432,110
Individuals by Nationality
Investor Type\tSell Value(LE)\tBuy Value(LE)\tNet Value(LE)
Egyptians\t900,000,000\t1,000,000,000\t100,000,000
Arab\t50,000,000\t40,000,000\t-10,000,000
Non-Arab Foreigners\t20,000,000\t14,567,890\t-5,432,110
Institutions by Nationality
Investor Type\tSell Value(LE)\tBuy Value(LE)\tNet Value(LE)
Egyptians\t334,567,890\t300,000,000\t-34,567,890
Arab\t50,000,000\t40,000,000\t-10,000,000
Non-Arab Foreigners\t280,000,000\t240,000,000\t-40,000,000
"""

PAGE_AR = """البورصة المصرية - متابعة السوق اليوم - نوع المستثمر
نوع المستثمر\tقيمة البيع\tقيمة الشراء\tصافي القيمة
المصريين\t1,000\t1,200\t200
العرب\t300\t250\t-50
الأجانب\t500\t350\t-150
الأفراد
المصريين\t600\t700\t100
العرب\t100\t80\t-20
الأجانب\t50\t40\t-10
المؤسسات
المصريين\t400\t500\t100
العرب\t200\t170\t-30
الأجانب\t450\t310\t-140
"""


@pytest.fixture(scope="module", autouse=True)
def _database():
    db.init_db()
    yield
    db.close_conn()


@pytest.fixture(autouse=True)
def _clean():
    db.execute("DELETE FROM investor_flows")
    yield


class TestParse:
    def test_full_page_reads_three_tables_and_recomputes_net(self) -> None:
        out = flows.parse_egx_text(PAGE)
        assert out["ok"] is True and out["warnings"] == []
        assert out["totals"]["foreign"] == {"sell": 300_000_000.0, "buy": 254_567_890.0, "net": -45_432_110.0,
                                            "net_reported": -45_432_110.0}
        assert out["totals"]["arab"]["net"] == -20_000_000.0 and out["totals"]["egyptians"]["net"] == 65_432_110.0
        assert out["individuals"]["egyptians"]["net"] == 100_000_000.0
        assert out["institutions"]["foreign"]["net"] == -40_000_000.0
        # "Non-Arab Foreigners" must not be mistaken for the Arab row
        assert out["individuals"]["arab"]["sell"] == 50_000_000.0

    def test_arabic_labels_and_unicode_minus(self) -> None:
        out = flows.parse_egx_text(PAGE_AR.replace("-150", "−150"))
        assert out["ok"] is True
        assert out["totals"]["foreign"]["net"] == -150.0 and out["totals"]["foreign"]["net_reported"] == -150.0
        assert out["institutions"]["arab"]["net"] == -30.0 and out["individuals"]["egyptians"]["buy"] == 700.0

    def test_partial_and_inconsistent_pastes_warn(self) -> None:
        # only the total table copied
        head = PAGE.split("Individuals by Nationality")[0]
        out = flows.parse_egx_text(head)
        assert out["ok"] is True and out["individuals"] == {} and any("Could not find" in w for w in out["warnings"])
        # a typo in the reported net is flagged but buy − sell wins
        out2 = flows.parse_egx_text(PAGE.replace("-45,432,110", "-4,432,110", 1))
        assert out2["totals"]["foreign"]["net"] == -45_432_110.0
        assert any("differs from buy" in w for w in out2["warnings"])
        # individuals + institutions not adding up to the total is flagged
        out3 = flows.parse_egx_text(PAGE.replace("1,000,000,000", "1,500,000,000", 1))
        assert any("does not match the total" in w for w in out3["warnings"])
        # rubbish
        assert flows.parse_egx_text("")["error"] == "nothing pasted"
        bad = flows.parse_egx_text("hello world 1 2 3")
        assert bad["ok"] is False and "three nationalities" in bad["error"]

    def test_totals_rebuilt_when_first_table_missing(self) -> None:
        body = "Individuals by Nationality" + PAGE.split("Individuals by Nationality", 1)[1]
        out = flows.parse_egx_text(body)
        assert out["ok"] is True and any("rebuilt" in w for w in out["warnings"])
        assert out["totals"]["foreign"] == {"sell": 300_000_000.0, "buy": 254_567_890.0, "net": -45_432_110.0}


class TestStore:
    def test_record_history_summary_delete(self) -> None:
        res = flows.record(PAGE, "2026-09-03")
        assert res["ok"] is True and res["date"] == "2026-09-03" and res["scope"] == "all"
        assert res["net_foreign"] == -45_432_110.0 and res["net_institutions"] == -84_567_890.0
        assert res["net_individuals"] == 84_567_890.0 and res["net_foreign_inst"] == -40_000_000.0
        assert res["total_value"] == 1_634_567_890.0
        assert "foreigners net sold 45m EGP" in res["reading"] and "distribution" in res["reading"]
        # same date again replaces, not duplicates
        assert flows.record(PAGE, "2026-09-03")["ok"] is True
        assert len(flows.history()) == 1
        last = flows.latest()
        assert last["date"] == "2026-09-03" and last["tables"]["institutions"]["foreign"]["buy"] == 240_000_000.0
        summ = flows.summary()
        assert summ["stored"] == 1 and summ["latest"]["net_foreign"] == -45_432_110.0
        assert summ["windows"]["5"]["sessions"] == 1 and summ["windows"]["5"]["net_foreign_neg_sessions"] == 1
        assert "1 session(s) stored" in summ["reading"]
        assert flows.delete("2026-09-03")["ok"] is True
        assert "no flows row" in flows.delete("2026-09-03")["error"]
        assert flows.summary()["stored"] == 0 and "paste the EGX page" in flows.summary()["reading"]

    def test_validation_errors(self) -> None:
        assert "date must be" in flows.record(PAGE, "soon")["error"]
        assert "scope must be" in flows.record(PAGE, "2026-09-03", scope="stocks")["error"]
        assert "nothing pasted" in flows.record("", "2026-09-03")["error"]
        assert flows.record(PAGE, None)["ok"] is True          # defaults to the last trading day
        assert len(flows.history()) == 1 and len(flows.history()[0]["date"]) == 10

    def test_streak_reading_after_five_sessions(self) -> None:
        for d in ("2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03"):
            flows.record(PAGE, d)
        summ = flows.summary()
        assert summ["stored"] == 5 and summ["windows"]["5"]["net_foreign"] == -45_432_110.0 * 5
        assert summ["windows"]["20"]["net_foreign_neg_sessions"] == 5
        assert "net sellers on 5 of the last 5 sessions" in summ["reading"]
        assert "persistent foreign selling" in summ["reading"]
        assert [r["date"] for r in summ["series"]] == ["2026-08-30", "2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03"]
        # buyers' version
        buy_page = PAGE.replace("300,000,000\t254,567,890", "254,567,890\t300,000,000")
        db.execute("DELETE FROM investor_flows")
        for d in ("2026-09-01", "2026-09-02", "2026-09-03"):
            flows.record(buy_page, d)
        assert "foreign money is coming in" in flows.summary()["reading"]
        # scopes are separate rows
        flows.record(PAGE, "2026-09-03", scope="securities")
        assert flows.summary("securities")["stored"] == 1 and flows.summary()["stored"] == 3
