"""Intraday defined-risk short premium (iron butterfly / iron condor) on the near weekly expiry.
See docs/results/2026-10-27-selling-preregistration.md for the exact rules."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time

import pandas as pd

from .calendar import ExpiryCalendar, lot_size_on
from .config import Params
from .costs import round_trip_costs
from .options import bs_price, years_to
from .signals import BAR

STRUCTURES = {  # (short offset from K0 in points, wing distance from K0 in points)
    "fly": (0, 150),
    "condor": (50, 150),
}


@dataclass(frozen=True)
class SpreadVariant:
    structure: str
    entry: time          # start time of the entry bar
    exit_rule: str       # "time" | "stop_tp"
    stop_frac: float = 0.5
    tp_frac: float = 0.5
    min_slip_pts: float = 0.5
    margin_cap_pct: float = 30.0


class OptionBook:
    """Near-expiry (slot 0) option bars by (side, ts, strike), with a Black-76 fallback for strikes outside the band."""

    def __init__(self, f: pd.DataFrame, opt: pd.DataFrame):
        o = opt[(opt["slot"] == 0)].dropna(subset=["strike", "open", "close"])
        self.f = f
        self.bars = {(sd, t, float(k)): (op, cl) for sd, t, k, op, cl in
                     zip(o["side"], o["ts"], o["strike"], o["open"], o["close"])}
        self.band = {}
        for sd, t, k, iv in zip(o["side"], o["ts"], o["strike"], o["iv"]):
            if iv and iv > 0:
                self.band.setdefault((sd, t), []).append((float(k), float(iv) / 100))
        atm = o[(o["offset"] == 0) & (o["side"] == "CE")]
        self.atm = {t: float(k) for t, k in zip(atm["ts"], atm["strike"])}
        self.modelled = self.lookups = 0

    def price(self, side: str, k: float, j: int, field: str, expiry) -> float | None:
        ts = self.f.index[j]
        self.lookups += 1
        b = self.bars.get((side, ts, k))
        if b is not None:
            return b[0] if field == "open" else b[1]
        band = self.band.get((side, ts))
        if not band:
            return None
        self.modelled += 1
        iv = min(band, key=lambda x: abs(x[0] - k))[1]
        F = self.f["open"].iat[j] if field == "open" else self.f["close"].iat[j]
        t = ts if field == "open" else ts + BAR
        return bs_price(F, k, years_to(expiry, t), iv, side == "CE")


def _slip(px: float, v: SpreadVariant, p: Params) -> float:
    return max(p.slippage_pct * px, v.min_slip_pts)


def simulate_day(book: OptionBook, i: int, v: SpreadVariant, equity: float, p: Params, expiry):
    """Decision bar i, entry at the open of bar i+1. Returns (trade, None) or (None, reason)."""
    f, e = book.f, i + 1
    k0 = book.atm.get(f.index[i])
    if k0 is None:
        return None, "NO_OPTION_DATA"
    so, w = STRUCTURES[v.structure]
    legs = [("CE", k0 + so, +1), ("PE", k0 - so, +1), ("CE", k0 + w, -1), ("PE", k0 - w, -1)]  # +1 short, -1 long
    width = w - so
    entry = []
    for side, k, sg in legs:
        px = book.price(side, k, e, "open", expiry)
        if px is None:
            return None, "NO_OPTION_DATA"
        entry.append(max(px - _slip(px, v, p), 0.05) if sg > 0 else px + _slip(px, v, p))
    credit = sum(sg * x for (_, _, sg), x in zip(legs, entry))
    r_u = width - credit
    if credit <= 0 or r_u <= 0:
        return None, "BAD_CREDIT"
    lot = lot_size_on(p.lot_schedule, f.index[e].date())
    lots = math.floor(equity * p.risk_pct / 100 / (r_u * lot))
    lots = min(lots, math.floor(equity * v.margin_cap_pct / 100 / (width * lot)))
    if lots < 1:
        return None, "LOTS_LT_1"
    qty = lots * lot

    day = f.index.date
    j, exit_j, field, reason = e, None, None, None
    while True:
        end = f.index[j] + BAR
        forced = end.time() >= p.square_off or j + 1 >= len(f) or day[j + 1] != day[j]
        closes = [book.price(sd, k, j, "close", expiry) for sd, k, _ in legs]
        if any(c is None for c in closes):  # data hole: exit at this bar's close using the last good values
            exit_j, field, reason = j, "close", "DATA_GAP"
            break
        val = sum(sg * c for (_, _, sg), c in zip(legs, closes))
        if forced:
            exit_j, field, reason = j, "close", "TIME"
            break
        if v.exit_rule == "stop_tp":
            if val - credit >= v.stop_frac * r_u:
                exit_j, field, reason = j + 1, "open", "STOP"
                break
            if val <= v.tp_frac * credit:
                exit_j, field, reason = j + 1, "open", "TARGET"
                break
        j += 1

    exits = []
    for side, k, sg in legs:
        px = book.price(side, k, exit_j, field, expiry)
        if px is None:  # fall back to the previous bar close
            px = book.price(side, k, exit_j - 1, "close", expiry) or 0.05
        exits.append(px + _slip(px, v, p) if sg > 0 else max(px - _slip(px, v, p), 0.05))
    debit = sum(sg * x for (_, _, sg), x in zip(legs, exits))
    gross = (credit - debit) * qty
    costs = sum(round_trip_costs(qty, x_out, x_in, p.costs) if sg > 0 else round_trip_costs(qty, x_in, x_out, p.costs)
                for (_, _, sg), x_in, x_out in zip(legs, entry, exits))
    net = gross - costs
    exit_ts = f.index[exit_j] if field == "open" else f.index[exit_j] + BAR
    return {"entry_ts": f.index[e], "exit_ts": exit_ts, "side": 0, "structure": v.structure, "k0": k0,
            "expiry": expiry, "lots": lots, "qty": qty, "credit": round(credit, 2), "risk_u": round(r_u, 2),
            "debit": round(debit, 2), "exit_reason": reason, "gross": gross, "costs": costs, "net": net,
            "risk_inr": r_u * qty, "net_r": net / (r_u * qty)}, None


def run_selling(f: pd.DataFrame, book: OptionBook, v: SpreadVariant, p: Params, cal: ExpiryCalendar,
                day_ok: pd.Series | None = None):
    """One position per session. Returns (trades, log)."""
    equity = p.capital
    trades, log = [], []
    decision = (pd.Timestamp.combine(pd.Timestamp("2000-01-01"), v.entry) - BAR).time()
    idx_by_day = {}
    for j, ts in enumerate(f.index):
        if ts.time() == decision:
            idx_by_day[ts.date()] = j
    for d, i in idx_by_day.items():
        rec = {"ts": f.index[i]}
        if day_ok is not None and not bool(day_ok.get(pd.Timestamp(d), False)):
            rec["status"] = "FILTERED"
        elif p.block_expiry_day_entries and cal.is_expiry(d):
            rec["status"] = "EXPIRY_DAY"
        else:
            slot, expiry = cal.choose(d, p.min_dte_days)
            if slot != 0:
                rec["status"] = "NEXT_EXPIRY_NO_DATA"
            else:
                t, why = simulate_day(book, i, v, equity, p, expiry)
                if t is None:
                    rec["status"] = why
                else:
                    rec["status"] = "TRADED"
                    trades.append(t)
                    equity += t["net"]
        log.append(rec)
    return pd.DataFrame(trades), pd.DataFrame(log)
