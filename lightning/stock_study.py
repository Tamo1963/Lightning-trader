"""Stock options study, stage 1 (docs/results/2026-10-27-stocks-preregistration.md).
Stock prices are real (Dhan); option P&L is MODELLED (Black-76, IV = 1.1 x 20-day realized vol). Stage-1 screen only."""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .calendar import _in_effect
from .costs import round_trip_costs
from .features import htf_rsi_asof
from .indicators import supertrend, vwma
from .options import bs_price, years_to

IV_MULT = 1.1
SLIP = 0.01


def monthly_expiries(trading_days, schedule) -> list[date]:
    """Last expiry-weekday of each month, moved to the previous trading day on a holiday."""
    days = sorted(set(trading_days))
    tset = set(days)
    out = []
    y, m = days[0].year, days[0].month
    end = days[-1] + timedelta(days=62)
    while date(y, m, 1) <= end:
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        last = nxt - timedelta(days=1)
        wd = _in_effect(schedule, max(date(y, m, 1), schedule[0]["from"]), "weekday")
        e = last - timedelta(days=(last.weekday() - wd) % 7)
        if e <= days[-1]:
            while e not in tset and e.month == m:
                e -= timedelta(days=1)
        out.append(e)
        y, m = nxt.year, nxt.month
    return out


def pick_monthly(expiries: list[date], d: date, min_days: int) -> date:
    for e in expiries:
        if (e - d).days >= min_days:
            return e
    raise ValueError("no expiry far enough")


def realized_vol(daily_close: pd.Series, n: int = 20) -> pd.Series:
    """Annualized n-day realized vol known at the START of each day (uses closes up to the previous day)."""
    r = np.log(daily_close).diff()
    return (r.rolling(n).std() * math.sqrt(252)).shift(1)


def model_option_r(s_in: float, s_out: float, side: int, t_in: pd.Timestamp, t_out: pd.Timestamp, expiry: date,
                   iv: float, step: float, lot: int, costs: dict) -> dict:
    """Buy ATM option at t_in, sell at t_out. Returns R = net / premium paid, plus components."""
    k = round(s_in / step) * step
    call = side == 1
    p0 = bs_price(s_in, k, years_to(expiry, t_in), iv, call)
    p1 = bs_price(s_out, k, years_to(expiry, t_out), iv, call)
    buy = p0 + max(SLIP * p0, 0.05)
    sell = max(p1 - max(SLIP * p1, 0.05), 0.0)
    cu = round_trip_costs(lot, buy, sell, costs) / lot
    return {"strike": k, "premium": buy, "exit_px": sell, "r": (sell - buy - cu) / buy,
            "move": (s_out / s_in - 1) * side}


def daily_signals(d: pd.DataFrame, rsi_n: int = 14) -> pd.Series:
    """S2: +1/-1 on the first day the daily rule set becomes true (decided at that day's close)."""
    idx = pd.DatetimeIndex(d.index).tz_localize("Asia/Kolkata")
    m = pd.Series(htf_rsi_asof(d["close"], idx, "M", rsi_n), index=d.index)
    w = pd.Series(htf_rsi_asof(d["close"], idx, "W-FRI", rsi_n, change=True), index=d.index)
    vw = vwma(d["close"], d["volume"], 20)
    _, st = supertrend(d["high"], d["low"], d["close"], 10, 3.0)
    up = (m > 50) & (w > 0) & (d["close"] > vw) & (st == 1)
    dn = (m < 50) & (w < 0) & (d["close"] < vw) & (st == -1)
    up_e, dn_e = up & ~up.shift(1, fill_value=False), dn & ~dn.shift(1, fill_value=False)
    s = pd.Series(0, index=d.index)
    s[up_e], s[dn_e] = 1, -1
    return s


def cluster_t(values: pd.Series, clusters: pd.Series) -> float:
    g = values.groupby(clusters).mean()
    return float(g.mean() / g.std(ddof=1) * math.sqrt(len(g))) if len(g) > 2 and g.std(ddof=1) > 0 else float("nan")
