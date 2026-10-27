"""Baseline (variant A) backtest: candidates -> option premium (real Dhan data or model) -> triple-barrier exit -> risk limits.

Timing: decision at bar close, entry at the NEXT bar open, one position at a time per instrument.
If stop and target are both touched inside one bar, the stop is assumed to hit first (conservative).
"""
from __future__ import annotations

import math

import pandas as pd

from .config import Params
from .costs import round_trip_costs
from .calendar import ExpiryCalendar, lot_size_on
from .pricing import ModelPricer
from .signals import BAR, generate


def _ceil(x: float, tick: float) -> float:
    return round(math.ceil(x / tick - 1e-9) * tick, 2)


def _floor(x: float, tick: float) -> float:
    return round(math.floor(x / tick + 1e-9) * tick, 2)


def simulate_trade(f: pd.DataFrame, i: int, side: int, equity: float, p: Params, pricer, cal: ExpiryCalendar):
    """Returns (trade dict, None) or (None, reject_reason). `i` is the decision bar; entry is bar i+1."""
    idx, e = f.index, i + 1
    d = idx[e].date()
    slot, expiry = cal.choose(d, p.min_dte_days)
    c = pricer.select(i, side, slot, expiry)
    first = pricer.bar(c, e) if c is not None else None
    if first is None:
        return None, "NO_OPTION_DATA"
    lot = lot_size_on(p.lot_schedule, d)
    entry = _ceil(first[0] * (1 + p.slippage_pct), p.tick)
    if entry < p.min_premium:
        return None, "PREMIUM_FLOOR"
    stop = _floor(entry * (1 - p.stop_pct), p.tick)
    risk_u = entry - stop
    lots = math.floor(equity * p.risk_pct / 100 / (lot * risk_u))
    lots = min(lots, math.floor(equity * p.max_premium_outlay_pct / 100 / (lot * entry)))
    if lots < 1:
        return None, "LOTS_LT_1"
    qty = lots * lot
    c_u = round_trip_costs(qty, entry, entry, p.costs) / qty + p.slippage_pct * entry
    reward_u = p.net_reward_risk * (risk_u + c_u) + c_u
    if reward_u > entry * p.max_target_pct:
        return None, "RR_UNREACHABLE"
    target = _ceil(entry + reward_u, p.tick)

    last = min(e + p.horizon_bars, len(idx)) - 1
    prev_close = first[0]
    for j in range(e, last + 1):
        end = idx[j] + BAR
        b = first if j == e else pricer.bar(c, j)
        forced = (j == last) or end.time() >= p.square_off or idx[j + 1].date() != idx[j].date()
        if b is None:  # data gap mid-trade: exit at the last known price, flagged
            px, reason = prev_close, "DATA_GAP"
        else:
            po, ph, pl, pc = b
            prev_close = pc
            if j > e and po <= stop:
                px, reason = po, "STOP_GAP"
            elif j > e and po >= target:
                px, reason = po, "TARGET_GAP"
            elif pl <= stop:
                px, reason = stop, "STOP"
            elif ph >= target:
                px, reason = target, "TARGET"
            elif forced:
                px, reason = pc, "TIME"
            else:
                continue
        sell = _floor(px * (1 - p.slippage_pct), p.tick)
        gross = (sell - entry) * qty
        costs = round_trip_costs(qty, entry, sell, p.costs)
        net = gross - costs
        risk_inr = risk_u * qty
        return {
            "entry_ts": idx[e], "exit_ts": end, "exit_idx": j, "side": side, "strike": c.strike,
            "expiry": expiry, "pricer": pricer.name, "lots": lots, "qty": qty, "entry": entry, "stop": stop,
            "target": target, "exit_fill": sell, "exit_reason": reason, "gross": gross, "costs": costs,
            "net": net, "risk_inr": risk_inr, "net_r": net / risk_inr, "bars_held": j - e + 1,
        }, None
    return None, "NO_EXIT"  # unreachable: the last bar is always forced


def run(f: pd.DataFrame, p: Params, pricer=None, cal: ExpiryCalendar | None = None, cands: pd.DataFrame | None = None):
    """Returns (trades, candidate_log). Every candidate is logged with TRADED or its rejection reason.
    Defaults: modelled premiums and an expiry calendar built from the data's own trading days."""
    pricer = pricer or ModelPricer(f, p.strike_step, p.iv)
    cal = cal or ExpiryCalendar(f.index.date, p.expiry_schedule)
    cands = generate(f, p) if cands is None else cands
    pos = {ts: k for k, ts in enumerate(f.index)}
    equity = peak = p.capital
    free_idx = -1
    halted = False
    day = week = None
    day_start_eq = week_start_eq = equity
    day_pnl = week_pnl = 0.0
    day_entries = consec = 0
    trades, log = [], []

    for ts, row in cands.iterrows():
        i, side = pos[ts], int(row["side"])
        d = ts.date()
        wk = ts.isocalendar()[:2]
        if d != day:
            day, day_start_eq, day_pnl, day_entries, consec = d, equity, 0.0, 0, 0
        if wk != week:
            week, week_start_eq, week_pnl = wk, equity, 0.0
        rec = {"ts": ts, "side": side}

        if i + 1 >= len(f) or f.index[i + 1].date() != d:
            reason = "NO_NEXT_BAR"
        elif i < free_idx:
            reason = "POSITION_OPEN"
        elif halted:
            reason = "DRAWDOWN_HALT"
        elif p.block_expiry_day_entries and cal.is_expiry(d):
            reason = "EXPIRY_DAY"
        elif day_entries >= p.max_entries_per_day:
            reason = "MAX_ENTRIES_DAY"
        elif day_pnl <= -p.daily_loss_limit_pct / 100 * day_start_eq:
            reason = "DAILY_LOSS_LIMIT"
        elif week_pnl <= -p.weekly_loss_limit_pct / 100 * week_start_eq:
            reason = "WEEKLY_LOSS_LIMIT"
        elif consec >= p.max_consecutive_losses:
            reason = "CONSEC_LOSS_PAUSE"
        else:
            t, reason = simulate_trade(f, i, side, equity, p, pricer, cal)
            if t is not None:
                reason = "TRADED"
                trades.append(t)
                free_idx = t["exit_idx"]
                equity += t["net"]
                day_pnl += t["net"]
                week_pnl += t["net"]
                day_entries += 1
                consec = consec + 1 if t["net"] < 0 else 0
                peak = max(peak, equity)
                if (peak - equity) / peak * 100 >= p.drawdown_halt_pct:
                    halted = True
        rec["status"] = reason
        log.append(rec)

    return pd.DataFrame(trades), pd.DataFrame(log)
