"""Market data sources for the shadow engine. Live = DhanHQ REST; Replay = stored history with a simulated clock.

Chain format (both sources): {"spot": float, "rows": {(side, strike): {"bid","ask","ltp","iv","oi","volume"}}}
where `volume` is the CUMULATIVE day volume (as Dhan reports it)."""
from __future__ import annotations

import time
from datetime import date

import pandas as pd

from ..data.dhan import DhanClient
from ..signals import BAR

IST = "Asia/Kolkata"


def regular_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Keep weekday bars starting 09:15..15:15 (Dhan also returns post-close placeholder bars, e.g. 18:15)."""
    hm = df.index.strftime("%H:%M")
    return df[(hm >= "09:15") & (hm <= "15:15") & (df.index.weekday < 5)]


def parse_chain(data: dict) -> dict:
    rows = {}
    for k, v in (data.get("oc") or {}).items():
        strike = float(k)
        for side, key in (("CE", "ce"), ("PE", "pe")):
            o = v.get(key)
            if not o:
                continue
            rows[(side, strike)] = {"bid": o.get("top_bid_price"), "ask": o.get("top_ask_price"), "ltp": o.get("last_price"),
                                    "iv": o.get("implied_volatility"), "oi": o.get("oi"), "volume": o.get("volume")}
    return {"spot": data.get("last_price"), "rows": rows}


class DhanLiveSource:
    def __init__(self, client: DhanClient, security_id: int, segment: str = "IDX_I"):
        self.c, self.sid, self.seg = client, security_id, segment
        self._last_chain_call = 0.0

    def now(self) -> pd.Timestamp:
        return pd.Timestamp.now(tz=IST)

    def daily(self, start: str = "2015-01-01") -> pd.DataFrame:
        d = self.c.daily(str(self.sid), self.seg, "INDEX", start, (self.now() + pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
        d.index = d.index.tz_localize(None).normalize()
        return d

    def bars(self, sessions_back: int = 10) -> pd.DataFrame:
        """Completed 15-min bars from ~sessions_back trading days ago up to now."""
        now = self.now()
        start = (now - pd.Timedelta(days=int(sessions_back * 1.6) + 4)).strftime("%Y-%m-%d 09:00:00")
        df = self.c.intraday(str(self.sid), self.seg, "INDEX", start, now.strftime("%Y-%m-%d %H:%M:%S"), 15)
        return regular_bars(df[df.index + BAR <= now - pd.Timedelta(seconds=5)])

    def expiries(self) -> list[date]:
        return [pd.Timestamp(x).date() for x in self.c.expiry_list(self.sid, self.seg)]

    def chain(self, expiry: date) -> dict:
        wait = 3.1 - (time.monotonic() - self._last_chain_call)
        if wait > 0:
            time.sleep(wait)
        self._last_chain_call = time.monotonic()
        return parse_chain(self.c.option_chain(self.sid, expiry.isoformat(), self.seg))


class ReplaySource:
    """Replays stored spot bars and near-expiry option bars. Quotes are synthesized from bar closes as
    bid/ask = close -/+ half_spread (fraction of price, min 0.05). The clock is set by the caller."""

    def __init__(self, spot15: pd.DataFrame, daily: pd.DataFrame, opt: pd.DataFrame, expiries: list[date],
                 half_spread: float = 0.005):
        self.spot, self.dly, self.exp = spot15, daily, sorted(expiries)
        o = opt[opt["slot"] == 0].copy()
        o["day"] = o["ts"].dt.date
        o = o.sort_values("ts")
        o["cumvol"] = o.groupby(["day", "side", "strike"])["volume"].cumsum()
        self._by_ts = {t: g for t, g in o.groupby("ts")}
        self.hs = half_spread
        self.clock = spot15.index[0]

    def now(self) -> pd.Timestamp:
        return self.clock

    def daily(self, start: str = "2015-01-01") -> pd.DataFrame:
        return self.dly[self.dly.index < self.clock.tz_localize(None).normalize()]

    def bars(self, sessions_back: int = 10) -> pd.DataFrame:
        b = self.spot[self.spot.index + BAR <= self.clock]
        days = b.index.normalize().unique()[-(sessions_back + 1):]
        return b[b.index.normalize().isin(days)]

    def expiries(self) -> list[date]:
        return [e for e in self.exp if e >= self.clock.date()]

    def chain(self, expiry: date) -> dict:
        """Quotes as of the last completed bar's close (only the near expiry exists in the stored data)."""
        b = self.spot[self.spot.index + BAR <= self.clock]
        if b.empty:
            return {"spot": None, "rows": {}}
        g = self._by_ts.get(b.index[-1])
        near = next((e for e in self.exp if e >= self.clock.date()), None)
        if g is None or expiry != near:
            return {"spot": float(b["close"].iat[-1]), "rows": {}}
        rows = {}
        for side, k, c, iv, oi, cv in zip(g["side"], g["strike"], g["close"], g["iv"], g["oi"], g["cumvol"]):
            h = max(self.hs * c, 0.05)
            rows[(side, float(k))] = {"bid": max(c - h, 0.05), "ask": c + h, "ltp": c, "iv": iv, "oi": oi, "volume": cv}
        return {"spot": float(b["close"].iat[-1]), "rows": rows}
