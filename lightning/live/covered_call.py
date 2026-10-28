"""Covered-call shadow engine (daily): long next-month stock futures + short call ~5% OTM, rolled on the last trading
day before each monthly expiry. Paper fills at quotes: buy at the ask, sell at the bid. NO ORDERS ARE PLACED.

Source interface:
  today() -> date | futures_expiries(sym) -> sorted list[date] | roll_day(d, expiry) -> bool
  fut_quote(sym, expiry) -> {bid, ask, ltp} or None | calls(sym, expiry) -> {strike: {bid, ask, ltp, iv, oi, volume}}"""
from __future__ import annotations

import time
from datetime import date, timedelta

import pandas as pd

from ..costs import round_trip_costs
from ..overlays import FUT_EXCH, FUT_STAMP_BUY, FUT_STT_SELL

SCHEMA = """
CREATE TABLE IF NOT EXISTS cc_cycles (id TEXT PRIMARY KEY, symbol TEXT, expiry TEXT, status TEXT, lot INTEGER,
  d_in TEXT, f_in_bid REAL, f_in_ask REAL, f_in REAL, k REAL, c_in_bid REAL, c_in_ask REAL, c_in REAL,
  d_out TEXT, f_out_bid REAL, f_out_ask REAL, f_out REAL, c_out_bid REAL, c_out_ask REAL, c_out REAL,
  ret_b0 REAL, ret_c5 REAL, net_b0_inr REAL, net_c5_inr REAL, note TEXT);
CREATE TABLE IF NOT EXISTS cc_marks (day TEXT, symbol TEXT, cycle_id TEXT, f_bid REAL, f_ask REAL, c_bid REAL, c_ask REAL,
  mtm_b0 REAL, mtm_c5 REAL, PRIMARY KEY (day, symbol));
CREATE TABLE IF NOT EXISTS cc_log (ts TEXT, symbol TEXT, event TEXT, detail TEXT);
"""


def last_weekday_before(e: date) -> date:
    d = e - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def fut_charges(f_in: float, f_out: float) -> float:
    """Per unit futures charges (no slippage: fills are already at bid/ask)."""
    return FUT_STT_SELL * f_out + FUT_EXCH * (f_in + f_out) + FUT_STAMP_BUY * f_in


