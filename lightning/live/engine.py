"""Shadow engine: completed 15-min bars -> features -> G1..G5 per strategy -> paper trades at real quotes.

No orders are ever placed. Every candidate is recorded with every gate; candidates that pass the trade-level checks
are paper-traded regardless of the Jev verdict, so A and A+J can be compared on identical candidates later.
Account-level limits (daily loss, entries per day) are evaluated and recorded as `would_block` but not enforced."""
from __future__ import annotations

import dataclasses
import hashlib
import math
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import yaml

from ..config import Params
from ..costs import round_trip_costs
from ..calendar import lot_size_on
from ..features import build_features
from ..signals import BAR, generate
from .db import AuditDB

ROOT = Path(__file__).resolve().parents[2]


def code_version() -> str:
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def config_hash() -> str:
    h = hashlib.sha256()
    for n in ("baseline.yaml", "risk.defaults.yaml", "costs.yaml", "shadow.yaml"):
        h.update((ROOT / "config" / n).read_bytes())
    return h.hexdigest()[:12]


def _ceil(x, tick=0.05):
    return round(math.ceil(x / tick - 1e-9) * tick, 2)


def _floor(x, tick=0.05):
    return round(math.floor(x / tick + 1e-9) * tick, 2)


class ShadowEngine:
    def __init__(self, source, db: AuditDB, p: Params, cfg: dict, jev, mode: str, volume_is_proxy: bool = False):
        self.src, self.db, self.p, self.cfg, self.jev, self.mode = source, db, p, cfg, jev, mode
        self.u = cfg["underlying"]["name"]
        self.step_pts = p.strike_step
        self.band = cfg["band_strikes"]
        self.version, self.chash = code_version(), config_hash()
        self.strategies = {k: dataclasses.replace(p, entry_mode=v["entry_mode"], htf_filter=v["htf_filter"],
                                                  horizon_bars=v["horizon_bars"]) for k, v in cfg["strategies"].items()}
        self.daily = source.daily()
        self.daily_day = source.now().date()
        hist = source.bars(cfg["history_sessions"]).copy()
        stored = {r["ts"]: r["volume"] for r in db.query("SELECT ts, volume FROM bars WHERE underlying=?", (self.u,))}
        if not volume_is_proxy:  # live index volume is a different measure: only use our own stored proxy
            hist["volume"] = [stored.get(t.isoformat(), 0.0) for t in hist.index]
        self.hist = hist[["open", "high", "low", "close", "volume"]]
        self.last_ts = self.hist.index[-1] if len(self.hist) else None
        self.prev_cumvol: dict = {}
        self.cum_day = None
        self.open = {r["id"]: r for r in db.query("SELECT * FROM paper_trades WHERE status='OPEN' AND underlying=?", (self.u,))}
        self.equity = {k: p.capital + sum(r["net"] or 0 for r in db.query(
            "SELECT net FROM paper_trades WHERE status='CLOSED' AND strategy=?", (k,))) for k in self.strategies}
        self.day_state = {}
        risk = yaml.safe_load((ROOT / "config" / "risk.defaults.yaml").read_text())
        self.spread_limit = float(risk["max_spread_pct_of_premium"])

    # ------------------------------------------------------------------ helpers
    def _expiries(self, d: date):
        ex = sorted(e for e in self.src.expiries() if e >= d)
        near = ex[0] if ex else None
        if near is None:
            return None, None, False
        chosen = near if (near - d).days >= self.p.min_dte_days else (ex[1] if len(ex) > 1 else None)
        return near, chosen, near == d

    def _store_quotes(self, ts, expiry, chain):
        spot = chain.get("spot")
        if not spot:
            return
        atm = round(spot / self.step_pts) * self.step_pts
        held = {(("CE" if t["side"] == 1 else "PE"), float(t["strike"])) for t in self.open.values() if t["expiry"] == str(expiry)}
        rows = []
        for (side, k), q in chain["rows"].items():
            if abs(k - atm) <= self.band * self.step_pts or (side, k) in held:
                rows.append({"ts": ts, "underlying": self.u, "expiry": str(expiry), "strike": k, "side": side,
                             "bid": q["bid"], "ask": q["ask"], "ltp": q["ltp"], "iv": q["iv"], "oi": q["oi"],
                             "volume": q["volume"], "spot": spot})
        self.db.insert_many("quotes", rows)

    def _volume_proxy(self, d: date, chain) -> float:
        """Sum over ATM+/-band calls and puts of the change in cumulative day volume since the previous snapshot."""
        if self.cum_day != d:
            self.prev_cumvol, self.cum_day = {}, d
        spot = chain.get("spot")
        if not spot:
            return 0.0
        atm = round(spot / self.step_pts) * self.step_pts
        v = 0.0
        for (side, k), q in chain["rows"].items():
            cum = q.get("volume") or 0.0
            if abs(k - atm) <= self.band * self.step_pts:
                v += max(cum - self.prev_cumvol.get((side, k), 0.0), 0.0)
            self.prev_cumvol[(side, k)] = cum
        return v

    def _close_trade(self, t, ts, q, reason):
        bid, ask = q["bid"], q["ask"]
        px = bid if bid and bid > 0 else 0.05
        costs = round_trip_costs(t["qty"], t["entry_px"], px, self.p.costs)
        net = (px - t["entry_px"]) * t["qty"] - costs
        entry_mid = (t["entry_bid"] + t["entry_ask"]) / 2
        exit_mid = (bid + ask) / 2 if bid and ask else px
        risk = (t["entry_px"] - t["stop"]) * t["qty"]
        fields = {"status": "CLOSED", "exit_ts": ts, "exit_bid": bid, "exit_ask": ask, "exit_px": px, "exit_reason": reason,
                  "costs": costs, "net": net, "net_r": net / risk if risk > 0 else None,
                  "net_mid": (exit_mid - entry_mid) * t["qty"] - costs, "bars_held": t["bars_held"]}
        self.db.update("paper_trades", "id", t["id"], fields)  # last_bid is in-memory only
        self.equity[t["strategy"]] = self.equity.get(t["strategy"], self.p.capital) + net
        ds = self.day_state.setdefault((t["strategy"], ts.date()), {"pnl": 0.0, "entries": 0, "consec": 0})
        ds["pnl"] += net
        ds["consec"] = ds["consec"] + 1 if net < 0 else 0
        del self.open[t["id"]]

    def _check_exits(self, ts, chains, bar_closed: bool):
        for t in list(self.open.values()):
            ch = chains.get(t["expiry"])
            if ch is None:
                continue
            q = ch["rows"].get(("CE" if t["side"] == 1 else "PE", float(t["strike"])))
            if q is None or q["bid"] is None:
                if bar_closed and (ts + BAR).time() >= self.p.square_off:  # no quote at square-off: last known bid
                    lb = t.get("last_bid") or 0.05
                    self._close_trade(t, ts + BAR, {"bid": lb, "ask": lb}, "SQUAREOFF_NO_QUOTE")
                continue
            t["last_bid"] = q["bid"]
            if bar_closed:
                t["bars_held"] += 1
            when = ts + BAR if bar_closed else ts
            if q["bid"] <= t["stop"]:
                self._close_trade(t, when, q, "STOP")
            elif q["bid"] >= t["target"]:
                self._close_trade(t, when, q, "TARGET")
            elif bar_closed and (t["bars_held"] >= t["horizon_bars"] or (ts + BAR).time() >= self.p.square_off):
                self._close_trade(t, when, q, "TIME")

    # ------------------------------------------------------------------ main entry points
    def step(self):
        """Process every newly completed bar. Call a few seconds after each 15-min boundary."""
        now = self.src.now()
        bars = self.src.bars(2)
        new = bars[bars.index > self.last_ts] if self.last_ts is not None else bars.iloc[-1:]
        for ts, b in new.iterrows():
            self._on_bar(ts, b, now)
        self.db.insert("heartbeat", {"ts": now, "status": "OK", "detail": f"bars={len(new)} open={len(self.open)}"})

    def poll(self):
        """Intra-bar stop/target checks for open paper positions."""
        if not self.open:
            return
        now = self.src.now()
        chains = {}
        for e in {t["expiry"] for t in self.open.values()}:
            chains[e] = self.src.chain(date.fromisoformat(e))
            self._store_quotes(now, e, chains[e])
        self._check_exits(now, chains, bar_closed=False)

    def _on_bar(self, ts, b, now):
        d = ts.date()
        if d != self.daily_day:  # monthly/weekly RSI need the latest completed daily candles every session
            self.daily, self.daily_day = self.src.daily(), d
        near, chosen, expiry_day = self._expiries(d)
        chain_near = self.src.chain(near) if near else {"spot": None, "rows": {}}
        chains = {str(near): chain_near}
        vol = self._volume_proxy(d, chain_near)
        self._store_quotes(ts + BAR, near, chain_near)
        self.hist.loc[ts] = [b["open"], b["high"], b["low"], b["close"], vol]
        self.hist = self.hist.sort_index()
        self.db.insert("bars", {"underlying": self.u, "ts": ts, "open": b["open"], "high": b["high"], "low": b["low"],
                                "close": b["close"], "volume": vol}, replace=True)
        self.last_ts = ts
        for e in {t["expiry"] for t in self.open.values()} - set(chains):
            chains[e] = self.src.chain(date.fromisoformat(e))
            self._store_quotes(ts + BAR, e, chains[e])
        self._check_exits(ts, chains, bar_closed=True)

        stale = (now - (ts + BAR)).total_seconds() > self.cfg["stale_after_seconds"]
        f = build_features(self.hist, self.daily, self.p)
        i = len(f) - 1
        for name, ps in self.strategies.items():
            c = generate(f, ps)
            if f.index[i] not in c.index:
                continue
            self._candidate(name, ps, f, i, int(c.loc[f.index[i], "side"]), ts, now, stale, expiry_day, chosen, chains)

    def _candidate(self, name, ps, f, i, side, ts, now, stale, expiry_day, expiry, chains):
        cid = f"{name}|{self.u}|{ts.isoformat()}"
        row = f.iloc[i]
        feats = {k: (None if pd.isna(row[k]) else float(row[k])) for k in
                 ("close", "vwap", "vwma", "st_dir", "atr", "adx", "monthly_rsi", "weekly_rsi_chg", "volume")}
        gates = []
        session_ok = self.hist[self.hist.index.normalize() == ts.normalize()].index.min().strftime("%H:%M") == "09:15"
        g1_reason = "SPECIAL_SESSION" if not session_ok else "STALE_DATA" if stale else ("EXPIRY_DAY" if expiry_day and ps.block_expiry_day_entries else
                                               ("NO_EXPIRY" if expiry is None else None))
        gates.append(("G1", g1_reason is None, g1_reason or "OK", {}))
        gates.append(("G2", True, "RULES_TRUE", {"strategy": name}))
        gates.append(("G3", True, "NOT_IMPLEMENTED", {"note": "no validated statistical model; pass-through"}))
        jv = self.jev.evaluate(f, i, side)
        self.db.insert("jev_calls", {"id": cid, "candidate_id": cid, "requested_at": now, "latency_ms": jv.get("latency_ms"),
                                     "model": jv.get("model"), "request_json": jv.get("request"),
                                     "response_json": jv.get("response"), "decision": jv["decision"],
                                     "detail_json": {"reason": jv.get("reason"), "agg": jv.get("agg")}, "error": jv.get("error")})
        gates.append(("G4", jv["decision"] == "APPROVE", f"{jv['decision']}:{jv.get('reason')}", {}))

        status, g5 = "REJECTED", ("G5", False, "NOT_EVALUATED", {})
        if g1_reason is None:
            g5 = self._g5_and_open(cid, name, ps, side, ts, now, expiry, chains, jv["decision"])
            status = "PAPER_TRADED" if g5[1] else "REJECTED"
        gates.append(g5)
        self.db.insert("candidates", {"id": cid, "created_at": now, "underlying": self.u, "strategy": name, "side": side,
                                      "decision_ts": ts + BAR, "status": status, "features_json": feats,
                                      "code_version": self.version, "config_hash": self.chash, "mode": self.mode})
        for g, ok, reason, det in gates:
            self.db.insert("gates", {"candidate_id": cid, "gate": g, "passed": int(ok), "reason": reason, "detail_json": det})

    def _g5_and_open(self, cid, name, ps, side, ts, now, expiry, chains, jev_decision):
        if any(t["strategy"] == name for t in self.open.values()):
            return ("G5", False, "POSITION_OPEN", {})
        ch = chains.get(str(expiry)) or self.src.chain(expiry)
        chains[str(expiry)] = ch
        spot = ch.get("spot")
        if not spot:
            return ("G5", False, "NO_QUOTE", {})
        k = round(spot / self.step_pts) * self.step_pts
        q = ch["rows"].get(("CE" if side == 1 else "PE", float(k)))
        if not q or not q["bid"] or not q["ask"] or q["ask"] <= 0:
            return ("G5", False, "NO_QUOTE", {"strike": k})
        bid, ask = float(q["bid"]), float(q["ask"])
        mid = (bid + ask) / 2
        spread_pct = 100 * (ask - bid) / mid if mid else 999
        det = {"strike": k, "bid": bid, "ask": ask, "spread_pct": round(spread_pct, 3)}
        ds = self.day_state.setdefault((name, ts.date()), {"pnl": 0.0, "entries": 0, "consec": 0})
        eq = self.equity[name]
        det["would_block"] = [r for r, hit in (
            ("DAILY_LOSS_LIMIT", ds["pnl"] <= -self.p.daily_loss_limit_pct / 100 * eq),
            ("MAX_ENTRIES_DAY", ds["entries"] >= self.p.max_entries_per_day),
            ("CONSEC_LOSS_PAUSE", ds["consec"] >= self.p.max_consecutive_losses)) if hit]
        if spread_pct > self.spread_limit:
            return ("G5", False, "SPREAD_TOO_WIDE", det)
        if ask < self.p.min_premium:
            return ("G5", False, "PREMIUM_FLOOR", det)
        lot = lot_size_on(self.p.lot_schedule, ts.date())
        stop = _floor(ask * (1 - self.p.stop_pct))
        risk_u = ask - stop
        lots = min(math.floor(eq * self.p.risk_pct / 100 / (lot * risk_u)),
                   math.floor(eq * self.p.max_premium_outlay_pct / 100 / (lot * ask)))
        if lots < 1:
            return ("G5", False, "LOTS_LT_1", det)
        qty = lots * lot
        c_u = round_trip_costs(qty, ask, ask, self.p.costs) / qty + (ask - bid)
        reward_u = self.p.net_reward_risk * (risk_u + c_u) + c_u
        if reward_u > ask * self.p.max_target_pct:
            return ("G5", False, "RR_UNREACHABLE", det)
        t = {"id": cid, "candidate_id": cid, "strategy": name, "underlying": self.u, "side": side, "strike": k,
             "expiry": str(expiry), "lots": lots, "qty": qty, "entry_ts": now, "entry_bid": bid, "entry_ask": ask,
             "entry_px": ask, "stop": stop, "target": _ceil(ask + reward_u), "horizon_bars": ps.horizon_bars,
             "bars_held": 0, "status": "OPEN", "jev_decision": jev_decision}
        self.db.insert("paper_trades", t)
        self.open[cid] = t
        ds["entries"] += 1
        return ("G5", True, "OPENED", det)
