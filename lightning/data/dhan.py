"""Thin DhanHQ v2 historical-data client. Endpoints/fields per https://dhanhq.co/docs/v2/historical-data/ and
https://dhanhq.co/docs/v2/expired-options-data/ (intraday: max 90 days per request, ~5 years; rolling expired
options: max 30 days per request, ~5 years, ATM-relative strikes with OHLC, IV, OI, volume, spot).
The access token is passed in by the caller and is never logged or stored."""
from __future__ import annotations

import time

import pandas as pd
import requests

BASE = "https://api.dhan.co/v2"
IST = "Asia/Kolkata"
MAX_DAYS = 85  # documented limit is 90 days per intraday request
ROLL_DAYS = 30  # documented limit for /charts/rollingoption
ROLL_FIELDS = ["open", "high", "low", "close", "iv", "volume", "strike", "oi", "spot"]


def parse_candles(payload: dict) -> pd.DataFrame:
    if not payload or not payload.get("timestamp"):
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame({k: payload[k] for k in ("open", "high", "low", "close", "volume")})
    if payload.get("open_interest"):
        df["oi"] = payload["open_interest"]
    df.index = pd.to_datetime(payload["timestamp"], unit="s", utc=True).tz_convert(IST)
    df.index.name = "ts"
    return df


def parse_rolling(payload: dict, side: str) -> pd.DataFrame:
    """side: 'ce' or 'pe'. Returns a frame indexed by IST timestamp with ROLL_FIELDS columns."""
    d = ((payload or {}).get("data") or {}).get(side) or {}
    if not d.get("timestamp"):
        return pd.DataFrame(columns=ROLL_FIELDS)
    n = len(d["timestamp"])
    df = pd.DataFrame({k: (d.get(k) if d.get(k) and len(d.get(k)) == n else [None] * n) for k in ROLL_FIELDS})
    df.index = pd.to_datetime(d["timestamp"], unit="s", utc=True).tz_convert(IST)
    df.index.name = "ts"
    return df


class DhanClient:
    def __init__(self, access_token: str, session: requests.Session | None = None, pause_s: float = 0.3):
        self._headers = {"access-token": access_token, "Content-Type": "application/json", "Accept": "application/json"}
        self._s = session or requests.Session()
        self._pause = pause_s

    def _post(self, path: str, body: dict, retries: int = 4) -> dict:
        for attempt in range(retries + 1):
            r = self._s.post(f"{BASE}{path}", json=body, headers=self._headers, timeout=30)
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(2 ** (attempt + 1))  # 2, 4, 8, 16 s
                continue
            if r.status_code >= 400:  # surface Dhan's error body, never the request headers
                raise RuntimeError(f"Dhan {path} HTTP {r.status_code}: {r.text[:300]}")
            return r.json()

    def daily(self, security_id: str, segment: str, instrument: str, start: str, end: str,
              expiry_code: int = 0, oi: bool = False) -> pd.DataFrame:
        body = {"securityId": security_id, "exchangeSegment": segment, "instrument": instrument,
                "expiryCode": expiry_code, "oi": oi, "fromDate": start, "toDate": end}
        return parse_candles(self._post("/charts/historical", body))

    def intraday(self, security_id: str, segment: str, instrument: str, start: str, end: str,
                 interval: int = 15, oi: bool = False) -> pd.DataFrame:
        """Chunks the range into <=85-day windows and concatenates."""
        frames, cur, stop = [], pd.Timestamp(start), pd.Timestamp(end)
        while cur < stop:
            nxt = min(cur + pd.Timedelta(days=MAX_DAYS), stop)
            body = {"securityId": security_id, "exchangeSegment": segment, "instrument": instrument,
                    "interval": str(interval), "oi": oi,
                    "fromDate": cur.strftime("%Y-%m-%d %H:%M:%S"), "toDate": nxt.strftime("%Y-%m-%d %H:%M:%S")}
            frames.append(parse_candles(self._post("/charts/intraday", body)))
            cur = nxt
            time.sleep(self._pause)
        df = pd.concat(frames) if frames else pd.DataFrame()
        return df[~df.index.duplicated(keep="last")].sort_index()

    def rolling_options(self, underlying_id: int, start: str, end: str, side: str, strike: str,
                        expiry_code: int, expiry_flag: str = "WEEK", interval: int = 15,
                        instrument: str = "OPTIDX") -> pd.DataFrame:
        """side: 'CALL'/'PUT'; strike: 'ATM', 'ATM+1', 'ATM-2', ... Chunks into 30-day windows (end exclusive)."""
        frames, cur, stop = [], pd.Timestamp(start), pd.Timestamp(end)
        while cur < stop:
            nxt = min(cur + pd.Timedelta(days=ROLL_DAYS), stop)
            body = {"exchangeSegment": "NSE_FNO", "interval": str(interval), "securityId": int(underlying_id),
                    "instrument": instrument, "expiryFlag": expiry_flag, "expiryCode": int(expiry_code),
                    "strike": strike, "drvOptionType": side, "requiredData": ROLL_FIELDS,
                    "fromDate": cur.strftime("%Y-%m-%d"), "toDate": nxt.strftime("%Y-%m-%d")}
            frames.append(parse_rolling(self._post("/charts/rollingoption", body), "ce" if side == "CALL" else "pe"))
            cur = nxt
            time.sleep(self._pause)
        df = pd.concat([x for x in frames if not x.empty]) if any(not x.empty for x in frames) else pd.DataFrame(columns=ROLL_FIELDS)
        return df[~df.index.duplicated(keep="last")].sort_index()
