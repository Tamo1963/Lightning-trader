"""Shadow pipeline: end-to-end on synthetic replay data, Jev fail-closed behaviour, no order capability."""
import asyncio
import dataclasses
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from lightning.calendar import ExpiryCalendar
from lightning.config import load_params
from lightning.data.dhan import DhanClient
from lightning.data.synthetic import generate as synth
from lightning.features import build_features
from lightning.live.db import AuditDB
from lightning.live.engine import ShadowEngine
from lightning.live.jev import JevGate, aggregate, build_state, decide, has_numbers, rotated_questions
from lightning.live.sources import ReplaySource, parse_chain
from lightning.options import bs_price, years_to
from lightning.signals import BAR

ROOT = Path(__file__).resolve().parent.parent
CFG = yaml.safe_load((ROOT / "config" / "shadow.yaml").read_text())


@pytest.fixture(scope="module")
def world():
    p = load_params()
    spot, daily = synth(years=1.8, seed=5)
    cal = ExpiryCalendar(spot.index.date, p.expiry_schedule)
    tail = spot[spot.index >= spot.index.normalize().unique()[-8]]
    rows = []
    for t, c in zip(tail.index, tail["close"]):
        e = cal.nth_from(t.date(), 0)
        atm = round(c / 50) * 50
        for side in ("CE", "PE"):
            for off in range(-3, 4):
                k = atm + 50 * off
                px = max(bs_price(c, k, years_to(e, t + BAR), 0.14, side == "CE"), 0.05)
                rows.append({"ts": t, "slot": 0, "side": side, "offset": off, "strike": float(k), "open": px,
                             "high": px, "low": px, "close": px, "iv": 14.0, "oi": 1.0, "volume": 1000.0})
    opt = pd.DataFrame(rows)
    return p, spot, daily, cal, opt, tail


def run_replay(world, tmp_path, jev=None, days=6):
    p, spot, daily, cal, opt, tail = world
    p = dataclasses.replace(p, min_dte_days=0, block_expiry_day_entries=False)  # synthetic data has near expiry only
    src = ReplaySource(spot, daily, opt, cal.expiries)
    start = tail.index.normalize().unique()[-days]
    ends = [t + BAR for t in spot.index if t >= start]
    src.clock = ends[0] - BAR + pd.Timedelta(seconds=10)
    db = AuditDB(tmp_path / "t.sqlite")
    cfg = dict(CFG, strategies={"A": {"entry_mode": "edge", "htf_filter": "none", "horizon_bars": 2}})
    eng = ShadowEngine(src, db, p, cfg, jev or JevGate({"enabled": False}), "REPLAY", volume_is_proxy=True)
    for e in ends:
        src.clock = e + pd.Timedelta(seconds=10)
        eng.step()
    return db, eng


def test_end_to_end_records_candidates_gates_and_paper_trades(world, tmp_path):
    db, eng = run_replay(world, tmp_path)
    c = db.query("SELECT * FROM candidates")
    assert c, "expected candidates on synthetic data"
    g = db.query("SELECT gate, COUNT(*) n FROM gates GROUP BY gate")
    assert {r["gate"] for r in g} == {"G1", "G2", "G3", "G4", "G5"}
    t = db.query("SELECT * FROM paper_trades")
    assert t and all(r["entry_px"] == r["entry_ask"] for r in t)  # buy at the ask
    closed = [r for r in t if r["status"] == "CLOSED"]
    assert closed and all(r["exit_px"] == r["exit_bid"] for r in closed if r["exit_reason"] != "SQUAREOFF_NO_QUOTE")
    assert all(r["jev_decision"] == "UNAVAILABLE" for r in t)
    assert len(db.query("SELECT * FROM heartbeat")) > 0


def test_restart_reloads_open_positions(world, tmp_path):
    db, eng = run_replay(world, tmp_path)
    p, spot, daily, cal, opt, tail = world
    src = eng.src
    eng2 = ShadowEngine(src, db, dataclasses.replace(p, min_dte_days=0), dict(CFG, strategies={"A": CFG["strategies"]["A_baseline"]}),
                        JevGate({"enabled": False}), "REPLAY", volume_is_proxy=True)
    assert set(eng2.open) == {r["id"] for r in db.query("SELECT id FROM paper_trades WHERE status='OPEN'")}


class FakeJev:
    def __init__(self, mode):
        self.mode = mode

    async def system_one(self, state, questions):
        if self.mode == "error":
            raise RuntimeError("boom")
        if self.mode == "slow":
            await asyncio.sleep(30)
        out = {}
        for k, q in questions.items():
            if q["type"] == "choice":
                opts = list(q["criteria"])
                fav = "call_favorable" if "call_favorable" in opts else "good_entry"
                out[k] = {"probabilities": {o: (0.8 if o == fav else 0.2 / (len(opts) - 1)) for o in opts}}
            else:
                out[k] = {"probability": 0.7}
        return {"answers": out}


