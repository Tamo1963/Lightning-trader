"""G1 (basic tradability) + G2 (baseline candidate rules). Decisions are made at bar CLOSE."""
from __future__ import annotations

import pandas as pd

from .config import Params

BAR = pd.Timedelta(minutes=15)


def generate(f: pd.DataFrame, p: Params) -> pd.DataFrame:
    """Candidates. side: +1 call, -1 put.

    entry_mode "edge": first bar on which the full rule set becomes true (baseline).
    entry_mode "pullback": trend state holds and the bar dips to session VWAP and closes back on the trend side.
    htf_filter "full": monthly RSI vs threshold and weekly RSI change; "no_monthly": weekly change only; "none".
    """
    decision_time = (f.index + BAR).time
    in_window = pd.Series([(p.entry_start <= t <= p.entry_end) for t in decision_time], index=f.index)
    ok = in_window & ~f["post_roll"].astype(bool) & (f["adx"].fillna(0) >= p.adx_min)
    need = ["vwap", "vwma"] + {"full": ["monthly_rsi", "weekly_rsi_chg"], "no_monthly": ["weekly_rsi_chg"], "none": []}[p.htf_filter]
    valid = f[need].notna().all(axis=1) & (f["st_dir"] != 0)
    c, true = f["close"], pd.Series(True, index=f.index)
    m_up = f["monthly_rsi"] > p.monthly_rsi_threshold if p.htf_filter == "full" else true
    m_dn = f["monthly_rsi"] < p.monthly_rsi_threshold if p.htf_filter == "full" else true
    w_up = f["weekly_rsi_chg"] > 0 if p.htf_filter in ("full", "no_monthly") else true
    w_dn = f["weekly_rsi_chg"] < 0 if p.htf_filter in ("full", "no_monthly") else true
    trend_up = valid & ok & m_up & w_up & (c > f["vwma"]) & (f["st_dir"] == 1)
    trend_dn = valid & ok & m_dn & w_dn & (c < f["vwma"]) & (f["st_dir"] == -1)
    if p.entry_mode == "edge":
        call, put = trend_up & (c > f["vwap"]), trend_dn & (c < f["vwap"])
    elif p.entry_mode == "pullback":
        call = trend_up & (f["low"] <= f["vwap"]) & (c > f["vwap"])
        put = trend_dn & (f["high"] >= f["vwap"]) & (c < f["vwap"])
    else:
        raise ValueError(f"unknown entry_mode {p.entry_mode}")
    call_edge = call & ~call.shift(1, fill_value=False)
    put_edge = put & ~put.shift(1, fill_value=False)
    side = pd.Series(0, index=f.index)
    side[call_edge] = 1
    side[put_edge] = -1
    out = pd.DataFrame({"side": side[side != 0]})
    out["decision_time"] = out.index + BAR
    return out
