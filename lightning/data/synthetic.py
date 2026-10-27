"""SYNTHETIC data for tests and plumbing demos ONLY. Results on it say nothing about real markets."""
from __future__ import annotations

import numpy as np
import pandas as pd

IST = "Asia/Kolkata"


def generate(years: float = 3.0, seed: int = 7, start: str = "2022-01-03", s0: float = 18000.0):
    rng = np.random.default_rng(seed)
    days = pd.bdate_range(start, periods=int(252 * years))
    n_bars = 25
    offs = pd.to_timedelta(9 * 60 + 15 + 15 * np.arange(n_bars), unit="m")
    ts = (days.values[:, None] + offs.values[None, :]).ravel()
    idx = pd.DatetimeIndex(ts).tz_localize(IST)
    mu_d = np.zeros(len(days))
    for k in range(1, len(days)):  # persistent daily drift regime
        mu_d[k] = 0.85 * mu_d[k - 1] + rng.normal(0, 0.0012)
    drift = np.repeat(mu_d / n_bars, n_bars)
    r = drift + rng.normal(0, 0.0009, len(idx))
    close = s0 * np.exp(np.cumsum(r))
    open_ = np.concatenate([[s0], close[:-1]])
    noise = np.abs(rng.normal(0, 0.0003, (2, len(idx))))
    high = np.maximum(open_, close) * (1 + noise[0])
    low = np.minimum(open_, close) * (1 - noise[1])
    shape = 1.5 - np.abs(np.linspace(-1, 1, n_bars))  # busier at open/close
    vol = (np.tile(shape, len(days)) * rng.lognormal(10, 0.4, len(idx))).astype(int)
    fut = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)
    fut.index.name = "ts"
    g = fut.groupby(fut.index.tz_localize(None).normalize())
    daily = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                          "close": g["close"].last(), "volume": g["volume"].sum()})
    daily.index.name = "ts"
    return fut, daily