def _feats(world):
    p, spot, daily, cal, opt, tail = world
    return build_features(spot.iloc[-600:], daily, p)


def test_jev_state_is_words_only(world):
    f = _feats(world)
    s = build_state(f, len(f) - 1, 1)
    assert not has_numbers(s) and s["candidate"] == "buy call"


def test_jev_approve_reject_and_fail_closed(world):
    f = _feats(world)
    i = len(f) - 1
    cfg = dict(CFG["jev"], timeout_seconds=1)
    assert JevGate(cfg, FakeJev("ok")).evaluate(f, i, 1)["decision"] == "APPROVE"
    assert JevGate(cfg, FakeJev("ok")).evaluate(f, i, -1)["reason"] == "DIRECTION_MISMATCH"
    assert JevGate(cfg, FakeJev("error")).evaluate(f, i, 1)["decision"] == "REJECT"
    assert JevGate(cfg, FakeJev("slow")).evaluate(f, i, 1)["decision"] == "REJECT"  # timeout
    assert JevGate({"enabled": True, "model": "x"}).evaluate(f, i, 1)["decision"] in ("UNAVAILABLE", "REJECT")


def test_rotation_average_and_spread():
    q, groups = rotated_questions()
    raw = {"answers": {k: {"probabilities": {"call_favorable": 0.9 if k.endswith("0") else 0.5, "put_favorable": 0.05,
                                             "stand_aside": 0.05}} for k in groups["direction"]}}
    raw["answers"].update({k: {"probabilities": {"good_entry": 1.0}} for k in groups["entry_quality"]})
    raw["answers"]["thesis_supported"] = {"probability": 0.6}
    agg = aggregate(raw, groups)
    assert abs(agg["direction"]["probs"]["call_favorable"] - (0.9 + 0.5 + 0.5) / 3) < 1e-9
    assert agg["direction"]["spread"] > 0.2
    assert decide(agg, 1, CFG["jev"]["rule"]) == ("APPROVE", "OK")


def test_parse_chain_and_no_order_methods():
    data = {"last_price": 25642.8, "oc": {"25650.000000": {"ce": {"top_bid_price": 133.55, "top_ask_price": 134,
                                                                   "last_price": 134, "implied_volatility": 9.8, "oi": 1, "volume": 5},
                                                            "pe": None}}}
    ch = parse_chain(data)
    assert ch["spot"] == 25642.8 and ch["rows"][("CE", 25650.0)]["ask"] == 134 and ("PE", 25650.0) not in ch["rows"]
    names = [n for n in dir(DhanClient) if not n.startswith("_")]
    assert not any(w in n.lower() for n in names for w in ("order", "place", "modify", "cancel", "exit_all"))


def test_volume_proxy_uses_cumulative_deltas(world, tmp_path):
    db, eng = run_replay(world, tmp_path, days=2)
    vols = [r["volume"] for r in db.query("SELECT volume FROM bars ORDER BY ts")]
    assert all(v >= 0 for v in vols) and max(vols) > 0


def test_regular_bars_drops_post_close_placeholders():
    from lightning.live.sources import regular_bars
    idx = pd.DatetimeIndex(["2026-10-27 09:15", "2026-10-27 15:15", "2026-10-27 15:30", "2026-10-27 18:15",
                            "2026-10-31 10:00"]).tz_localize("Asia/Kolkata")  # last one is a Saturday
    df = pd.DataFrame({"close": 1.0}, index=idx)
    assert regular_bars(df).index.strftime("%H:%M").tolist() == ["09:15", "15:15"]


def test_api_key_name_fallback(monkeypatch):
    from lightning.live.jev import api_key
    monkeypatch.delenv("JEV_API_KEY", raising=False); monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    assert api_key() is None
    monkeypatch.setenv("TYPESAFE_API_KEY", " k2 ")
    assert api_key() == "k2"
    monkeypatch.setenv("JEV_API_KEY", "k1")
    assert api_key() == "k1"


def test_aggregate_parses_typesafe_response_shape():
    """Shape per typesafe-sdk 0.7.5 SystemOneResponse: answers[name] = choice {choice, confidence, probabilities} or noul {noul}."""
    q, groups = rotated_questions()
    answers = {}
    for k, spec in q.items():
        if spec["type"] == "choice":
            opts = list(spec["criteria"])
            top = "call_favorable" if "call_favorable" in opts else "good_entry"
            answers[k] = {"type": "choice", "choice": top, "confidence": 0.7,
                          "probabilities": {o: (0.7 if o == top else 0.3 / (len(opts) - 1)) for o in opts}}
        else:
            answers[k] = {"type": "noul", "noul": 0.66}
    raw = {"model": "jev-1.13.0", "answers": answers, "usage": {"input_tokens": 100, "output_tokens": 0}}
    agg = aggregate(raw, groups)
    assert agg["thesis_supported"]["probs"] == {"yes": 0.66}
    assert decide(agg, 1, CFG["jev"]["rule"]) == ("APPROVE", "OK")
