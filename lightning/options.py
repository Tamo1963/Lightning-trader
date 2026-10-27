"""Modelled option premiums (Black-76 with r=0 on the futures price). LOW FIDELITY: constant IV, no skew,
no spread. Replace with real historical premiums when available (Phase 0 / expired-options data)."""
from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta

import pandas as pd

IST = "Asia/Kolkata"


def _ncdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def bs_price(F: float, K: float, T: float, iv: float, is_call: bool) -> float:
    if T <= 0 or iv <= 0:
        return max(F - K, 0.0) if is_call else max(K - F, 0.0)
    sd = iv * math.sqrt(T)
    d1 = (math.log(F / K) + 0.5 * sd * sd) / sd
    d2 = d1 - sd
    return F * _ncdf(d1) - K * _ncdf(d2) if is_call else K * _ncdf(-d2) - F * _ncdf(-d1)


def pick_expiry(day: date, weekday: int, min_dte_days: int) -> date:
    """First weekly expiry on `weekday` at least `min_dte_days` calendar days away (holidays ignored [VERIFY])."""
    d = day + timedelta(days=min_dte_days)
    return d + timedelta(days=(weekday - d.weekday()) % 7)


def is_expiry_day(day: date, weekday: int) -> bool:
    return day.weekday() == weekday


def expiry_dt(expiry: date) -> pd.Timestamp:
    return pd.Timestamp(datetime.combine(expiry, time(15, 30))).tz_localize(IST)


def years_to(expiry: date, ts: pd.Timestamp) -> float:
    return max((expiry_dt(expiry) - ts).total_seconds(), 0.0) / (365 * 86400)


def atm_strike(price: float, step: int) -> float:
    return round(price / step) * step