class CoveredCallEngine:
    def __init__(self, src, db, cfg: dict, lots: dict, costs: dict):
        self.src, self.db, self.cfg, self.lots, self.costs = src, db, cfg, lots, costs
        db.con.executescript(SCHEMA)

    def _log(self, sym, event, detail=""):
        self.db.insert("cc_log", {"ts": pd.Timestamp.now(tz="Asia/Kolkata"), "symbol": sym, "event": event, "detail": str(detail)[:500]})

    def _open(self, sym, d, expiry, note):
        fq = self.src.fut_quote(sym, expiry)
        calls = self.src.calls(sym, expiry)
        if not fq or not fq.get("ask") or not calls:
            self._log(sym, "OPEN_SKIPPED_NO_QUOTE", f"{expiry}")
            return
        target = fq["ask"] * (1 + self.cfg["otm"])
        k = min((s for s, q in calls.items() if q.get("bid")), key=lambda s: abs(s - target), default=None)
        if k is None:
            self._log(sym, "OPEN_SKIPPED_NO_CALL_BID", f"{expiry}")
            return
        q = calls[k]
        cid = f"{sym}|{expiry.isoformat()}"
        self.db.insert("cc_cycles", {"id": cid, "symbol": sym, "expiry": expiry, "status": "OPEN", "lot": self.lots[sym], "d_in": d,
                                     "f_in_bid": fq["bid"], "f_in_ask": fq["ask"], "f_in": fq["ask"], "k": k,
                                     "c_in_bid": q["bid"], "c_in_ask": q["ask"], "c_in": q["bid"], "note": note})
        self._log(sym, "OPENED", f"{cid} fut@{fq['ask']} call {k}@{q['bid']}")

    def _close(self, cyc, d, reason):
        sym, expiry, k = cyc["symbol"], date.fromisoformat(cyc["expiry"]), cyc["k"]
        fq, calls = self.src.fut_quote(sym, expiry), self.src.calls(sym, expiry)
        q = calls.get(k) if calls else None
        if not fq or not fq.get("bid"):
            self._log(sym, "CLOSE_DEFERRED_NO_FUT_QUOTE", cyc["id"])
            return False
        intrinsic = max(fq["bid"] - k, 0.0)
        if not q or not q.get("ask"):  # far OTM call with no seller: worth about its intrinsic value
            q = {"bid": None, "ask": intrinsic + 0.05}
            self._log(sym, "CALL_NO_QUOTE_FALLBACK", f"{cyc['id']} k={k} -> {q['ask']:.2f}")
        f_out, c_out = fq["bid"], max(q["ask"], intrinsic)  # buy-back never below intrinsic
        lot = cyc["lot"]
        b0 = (f_out - cyc["f_in"]) - fut_charges(cyc["f_in"], f_out)
        c5 = b0 + (cyc["c_in"] - c_out) - round_trip_costs(lot, c_out, cyc["c_in"], self.costs) / lot
        self.db.update("cc_cycles", "id", cyc["id"], {
            "status": "CLOSED", "d_out": d, "f_out_bid": fq["bid"], "f_out_ask": fq["ask"], "f_out": f_out,
            "c_out_bid": q["bid"], "c_out_ask": q["ask"], "c_out": c_out, "ret_b0": b0 / cyc["f_in"], "ret_c5": c5 / cyc["f_in"],
            "net_b0_inr": b0 * lot, "net_c5_inr": c5 * lot, "note": (cyc.get("note") or "") + f" closed:{reason}"})
        self._log(sym, "CLOSED", f"{cyc['id']} b0={b0 / cyc['f_in']:+.4f} c5={c5 / cyc['f_in']:+.4f}")
        return True

    def _mark(self, cyc, d):
        sym, expiry = cyc["symbol"], date.fromisoformat(cyc["expiry"])
        fq, calls = self.src.fut_quote(sym, expiry), self.src.calls(sym, expiry)
        q = (calls or {}).get(cyc["k"])
        if not fq or not q:
            return
        b0 = (fq["bid"] - cyc["f_in"]) * cyc["lot"]
        c5 = b0 + (cyc["c_in"] - q["ask"]) * cyc["lot"]
        self.db.insert("cc_marks", {"day": d, "symbol": sym, "cycle_id": cyc["id"], "f_bid": fq["bid"], "f_ask": fq["ask"],
                                    "c_bid": q["bid"], "c_ask": q["ask"], "mtm_b0": b0, "mtm_c5": c5}, replace=True)

    def step(self):
        d = self.src.today()
        for sym in self.cfg["symbols"]:
            try:
                exps = [e for e in self.src.futures_expiries(sym) if e >= d]
                if len(exps) < 2:
                    self._log(sym, "NO_EXPIRIES", exps)
                    continue
                e0, e1 = exps[0], exps[1]
                open_c = self.db.query("SELECT * FROM cc_cycles WHERE symbol=? AND status='OPEN'", (sym,))
                roll_day = self.src.roll_day(d, e0)
                if open_c and date.fromisoformat(open_c[0]["expiry"]) < d:  # runner was off on the roll day
                    self.db.update("cc_cycles", "id", open_c[0]["id"], {"status": "EXPIRED_UNTRACKED", "note": "missed roll; excluded"})
                    self._log(sym, "MISSED_ROLL", open_c[0]["id"])
                    open_c = []
                if open_c:
                    cyc = open_c[0]
                    if date.fromisoformat(cyc["expiry"]) == e0 and roll_day:
                        if self._close(cyc, d, "ROLL"):
                            self._open(sym, d, e1, "roll")
                    else:
                        self._mark(cyc, d)
                elif roll_day:
                    self._open(sym, d, e1, "start at roll")
                elif (e0 - d).days >= self.cfg["min_days_to_open"]:
                    self._open(sym, d, e0, "start mid-cycle")
            except Exception as e:  # noqa: BLE001 - one symbol's failure must not stop the others
                self._log(sym, "ERROR", f"{type(e).__name__}: {e}")


