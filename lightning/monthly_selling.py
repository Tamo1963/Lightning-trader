"""Monthly hedged option selling with a profit target in % of capital employed (daily closes, NSE bhavcopy).
Rules: docs/results/2026-10-28-monthly-selling-preregistration.md"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .calendar import lot_size_on
from .costs import round_trip_costs

STRUCTS = {"fly": (0, 300), "condor_n": (100, 400), "condor_w": (200, 500)}  # (short distance, wing distance) in points


@dataclass(frozen=True)
class MonthlyVariant:
    structure: str
    entry: str            # "early" | "mid"
    stop: str             # "none" | "stop10"
    target_pct: float = 5.0
    stop_pct: float = 10.0
    capital_employed_pct: float = 20.0
    slip_pct: float = 0.01
    min_slip: float = 0.5


class Chain:
    """Close and volume by (date, expiry, opt, strike)."""

    def __init__(self, df: pd.DataFrame):
        self.px = {(d, e, o, float(k)): (c, v) for d, e, o, k, c, v in
                   zip(df["date"], df["expiry"], df["opt"], df["strike"], df["close"], df["volume"])}
        self.strikes = {}
        for d, e, o, k in zip(df["date"], df["expiry"], df["opt"], df["strike"]):
            self.strikes.setdefault((d, e, o), set()).add(float(k))
        self.days = sorted(set(df["date"]))
        mon = set()
        for d, g in df.groupby("date"):
            mon |= set(g["expiry"])
        self.expiries = sorted(mon)

    def wing(self, d, e, opt, k_target, outward: int):
        ks = sorted(self.strikes.get((d, e, opt), ()))
        cand = [k for k in ks if (k >= k_target if outward > 0 else k <= k_target)]
        if not cand:
            return None
        return min(cand) if outward > 0 else max(cand)


def _slip(px, v: MonthlyVariant):
    return max(v.slip_pct * px, v.min_slip)


def cycles(chain: Chain, entry: str):
    """(entry_day, last_day, expiry) per monthly expiry, using only listed trading days."""
    out, days = [], chain.days
    for prev, e in zip(chain.expiries[:-1], chain.expiries[1:]):
        window = [d for d in days if prev < d < e]
        if len(window) < 3:
            continue
        if entry == "early":
            d0 = window[0]
        else:
            mids = [d for d in window if (e - d).days <= 14]
            if not mids:
                continue
            d0 = mids[0]
        last = window[-1]
        if d0 < last:
            out.append((d0, last, e))
    return out


def simulate(chain: Chain, spot_close: pd.Series, v: MonthlyVariant, p, equity0: float):
    """Returns (trades DataFrame, log list)."""
    so, w = STRUCTS[v.structure]
    equity, trades, log = equity0, [], []
    for d0, last, e in cycles(chain, v.entry):
        s0 = spot_close.get(pd.Timestamp(d0))
        if s0 is None or not np.isfinite(s0):
            log.append((d0, "NO_SPOT")); continue
        k0 = round(s0 / 50) * 50
        kc, kp = k0 + so, k0 - so
        if kc not in chain.strikes.get((d0, e, "CE"), ()) or kp not in chain.strikes.get((d0, e, "PE"), ()):
            log.append((d0, "SHORT_STRIKE_MISSING")); continue
        wc, wp = chain.wing(d0, e, "CE", k0 + w, +1), chain.wing(d0, e, "PE", k0 - w, -1)
        if wc is None or wp is None:
            log.append((d0, "WING_MISSING")); continue
        legs = [("CE", kc, +1), ("PE", kp, +1), ("CE", wc, -1), ("PE", wp, -1)]  # +1 short, -1 long
        width = max(wc - kc, kp - wp)
        px0 = [chain.px[(d0, e, o, k)][0] for o, k, _ in legs]
        fills = [px - _slip(px, v) if sg > 0 else px + _slip(px, v) for (_, _, sg), px in zip(legs, px0)]
        fills = [max(f, 0.05) for f in fills]
        credit = sum(sg * f for (_, _, sg), f in zip(legs, fills))
        r_u = width - credit
        if credit <= 0 or r_u <= 0:
            log.append((d0, "BAD_CREDIT")); continue
        lot = lot_size_on(p.lot_schedule, d0)
        lots = math.floor(equity * v.capital_employed_pct / 100 / (r_u * lot))
        if lots < 1:
            log.append((d0, "LOTS_LT_1")); continue
        qty = lots * lot
        ce = r_u * qty
        last_px, zero_vol, leg_days = list(px0), 0, 0
        days = [d for d in chain.days if d0 < d <= last]
        exit_day, reason, exit_px = last, "TIME", None
        for d in days:
            cur = []
            for i, (o, k, _) in enumerate(legs):
                rec = chain.px.get((d, e, o, k))
                if rec is not None:
                    last_px[i] = rec[0]
                    zero_vol += int(rec[1] == 0)
                leg_days += 1
                cur.append(last_px[i])
            outs = [c + _slip(c, v) if sg > 0 else max(c - _slip(c, v), 0.0) for (_, _, sg), c in zip(legs, cur)]
            debit = sum(sg * x for (_, _, sg), x in zip(legs, outs))
            costs = sum(round_trip_costs(qty, x_out, x_in, p.costs) if sg > 0 else round_trip_costs(qty, x_in, x_out, p.costs)
                        for (_, _, sg), x_in, x_out in zip(legs, fills, outs))
            pnl = (credit - debit) * qty - costs
            if pnl >= v.target_pct / 100 * ce:
                exit_day, reason, exit_px = d, "TARGET", (outs, costs, pnl); break
            if v.stop == "stop10" and pnl <= -v.stop_pct / 100 * ce:
                exit_day, reason, exit_px = d, "STOP", (outs, costs, pnl); break
            exit_px = (outs, costs, pnl)
        if exit_px is None:
            log.append((d0, "NO_DAYS")); continue
        outs, costs, net = exit_px
        equity += net
        trades.append({"entry_day": d0, "exit_day": exit_day, "expiry": e, "structure": v.structure, "k0": k0,
                       "legs": [(o, k) for o, k, _ in legs], "credit": round(credit, 2), "width": width, "risk_u": round(r_u, 2),
                       "lots": lots, "qty": qty, "capital_employed": ce, "exit_reason": reason, "costs": costs, "net": net,
                       "r": net / ce, "days_held": len([d for d in days if d <= exit_day]),
                       "zero_vol_share": zero_vol / max(leg_days, 1), "equity_after": equity})
        log.append((d0, "TRADED"))
    return pd.DataFrame(trades), log
