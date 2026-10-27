"""Thin DhanHQ v2 historical-data client. Endpoints/fields per https://dhanhq.co/docs/v2/historical-data/
(intraday: intervals 1/5/15/25/60, max 90 days per request, ~5 years of history).
The access token is passed in by the caller and is never logged or stored."""
from __future__ import annotations

import time

import pandas as pd
import requests

BASE = "https://api.dhan.co/v2"
IST = "Asia/Kolkata"
MAX_DAYS = 85  # documented limit is 90 days per intraday request


def parse_candles(payload: dict) -> pd.DataFrame:
    if not payload or not payload.get("timestamp"):
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame({k: payload[k] for k in ("open", "high", "low", "close", "volume")})
    if payload.get("open_interest"):
        df["oi"] = payload["open_interest"]
    df.index = pd.to_datetime(payload["timestamp"], unit="s", utc=True).tz_convert(IST)
    df.index.name = "ts"
    return df


class DhanClient:
    def __init__(self, access_token: str, session: requests.Session | None = None, pause_s: float = 0.3):
        self._headers = {"access-token": access_token, "Content-Type": "application/json", "Accept": "application/json"}
        self._s = session or requests.Session()
        self._pause = pause_s

    def _post(self, path: str, body: dict) -> dict:
        r = self._s.post(f"{BASE}{path}", json=body, headers=self._headers, timeout=30)
        r.raise_for_status()
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
