"""DhanClient against a fake HTTP session: chunking, request bodies, retry, and no token leakage in errors."""
import pandas as pd
import pytest

from lightning.data.dhan import DhanClient


class FakeResp:
    def __init__(self, code, body):
        self.status_code, self._b, self.text = code, body, str(body)

    def json(self):
        return self._b


class FakeSession:
    def __init__(self, codes=None):
        self.calls, self.codes = [], list(codes or [])

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json))
        code = self.codes.pop(0) if self.codes else 200
        if code != 200:
            return FakeResp(code, {"errorMessage": "x"})
        t0 = int(pd.Timestamp(json["fromDate"], tz="Asia/Kolkata").timestamp()) + 9 * 3600 + 15 * 60
        side = "ce" if json.get("drvOptionType") == "CALL" else "pe"
        arr = {k: [1.0] for k in ("open", "high", "low", "close", "iv", "volume", "strike", "oi", "spot")}
        return FakeResp(200, {"data": {side: {**arr, "timestamp": [t0]}}})


def test_rolling_chunks_30_days_and_body(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    s = FakeSession()
    df = DhanClient("SECRET", session=s, pause_s=0).rolling_options(13, "2026-01-01", "2026-03-15", "CALL", "ATM+1", 1)
    assert len(s.calls) == 3 and len(df) == 3
    body = s.calls[0][1]
    assert s.calls[0][0].endswith("/charts/rollingoption")
    assert body["strike"] == "ATM+1" and body["expiryFlag"] == "WEEK" and body["securityId"] == 13
    assert body["toDate"] == "2026-01-31"


def test_retry_then_error_without_token(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda s: None)
    s = FakeSession(codes=[429, 200])
    DhanClient("SECRET", session=s, pause_s=0).rolling_options(13, "2026-01-01", "2026-01-05", "PUT", "ATM", 1)
    assert len(s.calls) == 2
    s2 = FakeSession(codes=[401])
    with pytest.raises(RuntimeError) as e:
        DhanClient("SECRET", session=s2, pause_s=0).rolling_options(13, "2026-01-01", "2026-01-05", "PUT", "ATM", 1)
    assert "SECRET" not in str(e.value)