class ReplayCCSource:
    """NSE bhavcopy closes with synthetic quotes matching the backtest slippage (futures 0.01%, options max(1%, 0.05))."""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.days = sorted(set(df["date"]))
        self._by_day = {d: g for d, g in df.groupby("date")}
        self.d = self.days[0]

    def today(self):
        return self.d

    def roll_day(self, d, expiry):
        before = [x for x in self.days if x < expiry]
        return bool(before) and d == before[-1]

    def futures_expiries(self, sym):
        g = self._by_day[self.d]
        return sorted(set(g[(g["symbol"] == sym) & (g["kind"] == "FUT")]["expiry"]))

    def fut_quote(self, sym, expiry):
        g = self._by_day[self.d]
        r = g[(g["symbol"] == sym) & (g["kind"] == "FUT") & (g["expiry"] == expiry)]
        if r.empty:
            return None
        c = float(r["close"].iat[0])
        return {"bid": c * (1 - 0.0001), "ask": c * (1 + 0.0001), "ltp": c}

    def calls(self, sym, expiry):
        g = self._by_day[self.d]
        r = g[(g["symbol"] == sym) & (g["kind"] == "OPT") & (g["opt"] == "CE") & (g["expiry"] == expiry)]
        out = {}
        for k, c, v in zip(r["strike"], r["close"], r["volume"]):
            s = max(0.01 * c, 0.05)
            out[float(k)] = {"bid": max(c - s, 0.0), "ask": c + s, "ltp": c, "iv": None, "oi": None, "volume": v}
        return out


class DhanCCSource:
    """Live Dhan quotes. Futures ids/expiries from the Dhan scrip master; calls from the stock option chain."""

    def __init__(self, client, scrip_master_csv, equity_ids: dict, chain_segment: str, holidays=()):
        m = pd.read_csv(scrip_master_csv, usecols=["SEM_EXM_EXCH_ID", "SEM_INSTRUMENT_NAME", "SEM_SMST_SECURITY_ID",
                                                   "SEM_TRADING_SYMBOL", "SEM_EXPIRY_DATE"], low_memory=False)
        fut = m[(m["SEM_EXM_EXCH_ID"] == "NSE") & (m["SEM_INSTRUMENT_NAME"] == "FUTSTK")].copy()
        fut["sym"] = fut["SEM_TRADING_SYMBOL"].str.split("-").str[0]
        fut["expiry"] = pd.to_datetime(fut["SEM_EXPIRY_DATE"]).dt.date
        self.fut_ids = {(s, e): int(i) for s, e, i in zip(fut["sym"], fut["expiry"], fut["SEM_SMST_SECURITY_ID"])}
        self.c, self.eq, self.seg = client, equity_ids, chain_segment
        self.holidays = {pd.Timestamp(h).date() for h in holidays}

    def today(self):
        return pd.Timestamp.now(tz="Asia/Kolkata").date()

    def roll_day(self, d, expiry):
        x = expiry - timedelta(days=1)
        while x.weekday() >= 5 or x in self.holidays:
            x -= timedelta(days=1)
        return d >= x

    def futures_expiries(self, sym):
        return sorted(e for (s, e) in self.fut_ids if s == sym)

    def fut_quote(self, sym, expiry):
        sid = self.fut_ids.get((sym, expiry))
        if sid is None:
            return None
        q = self.c.market_quote({"NSE_FNO": [sid]})["NSE_FNO"][str(sid)]
        bid = (q.get("depth", {}).get("buy") or [{}])[0].get("price")
        ask = (q.get("depth", {}).get("sell") or [{}])[0].get("price")
        return {"bid": bid or None, "ask": ask or None, "ltp": q.get("last_price")}

    def calls(self, sym, expiry):
        from .sources import parse_chain
        time.sleep(3.1)  # option chain rate limit: 1 request / 3 s
        ch = parse_chain(self.c.option_chain(self.eq[sym], expiry.isoformat(), self.seg))
        return {k: q for (side, k), q in ch["rows"].items() if side == "CE"}
