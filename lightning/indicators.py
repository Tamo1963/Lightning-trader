"""Causal indicators: the value at row i uses only rows <= i."""
from __future__ import annotations

import numpy as np
import pandas as pd


def wilder(x: pd.Series, n: int) -> pd.Series:
    """Wilder smoothing: first value is the simple mean of the first n valid observations, then
    y_t = y_{t-1} + (x_t - y_{t-1}) / n. NaN until n observations exist."""
    v = x.to_numpy(dtype=float)
    out = np.full(len(v), np.nan)
    valid = np.flatnonzero(~np.isnan(v))
    if len(valid) < n:
        return pd.Series(out, index=x.index)
    k = valid[n - 1]
    out[k] = v[valid[:n]].mean()
    for i in range(k + 1, len(v)):
        out[i] = out[i - 1] + (v[i] - out[i - 1]) / n if not np.isnan(v[i]) else out[i - 1]
    return pd.Series(out, index=x.index)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI (SMA-seeded smoothing, as in the original definition)."""
    d = close.diff()
    au = wilder(d.clip(lower=0).where(d.notna()), n)
    ad = wilder((-d.clip(upper=0)).where(d.notna()), n)
    out = 100 - 100 / (1 + au / ad)
    out = out.where(ad != 0, np.where(au == 0, 50.0, 100.0))
    return out.where(au.notna() & ad.notna())


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    pc = close.shift(1)
    return pd.concat([high - low, (high - pc).abs(), (low - pc).abs()], axis=1).max(axis=1)


def atr(high, low, close, n: int = 14) -> pd.Series:
    return wilder(true_range(high, low, close), n)


def adx(high, low, close, n: int = 14) -> pd.Series:
    up, dn = high.diff(), -low.diff()
    plus = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=high.index)
    minus = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=high.index)
    a = atr(high, low, close, n)
    pdi = 100 * wilder(plus, n) / a
    mdi = 100 * wilder(minus, n) / a
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return wilder(dx, n)


def supertrend(high, low, close, period: int = 10, mult: float = 3.0):
    """Returns (line, direction); direction is +1 when close is above the line, else -1."""
    a = atr(high, low, close, period).to_numpy()
    hl2 = ((high + low) / 2).to_numpy()
    ub, lb, c = hl2 + mult * a, hl2 - mult * a, close.to_numpy()
    n = len(c)
    fub, flb = ub.copy(), lb.copy()
    line, dirn = np.full(n, np.nan), np.zeros(n, dtype=int)
    valid = np.flatnonzero(~np.isnan(a))
    if len(valid) == 0:
        return pd.Series(line, index=close.index), pd.Series(dirn, index=close.index)
    k = valid[0]
    dirn[k] = 1 if c[k] > hl2[k] else -1
    line[k] = flb[k] if dirn[k] == 1 else fub[k]
    for i in range(k + 1, n):
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1]) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1]) else flb[i - 1]
        if dirn[i - 1] == -1 and c[i] > fub[i]:
            dirn[i] = 1
        elif dirn[i - 1] == 1 and c[i] < flb[i]:
            dirn[i] = -1
        else:
            dirn[i] = dirn[i - 1]
        line[i] = flb[i] if dirn[i] == 1 else fub[i]
    return pd.Series(line, index=close.index), pd.Series(dirn, index=close.index)


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """Cumulative VWAP reset each calendar session. Needs traded volume (use futures, not the spot index)."""
    day = df.index.normalize()
    tp = (df["high"] + df["low"] + df["close"]) / 3
    pv = (tp * df["volume"]).groupby(day).cumsum()
    v = df["volume"].groupby(day).cumsum()
    return pv / v.replace(0, np.nan)


def vwma(close: pd.Series, volume: pd.Series, n: int = 20) -> pd.Series:
    return (close * volume).rolling(n).sum() / volume.rolling(n).sum().replace(0, np.nan)
