"""Volatility-expansion family: opening-range breakout with pre-open day filters.
See docs/results/2026-10-27-volexp-preregistration.md. All day filters use only data known before the open."""
from __future__ import annotations

from datetime import time

import numpy as np
import pandas as pd

from .signals import BAR

LAST_DECISION = time(13, 0)


def day_filters(f: pd.DataFrame, daily: pd.DataFrame, opt: pd.DataFrame | None) -> pd.DataFrame:
    """Per session date: `compression`, `low_iv` and `iv_high` flags, computed from PRIOR sessions only."""
    days = pd.DatetimeIndex(sorted(set(f.index.tz_localize(None).normalize())))
    d = daily.reindex(days)  # regular sessions only (drops Muhurat/special rows from the daily series)
    rng = d["high"] - d["low"]
    out = pd.DataFrame(index=days)
    out["compression"] = rng.shift(1) < 0.75 * rng.shift(2).rolling(20).median()
    out["low_iv"] = False
    out["iv_high"] = False
    if opt is not None and not opt.empty:
        a = opt[(opt["slot"] == 0) & (opt["offset"] == 0) & (opt["iv"] > 0)].sort_values("ts")
        last = a.groupby([a["ts"].dt.tz_localize(None).dt.normalize(), "side"])["iv"].last().unstack()
        iv = last.mean(axis=1).reindex(days)
        q = iv.rolling(60, min_periods=60).quantile(0.33)
        out["low_iv"] = iv.shift(1) < q.shift(1)
        q_hi = iv.rolling(60, min_periods=60).quantile(0.67)
        out["iv_high"] = iv.shift(1) > q_hi.shift(1)
    return out.fillna(False).astype(bool)


def generate_orb(f: pd.DataFrame, k_bars: int, day_ok: pd.Series | None = None) -> pd.DataFrame:
    """First close outside the opening range of the first `k_bars` bars; one candidate per day.
    day_ok: boolean Series indexed by tz-naive session date (None = all days)."""
    sides, stamps = [], []
    for day, g in f.groupby(f.index.tz_localize(None).normalize()):
        if day_ok is not None and not bool(day_ok.get(day, False)):
            continue
        if len(g) <= k_bars or g.index[0].strftime("%H:%M") != "09:15":
            continue
        hi, lo = g["high"].iloc[:k_bars].max(), g["low"].iloc[:k_bars].min()
        for ts, c in zip(g.index[k_bars:], g["close"].iloc[k_bars:]):
            if (ts + BAR).time() > LAST_DECISION:
                break
            if c > hi or c < lo:
                sides.append(1 if c > hi else -1)
                stamps.append(ts)
                break
    out = pd.DataFrame({"side": np.array(sides, dtype=int)}, index=pd.DatetimeIndex(stamps, tz=f.index.tz))
    out["decision_time"] = out.index + BAR
    return out
