"""Shared helpers for pre-registered grid runs."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .metrics import summarize

IST = "Asia/Kolkata"


def window(df: pd.DataFrame, sp: dict, col: str = "entry_ts") -> pd.DataFrame:
    lo = pd.Timestamp(sp["from"]).tz_localize(IST)
    hi = pd.Timestamp(sp["to"]).tz_localize(IST) + pd.Timedelta(days=1)
    return df[(df[col] >= lo) & (df[col] < hi)] if not df.empty else df


def row(name: str, t: pd.DataFrame, capital: float) -> dict:
    s = summarize(t, capital)
    if s["n_trades"] == 0:
        return {"variant": name, "n": 0, "exp_r": float("-inf")}
    calls = int((t["side"] == 1).sum())
    return {"variant": name, "n": s["n_trades"], "calls": calls, "puts": s["n_trades"] - calls,
            "win": round(s["win_rate"], 3), "exp_r": round(s["expectancy_r"], 4),
            "ci90_lo": round(s["expectancy_r_ci90"][0], 4), "ci90_hi": round(s["expectancy_r_ci90"][1], 4),
            "pf": round(s["profit_factor"], 3), "pnl": round(s["total_pnl_inr"]),
            "max_dd_pct": round(s["max_drawdown_pct"], 1),
            "time_exits": round(s["exit_reasons"].get("TIME", 0) / s["n_trades"], 2)}


def direction_atr(f: pd.DataFrame, cands: pd.DataFrame, horizon_bars: int) -> pd.Series:
    """Index move in the trade direction, next-bar open to horizon close (capped at session end), in ATR units."""
    pos = {t: i for i, t in enumerate(f.index)}
    day = f.index.date
    vals, idx = [], []
    for ts, side in zip(cands.index, cands["side"]):
        i = pos[ts]
        if i + 1 >= len(f) or day[i + 1] != day[i]:
            continue
        j = min(i + horizon_bars, len(f) - 1)
        while day[j] != day[i]:
            j -= 1
        vals.append((f["close"].iat[j] - f["open"].iat[i + 1]) * side / f["atr"].iat[i])
        idx.append(ts)
    return pd.Series(vals, index=pd.DatetimeIndex(idx), dtype=float)
