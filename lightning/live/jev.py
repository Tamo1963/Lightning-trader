"""Jev gate (G4) for shadow testing: labelled state, option-order rotation, fail-closed decision.

The decision rule thresholds are DRAFTS; shadow data (Jev outputs + paper outcomes of every candidate) is what they
will be fitted on. The response parser is tolerant because the exact SDK response shape is confirmed only by the
Phase 0 spike (scripts/jev_spike.py)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..indicators import rsi

QUESTIONS = Path(__file__).resolve().parents[2] / "schemas" / "jev_questions.json"


def _bucket(x, edges, labels):
    if x is None or not np.isfinite(x):
        return "unknown"
    for e, l in zip(edges, labels):
        if x < e:
            return l
    return labels[-1]


def build_state(f: pd.DataFrame, i: int, side: int) -> dict:
    """Words only, never raw numbers (Jev's documented weak spot); no dates or tickers."""
    r = f.iloc[i]
    stretch = (r["close"] - r["vwap"]) / r["atr"] if r["atr"] else np.nan
    rsi15 = rsi(f["close"].iloc[max(0, i - 60):i + 1]).iat[-1]
    t = (f.index[i] + pd.Timedelta(minutes=15)).time()
    return {
        "instrument": "index option underlying",
        "candidate": "buy call" if side == 1 else "buy put",
        "trend_15m": "up" if r["st_dir"] == 1 else "down",
        "trend_strength": _bucket(r["adx"], [15, 25], ["weak", "moderate", "strong"]),
        "price_vs_value": ("above" if stretch > 0 else "below") + " session value, " +
                          _bucket(abs(stretch), [0.5, 1.5], ["close to it", "moderately stretched", "far stretched"]),
        "price_vs_vwma": "above" if r["close"] > r["vwma"] else "below",
        "momentum_15m": _bucket(rsi15, [30, 45, 55, 70], ["oversold", "weak", "neutral", "strong", "overbought"]),
        "monthly_regime": "bullish" if r["monthly_rsi"] > 50 else "bearish",
        "weekly_momentum": "rising" if r["weekly_rsi_chg"] > 0 else "falling",
        "session_phase": "morning" if t.hour < 11 else ("midday" if (t.hour, t.minute) < (13, 30) else "afternoon"),
    }


def has_numbers(state: dict) -> bool:
    return any(re.search(r"\d", str(v)) for v in state.values())


def rotated_questions() -> tuple[dict, dict]:
    spec = json.loads(QUESTIONS.read_text())["questions"]
    out, groups = {}, {}
    for name, q in spec.items():
        if q["type"] == "choice":
            labels = list(q["criteria"])
            for k in range(len(labels)):
                order = labels[k:] + labels[:k]
                out[f"{name}_{k}"] = {"type": "choice", "instructions": q["instructions"],
                                      "criteria": {o: q["criteria"][o] for o in order}}
                groups.setdefault(name, []).append(f"{name}_{k}")
        else:
            out[name] = dict(q)
            groups[name] = [name]
    return out, groups


def _find_probs(obj, key):
    """Locate the probability mapping for question `key` in an unknown response shape."""
    if isinstance(obj, dict):
        if key in obj:
            v = obj[key]
            for cand in ("probabilities", "probs", "distribution"):
                if isinstance(v, dict) and isinstance(v.get(cand), dict):
                    return v[cand]
            if isinstance(v, dict) and isinstance(v.get("noul"), (int, float)):  # TypeSafe noul answer
                return {"yes": v["noul"]}
            if isinstance(v, dict) and isinstance(v.get("probability"), (int, float)):
                return {"yes": v["probability"]}
            if isinstance(v, (int, float)):
                return {"yes": v}
            if isinstance(v, dict) and all(isinstance(x, (int, float)) for x in v.values()):
                return v
        for v in obj.values():
            hit = _find_probs(v, key)
            if hit is not None:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = _find_probs(v, key)
            if hit is not None:
                return hit
    return None


def aggregate(raw: dict, groups: dict) -> dict:
    """Average probabilities over rotations; spread = max abs deviation across rotations."""
    out = {}
    for name, keys in groups.items():
        ps = [_find_probs(raw, k) for k in keys]
        if any(p is None for p in ps):
            raise ValueError(f"cannot parse answer for {name}")
        opts = sorted(set().union(*ps))
        mean = {o: float(np.mean([p.get(o, 0.0) for p in ps])) for o in opts}
        spread = max(abs(p.get(o, 0.0) - mean[o]) for p in ps for o in opts)
        out[name] = {"probs": mean, "spread": spread}
    return out


def decide(agg: dict, side: int, rule: dict) -> tuple[str, str]:
    want = "call_favorable" if side == 1 else "put_favorable"
    d, q = agg["direction"]["probs"], agg["entry_quality"]["probs"]
    thesis = agg["thesis_supported"]["probs"]
    p_yes = thesis.get("yes", thesis.get("true", max(thesis.values()) if thesis else 0.0))
    if max(d, key=d.get) != want:
        return "REJECT", "DIRECTION_MISMATCH"
    if d.get("stand_aside", 0) > rule["max_stand_aside"]:
        return "REJECT", "STAND_ASIDE"
    if max(q, key=q.get) != "good_entry":
        return "REJECT", "ENTRY_" + max(q, key=q.get).upper()
    if p_yes < rule["min_thesis"]:
        return "REJECT", "THESIS_WEAK"
    return "APPROVE", "OK"


def api_key() -> str | None:
    """JEV_API_KEY, or the SDK's own TYPESAFE_API_KEY. Passed to the client explicitly; never logged."""
    return (os.environ.get("JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY") or "").strip() or None


class JevGate:
    """client: object with async `system_one(state=..., questions=...)`; built from typesafe-sdk when not given."""

    def __init__(self, cfg: dict, client=None):
        self.cfg, self.client = cfg, client
        self.questions, self.groups = rotated_questions()
        key = api_key()
        if self.client is None and cfg.get("enabled") and key:
            try:
                from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy  # optional dependency
                self.client = AsyncTypeSafeClient(api_key=key, model=cfg["model"], timeout=cfg["timeout_seconds"],
                                                  retry=RetryPolicy(max_retries=cfg["max_retries"]))
            except Exception as e:  # noqa: BLE001 - any SDK problem means fail closed
                self.init_error = str(e)

    def evaluate(self, f: pd.DataFrame, i: int, side: int) -> dict:
        state = build_state(f, i, side)
        rec = {"model": self.cfg.get("model"), "request": {"state": state, "questions": self.questions}}
        if has_numbers(state):
            return {**rec, "decision": "REJECT", "reason": "STATE_HAS_NUMBERS", "error": "numbers in state"}
        if self.client is None:
            return {**rec, "decision": "UNAVAILABLE", "reason": getattr(self, "init_error", "NO_API_KEY"), "error": None}
        t0 = time.perf_counter()
        try:
            resp = asyncio.run(asyncio.wait_for(self.client.system_one(state=state, questions=self.questions),
                                                self.cfg["timeout_seconds"] + 2))
            raw = resp.model_dump() if hasattr(resp, "model_dump") else (resp.dict() if hasattr(resp, "dict") else resp)
            agg = aggregate(raw, self.groups)
            decision, reason = decide(agg, side, self.cfg["rule"])
            return {**rec, "response": raw, "agg": agg, "decision": decision, "reason": reason, "error": None,
                    "latency_ms": int(1000 * (time.perf_counter() - t0))}
        except Exception as e:  # noqa: BLE001 - fail closed on anything
            return {**rec, "decision": "REJECT", "reason": "ERROR", "error": str(e)[:300],
                    "latency_ms": int(1000 * (time.perf_counter() - t0))}
