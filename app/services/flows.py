"""Investor-type flows — who bought and who sold, by nationality and by kind.

EGX publishes, after every session, the buy / sell / net traded value of
Egyptians, Arabs and non-Arab foreigners, split into individuals and
institutions ("Today's market watch → Investor Type"). On this exchange it is
the most-watched flow figure there is: foreign selling drives the index far
more than any single chart. The page sits behind a JavaScript bot challenge,
so the app does not scrape it. Instead the user copies the page text (Ctrl+A,
Ctrl+C on the EGX page) and pastes it into the dashboard card; ``parse_egx_text``
finds the three tables, ``record`` stores the session, and ``summary`` turns
the last sessions into sentences ("foreigners net sold 5 of the last 5
sessions").

Values are EGP. Never raises; write functions return ok only after the row exists.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app import db

logger = logging.getLogger(__name__)
CAIRO = ZoneInfo("Africa/Cairo")

NATIONALITIES: tuple[str, ...] = ("egyptians", "arab", "foreign")
GROUPS: tuple[str, ...] = ("totals", "individuals", "institutions")
LABEL = {"egyptians": "Egyptians", "arab": "Arabs", "foreign": "Foreigners (non-Arab)"}
SCOPES: tuple[str, ...] = ("all", "securities", "bonds")

#: Label spellings on the EGX page (English and Arabic), per nationality key.
_NAT_PATTERNS: dict[str, str] = {
    "egyptians": r"(?:Egyptians?|المصريين|مصريين|مصريون)",
    "arab": r"(?:Arabs?|العرب|عرب)",
    "foreign": r"(?:Non[- ]Arab\s+Foreigners?|Foreigners?|الأجانب|أجانب)",
}
_SECTION_IND = re.compile(r"(?:Individuals?\s+by\s+Nationality|الأفراد)", re.IGNORECASE)
_SECTION_INST = re.compile(r"(?:Institutions?\s+by\s+Nationality|المؤسسات)", re.IGNORECASE)
_NUM = r"\(?[-−]?[\d,]+(?:\.\d+)?\)?"


def _now_iso() -> str:
    return datetime.now(CAIRO).isoformat()


def _to_num(tok: str) -> Optional[float]:
    t = tok.strip().replace(",", "").replace("٬", "").replace("،", "").replace("−", "-")
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    try:
        v = float(t)
    except ValueError:
        return None
    return -v if neg else v


def _parse_section(text: str) -> dict[str, dict[str, Any]]:
    """{nat: {sell, buy, net}} from one table's text. Column order on the EGX page is
    Sell, Buy, Net; the net is recomputed as buy − sell so a typo cannot survive."""
    out: dict[str, dict[str, Any]] = {}
    for key, pat in _NAT_PATTERNS.items():
        m = re.search(pat + r"\s*[:\t ]*\s*(" + _NUM + r")\s+(" + _NUM + r")\s+(" + _NUM + r")", text)
        if not m:
            continue
        sell, buy, net = (_to_num(m.group(1)), _to_num(m.group(2)), _to_num(m.group(3)))
        if sell is None or buy is None:
            continue
        out[key] = {"sell": sell, "buy": buy, "net": round(buy - sell, 2), "net_reported": net}
    return out


def parse_egx_text(text: str) -> dict:
    """Parse the pasted "Investor Type" page. Returns {"totals", "individuals",
    "institutions", "warnings", "ok"}; partial tables come back with warnings."""
    raw = str(text or "").replace("\xa0", " ")
    warnings: list[str] = []
    if not raw.strip():
        return {"ok": False, "error": "nothing pasted"}
    i_ind = _SECTION_IND.search(raw)
    i_inst = _SECTION_INST.search(raw)
    if i_ind and i_inst and i_ind.start() < i_inst.start():
        totals_txt, ind_txt, inst_txt = raw[: i_ind.start()], raw[i_ind.start(): i_inst.start()], raw[i_inst.start():]
    elif i_ind and i_inst:
        totals_txt, inst_txt, ind_txt = raw[: i_inst.start()], raw[i_inst.start(): i_ind.start()], raw[i_ind.start():]
    else:
        totals_txt, ind_txt, inst_txt = raw, "", ""
        warnings.append("Could not find the 'Individuals by Nationality' / 'Institutions by Nationality' headings — "
                        "only the total table was read.")
    totals = _parse_section(totals_txt)
    individuals = _parse_section(ind_txt) if ind_txt else {}
    institutions = _parse_section(inst_txt) if inst_txt else {}
    if not totals and individuals and institutions:
        # Some copies drop the first table: rebuild totals from the two groups.
        totals = {k: {"sell": individuals[k]["sell"] + institutions[k]["sell"],
                      "buy": individuals[k]["buy"] + institutions[k]["buy"]}
                  for k in NATIONALITIES if k in individuals and k in institutions}
        for k in totals:
            totals[k]["net"] = round(totals[k]["buy"] - totals[k]["sell"], 2)
        warnings.append("Total table missing — rebuilt from individuals + institutions.")
    missing = [LABEL[k] for k in NATIONALITIES if k not in totals]
    if missing:
        warnings.append("Missing nationalities in the total table: " + ", ".join(missing) + ".")
    # Consistency: totals should equal individuals + institutions within 1%.
    for k in totals:
        if k in individuals and k in institutions:
            s = individuals[k]["buy"] + institutions[k]["buy"]
            if totals[k]["buy"] and abs(s - totals[k]["buy"]) / abs(totals[k]["buy"]) > 0.01:
                warnings.append(f"{LABEL[k]}: individuals + institutions buy ({s:,.0f}) does not match the total "
                                f"({totals[k]['buy']:,.0f}) — check the paste.")
        rep = totals[k].get("net_reported")
        if rep is not None and abs(rep - totals[k]["net"]) > max(1000.0, 0.001 * abs(totals[k]["buy"] or 1)):
            warnings.append(f"{LABEL[k]}: reported net {rep:,.0f} differs from buy − sell {totals[k]['net']:,.0f}.")
    ok = len(totals) == 3
    return {"ok": ok, "totals": totals, "individuals": individuals, "institutions": institutions,
            "warnings": warnings, **({} if ok else {"error": "could not read all three nationalities from the paste"})}


def _derived(parsed: dict) -> dict:
    t, ind, inst = parsed.get("totals") or {}, parsed.get("individuals") or {}, parsed.get("institutions") or {}
    total_value = sum(v.get("buy", 0.0) for v in t.values())
    return {
        "net_egyptians": t.get("egyptians", {}).get("net"),
        "net_arab": t.get("arab", {}).get("net"),
        "net_foreign": t.get("foreign", {}).get("net"),
        "net_individuals": round(sum(v["net"] for v in ind.values()), 2) if ind else None,
        "net_institutions": round(sum(v["net"] for v in inst.values()), 2) if inst else None,
        "net_foreign_inst": inst.get("foreign", {}).get("net"),
        "total_value": round(total_value, 2) if total_value else None,
        "foreign_share_pct": (round((t.get("foreign", {}).get("buy", 0) + t.get("foreign", {}).get("sell", 0))
                                    / (2 * total_value) * 100.0, 2) if total_value else None),
    }


# ── persistence ──────────────────────────────────────────────────────────────


def record(text: str, date: Optional[str] = None, scope: str = "all") -> dict:
    """Parse and store one session's paste. ``date`` defaults to the last trading day."""
    try:
        parsed = parse_egx_text(text)
        if not parsed.get("ok"):
            return {"error": parsed.get("error") or "parse failed", "warnings": parsed.get("warnings", [])}
        if scope not in SCOPES:
            return {"error": f"scope must be one of {', '.join(SCOPES)}"}
        if not date:
            from app import calendar_egx

            date = calendar_egx.last_trading_day(calendar_egx.now_cairo().date()).strftime("%Y-%m-%d")
        d = str(date)[:10]
        try:
            datetime.strptime(d, "%Y-%m-%d")
        except ValueError:
            return {"error": "date must be YYYY-MM-DD"}
        der = _derived(parsed)
        db.execute(
            "INSERT OR REPLACE INTO investor_flows (date, scope, net_egyptians, net_arab, net_foreign, net_individuals, "
            " net_institutions, net_foreign_inst, total_value, payload_json, source, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'paste', ?)",
            (d, scope, der["net_egyptians"], der["net_arab"], der["net_foreign"], der["net_individuals"],
             der["net_institutions"], der["net_foreign_inst"], der["total_value"],
             json.dumps({k: parsed[k] for k in GROUPS}), _now_iso()),
        )
        rows = db.query("SELECT * FROM investor_flows WHERE date = ? AND scope = ?", (d, scope))
        if not rows:
            return {"error": "row was not stored"}
        return {"ok": True, "date": d, "scope": scope, **der, "warnings": parsed.get("warnings", []),
                "reading": reading(_row_out(rows[0]), history(20, scope))}
    except Exception as exc:  # noqa: BLE001
        logger.exception("flows.record failed")
        return {"error": str(exc)}


