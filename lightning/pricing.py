"""Option premium sources for the backtest.

RealPricer: Dhan rolling expired-options data (ATM-relative strikes, 15-min OHLC). A held contract has a FIXED
strike, so each bar looks the strike up across the fetched offsets (ATM-k .. ATM+k).
ModelPricer: Black-76 with constant IV. LOW FIDELITY; fallback and tests only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from .options import atm_strike, bs_price, years_to
from .signals import BAR

SIDE = {1: "CE", -1: "PE"}


@dataclass(frozen=True)
class Contract:
    side: int
    strike: float
    expiry: date
    slot: int  # 0 = near expiry, 1 = next expiry


class ModelPricer:
    name = "model"

    def __init__(self, f: pd.DataFrame, strike_step: int, iv: float):
        self.f, self.step, self.iv = f, strike_step, iv

    def select(self, i: int, side: int, slot: int, expiry: date):
        return Contract(side, atm_strike(self.f["close"].iat[i], self.step), expiry, slot)

    def bar(self, c: Contract, j: int):
        f, ts = self.f, self.f.index[j]
        end, call = ts + BAR, c.side == 1
        pr = lambda F, t: bs_price(F, c.strike, years_to(c.expiry, t), self.iv, call)
        hi, lo = f["high"].iat[j], f["low"].iat[j]
        ph, pl = (pr(hi, end), pr(lo, end)) if call else (pr(lo, end), pr(hi, end))
        return pr(f["open"].iat[j], ts), ph, pl, pr(f["close"].iat[j], end)


class RealPricer:
    """opt: long table with columns ts, slot, side ('CE'/'PE'), offset, open, high, low, close, strike, ..."""
    name = "real"

    def __init__(self, f: pd.DataFrame, opt: pd.DataFrame):
        self.f = f
        o = opt.dropna(subset=["strike", "open", "close"])
        self._bars = {
            (s, sd, t, float(k)): (op, hi, lo, cl)
            for s, sd, t, k, op, hi, lo, cl in zip(o["slot"], o["side"], o["ts"], o["strike"],
                                                    o["open"], o["high"], o["low"], o["close"])
        }
        atm = o[o["offset"] == 0]
        self._atm = {(s, sd, t): float(k) for s, sd, t, k in zip(atm["slot"], atm["side"], atm["ts"], atm["strike"])}

    def select(self, i: int, side: int, slot: int, expiry: date):
        k = self._atm.get((slot, SIDE[side], self.f.index[i]))
        return None if k is None else Contract(side, k, expiry, slot)

    def bar(self, c: Contract, j: int):
        return self._bars.get((c.slot, SIDE[c.side], self.f.index[j], c.strike))
