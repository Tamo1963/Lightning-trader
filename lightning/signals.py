"""G1 (basic tradability) + G2 (baseline candidate rules). Decisions are made at bar CLOSE."""
from __future__ import annotations

import pandas as pd

from .config import Params

BAR = pd.Timedelta(minutes=15)


def generate(f: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Edge-triggered candidates: first bar on which the full rule set becomes true. side: +1 call, -1 put."""
    decision_time = (f.index + BAR).time
    in_window = pd.Series([(p.entry_start <= t <= p.entry_end) for t in decision_time], index=f.index)
    ok = in_window & ~f["post_roll"].astype(bool) & (f["adx"].fillna(0) >= p.adx_min)
    valid = f[["monthly_rsi", "weekly_rsi_chg", "vwap", "vwma"]].notna().all(axis=1) & (f["st_dir"] != 0)
    c = f["close"]
    call = (valid & ok & (f["monthly_rsi"] > p.monthly_rsi_threshold) & (f["weekly_rsi_chg"] > 0)
            & (c > f["vwap"]) & (c > f["vwma"]) & (f["st_dir"] == 1))
    put = (valid & ok & (f["monthly_rsi"] < p.monthly_rsi_threshold) & (f["weekly_rsi_chg"] < 0)
           & (c < f["vwap"]) & (c < f["vwma"]) & (f["st_dir"] == -1))
    call_edge = call & ~call.shift(1, fill_value=False)
    put_edge = put & ~put.shift(1, fill_value=False)
    side = pd.Series(0, index=f.index)
    side[call_edge] = 1
    side[put_edge] = -1
    out = pd.DataFrame({"side": side[side != 0]})
    out["decision_time"] = out.index + BAR
    return out