def delete(date: str, scope: str = "all") -> dict:
    try:
        n = db.execute_rowcount("DELETE FROM investor_flows WHERE date = ? AND scope = ?", (str(date)[:10], scope))
        return {"ok": True, "deleted": n} if n else {"error": f"no flows row for {date} ({scope})"}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _row_out(r: dict) -> dict:
    out = dict(r)
    try:
        out["tables"] = json.loads(out.pop("payload_json") or "{}")
    except (TypeError, ValueError):
        out["tables"] = {}
    return out


def history(days: int = 60, scope: str = "all") -> list[dict]:
    """Stored sessions, oldest first (last ``days`` rows)."""
    try:
        rows = db.query("SELECT * FROM investor_flows WHERE scope = ? ORDER BY date DESC LIMIT ?",
                        (scope, max(1, int(days))))
        return [_row_out(r) for r in reversed(rows)]
    except Exception as exc:  # noqa: BLE001
        logger.warning("flows.history failed: %s", exc)
        return []


def latest(scope: str = "all") -> Optional[dict]:
    h = history(1, scope)
    return h[-1] if h else None


# ── readings ─────────────────────────────────────────────────────────────────


def _fmt_egp(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    a = abs(v)
    if a >= 1e9:
        return f"{v / 1e9:+.2f}bn EGP"
    if a >= 1e6:
        return f"{v / 1e6:+.0f}m EGP"
    return f"{v:+,.0f} EGP"


def summary(scope: str = "all") -> dict:
    """Latest session plus 5- and 20-session sums and streaks per actor."""
    rows = history(60, scope)
    if not rows:
        return {"stored": 0, "latest": None, "reading": "No investor-type data yet — paste the EGX page after the close.",
                "basis": _basis()}
    last = rows[-1]
    keys = ("net_egyptians", "net_arab", "net_foreign", "net_individuals", "net_institutions", "net_foreign_inst")
    out: dict[str, Any] = {"stored": len(rows), "latest": {k: last.get(k) for k in keys + ("date", "total_value")},
                           "windows": {}}
    for n in (5, 20):
        win = rows[-n:]
        agg: dict[str, Any] = {"sessions": len(win)}
        for k in keys:
            vals: list[float] = [float(v) for v in (r.get(k) for r in win) if v is not None]
            agg[k] = round(sum(vals), 2) if vals else None
            agg[k + "_neg_sessions"] = sum(1 for v in vals if v < 0)
        out["windows"][str(n)] = agg
    out["reading"] = reading(last, rows)
    out["series"] = [{"date": r["date"], "net_foreign": r.get("net_foreign"), "net_arab": r.get("net_arab"),
                      "net_egyptians": r.get("net_egyptians"), "net_institutions": r.get("net_institutions"),
                      "net_individuals": r.get("net_individuals"), "total_value": r.get("total_value")} for r in rows]
    out["basis"] = _basis()
    return out


def reading(last: dict, rows: list[dict]) -> str:
    """Two or three sentences a trader can act on."""
    if not last:
        return ""
    parts = []
    nf, na, ne = last.get("net_foreign"), last.get("net_arab"), last.get("net_egyptians")
    ni, nn = last.get("net_institutions"), last.get("net_individuals")
    d = last.get("date")
    if nf is not None:
        parts.append(f"{d}: foreigners net {'bought' if nf >= 0 else 'sold'} {_fmt_egp(abs(nf)).lstrip('+')}"
                     + (f", Arabs net {'bought' if na >= 0 else 'sold'} {_fmt_egp(abs(na)).lstrip('+')}" if na is not None else "")
                     + (f", Egyptians net {'bought' if ne >= 0 else 'sold'} {_fmt_egp(abs(ne)).lstrip('+')}" if ne is not None else "") + ".")
    if ni is not None and nn is not None:
        if ni < 0 < nn:
            parts.append(f"Institutions net sold {_fmt_egp(abs(ni)).lstrip('+')} into retail buying of "
                         f"{_fmt_egp(abs(nn)).lstrip('+')} — distribution: the informed side is leaving.")
        elif ni > 0 > nn:
            parts.append(f"Institutions net bought {_fmt_egp(abs(ni)).lstrip('+')} from retail sellers "
                         f"({_fmt_egp(abs(nn)).lstrip('+')}) — accumulation: the informed side is absorbing.")
        else:
            parts.append(f"Institutions {_fmt_egp(ni)}, individuals {_fmt_egp(nn)} — both on the same side.")
    win: list[float] = [float(v) for v in (r.get("net_foreign") for r in rows[-5:]) if v is not None]
    if len(win) >= 3:
        neg = sum(1 for v in win if v < 0)
        parts.append(f"Foreigners were net sellers on {neg} of the last {len(win)} sessions "
                     f"({_fmt_egp(sum(win))} over the window)"
                     + (" — persistent foreign selling caps rallies here; keep sizes small." if neg >= max(3, len(win) - 1)
                        else " — foreign money is coming in; breakouts have a sponsor." if neg <= 1 else "."))
    else:
        parts.append(f"{len(rows)} session(s) stored so far — the 5- and 20-session reads appear from the third paste.")
    return " ".join(parts)


def _basis() -> str:
    return ("EGX 'Today's market watch → Investor Type' figures, pasted after the close: buy / sell / net traded value "
            "(EGP) for Egyptians, Arabs and non-Arab foreigners, split into individuals and institutions. Net is "
            "recomputed as buy − sell. The page has no feed and sits behind a bot challenge, so the app never "
            "scrapes it; select all on the page, copy, paste here. One row per session and scope (all securities & "
            "bonds by default).")
