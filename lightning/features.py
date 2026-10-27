"""Feature frame for the baseline. Higher-timeframe RSI uses only COMPLETED periods (no look-ahead)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Params
from .indicators import adx, atr, rsi, session_vwap, supertrend, vwma


def htf_rsi_asof(daily_close: pd.Series, intraday_index: pd.DatetimeIndex, freq: str,
                 n: int = 14, change: bool = False) -> np.ndarray:
    """RSI (or its change) of the last COMPLETED period as of each intraday timestamp.

    freq: pandas period alias, e.g. "M" (calendar month) or "W-FRI" (week ending Friday).
    A period's value becomes visible on the calendar day after the period ends.
    """
    dc = daily_close.copy()
    dc.index = pd.DatetimeIndex(dc.index).tz_localize(None) if dc.index.tz is not None else pd.DatetimeIndex(dc.index)
    last = dc.groupby(dc.index.to_period(freq)).last()
    r = rsi(last, n)
    if change:
        r = r.diff()
    avail = last.index.end_time.normalize() + pd.Timedelta(days=1)
    s = pd.Series(r.to_numpy(), index=avail)
    days = pd.DatetimeIndex(intraday_index).tz_localize(None).normalize()
    uniq = days.unique()
    per_day = s.reindex(s.index.union(uniq)).ffill().reindex(uniq)
    return per_day.to_numpy()[uniq.get_indexer(days)]


def build_features(fut15: pd.DataFrame, daily_spot: pd.DataFrame, p: Params) -> pd.DataFrame:
    """fut15: 15-min OHLCV (bar-start timestamps, IST). daily_spot: daily OHLC of the spot index."""
    f = fut15.copy()
    f["vwap"] = session_vwap(f)
    f["vwma"] = vwma(f["close"], f["volume"], p.vwma_period)
    _, f["st_dir"] = supertrend(f["high"], f["low"], f["close"], p.supertrend_period, p.supertrend_mult)
    f["atr"] = atr(f["high"], f["low"], f["close"], p.atr_period)
    f["adx"] = adx(f["high"], f["low"], f["close"], p.adx_period)
    dc = daily_spot["close"]
    f["monthly_rsi"] = htf_rsi_asof(dc, f.index, "M", p.rsi_period)
    f["weekly_rsi_chg"] = htf_rsi_asof(dc, f.index, "W-FRI", p.rsi_period, change=True)
    if "post_roll" not in f:
        f["post_roll"] = False
    return f
