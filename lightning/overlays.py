"""Futures buy-and-hold with option overlays (protective puts, covered calls), monthly rolls at daily closes.
Rules: docs/results/2026-10-28-hedged-futures-preregistration.md"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .costs import round_trip_costs

FUT_SLIP, FUT_STT_SELL, FUT_EXCH, FUT_STAMP_BUY = 0.0001, 0.0002, 0.0000173, 0.00002
VARIANTS = {"B0": (None, 0.0), "P3": ("PE", -0.03), "P5": ("PE", -0.05), "C3": ("CE", 0.03), "C5": ("CE", 0.05)}


def _opt_slip(px):
    return max(0.01 * px, 0.05)


def cycles_for(sym_df: pd.DataFrame):
    """[(roll_in_day, roll_out_day, expiry)] from the futures contracts of one symbol."""
    fut = sym_df[sym_df["kind"] == "FUT"]
    days = sorted(set(sym_df["date"]))
    exps = sorted(set(fut["expiry"]))
    roll = {}
    for e in exps:
        if e > days[-1]:  # expiry beyond the data: the cycle would be cut short
            continue
        before = [d for d in days if d < e]
        if before:
            roll[e] = before[-1]
    out = []
    for prev, e in zip(exps[:-1], exps[1:]):
        if prev in roll and e in roll and roll[prev] < roll[e]:
            out.append((roll[prev], roll[e], e))
    return out


def run_symbol(sym_df: pd.DataFrame, lot: int, costs: dict) -> pd.DataFrame:
    """One row per cycle with the return of every variant (fraction of futures notional at roll-in)."""
    fut = sym_df[sym_df["kind"] == "FUT"]
    fpx = {(d, e): c for d, e, c in zip(fut["date"], fut["expiry"], fut["close"])}
    opt = sym_df[sym_df["kind"] == "OPT"]
    opx = {(d, e, o, float(k)): (c, v) for d, e, o, k, c, v in zip(opt["date"], opt["expiry"], opt["opt"], opt["strike"], opt["close"], opt["volume"])}
    strikes = {}
    for d, e, o, k in zip(opt["date"], opt["expiry"], opt["opt"], opt["strike"]):
        strikes.setdefault((d, e, o), set()).add(float(k))
    days = sorted(set(sym_df["date"]))
    rows = []
    for d_in, d_out, e in cycles_for(sym_df):
        f0, f1 = fpx.get((d_in, e)), fpx.get((d_out, e))
        if not f0 or not f1:
            continue
        path = [fpx[(d, e)] for d in days if d_in <= d <= d_out and (d, e) in fpx]
        jump = any(abs(math.log(b / a)) > 0.3 for a, b in zip(path[:-1], path[1:]) if a > 0 and b > 0)
        base = (f1 * (1 - FUT_SLIP) - f0 * (1 + FUT_SLIP)) / f0 - (FUT_STT_SELL * f1 + FUT_EXCH * (f0 + f1) + FUT_STAMP_BUY * f0) / f0
        row = {"d_in": d_in, "d_out": d_out, "expiry": e, "f0": f0, "f1": f1, "corp_action": jump, "B0": base}
        for name, (side, m) in VARIANTS.items():
            if side is None:
                continue
            ks = strikes.get((d_in, e, side))
            if not ks:
                row[name], row[name + "_traded"] = np.nan, False
                continue
            k = min(ks, key=lambda x: abs(x - f0 * (1 + m)))
            p0, v0 = opx[(d_in, e, side, k)]
            rec = opx.get((d_out, e, side, k))
            intrinsic = max(f1 - k, 0.0) if side == "CE" else max(k - f1, 0.0)
            p1 = max(rec[0] if rec else intrinsic, intrinsic)  # stale-close guard: never below intrinsic
            if side == "PE":  # buy put, sell it later
                buy, sell = p0 + _opt_slip(p0), max(p1 - _opt_slip(p1), 0.0)
                ch = round_trip_costs(lot, buy, sell, costs) / lot
                row[name] = base + (sell - buy - ch) / f0
            else:  # sell call, buy it back later
                sell, buy = max(p0 - _opt_slip(p0), 0.0), p1 + _opt_slip(p1)
                ch = round_trip_costs(lot, buy, sell, costs) / lot
                row[name] = base + (sell - buy - ch) / f0
            row[name + "_traded"] = bool(v0 and v0 > 0)
            row[name + "_k"] = k
        rows.append(row)
    return pd.DataFrame(rows)


def perf(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 3:
        return {"n": len(r)}
    eq = (1 + r).cumprod()
    return {"n": len(r), "ann_ret": float(eq.iat[-1] ** (12 / len(r)) - 1), "ann_vol": float(r.std(ddof=1) * math.sqrt(12)),
            "sharpe": float(r.mean() / r.std(ddof=1) * math.sqrt(12)) if r.std(ddof=1) > 0 else float("nan"),
            "max_dd": float((1 - eq / eq.cummax()).max()), "worst": float(r.min())}
