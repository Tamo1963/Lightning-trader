from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"


def _load(name: str, config_dir: Path) -> dict:
    return yaml.safe_load((config_dir / name).read_text())


def _t(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


@dataclass(frozen=True)
class Params:
    # instrument and contract
    underlying_security_id: int
    lot_schedule: list
    strike_step: int
    expiry_schedule: list
    min_dte_days: int
    iv: float
    # indicators and signal
    rsi_period: int
    supertrend_period: int
    supertrend_mult: float
    vwma_period: int
    adx_period: int
    atr_period: int
    monthly_rsi_threshold: float
    adx_min: float
    post_roll_block_bars: int
    # barriers and execution
    stop_pct: float
    net_reward_risk: float
    max_target_pct: float
    horizon_bars: int
    min_premium: float
    slippage_pct: float
    tick: float
    # risk
    capital: float
    risk_pct: float
    risk_hard_cap_pct: float
    max_premium_outlay_pct: float
    daily_loss_limit_pct: float
    weekly_loss_limit_pct: float
    drawdown_halt_pct: float
    max_entries_per_day: int
    max_consecutive_losses: int
    entry_start: time
    entry_end: time
    square_off: time
    block_expiry_day_entries: bool
    costs: dict
    data: dict


def load_params(stage: str = "shadow_paper", config_dir: Path = CONFIG_DIR) -> Params:
    b, r, c = (_load(n, config_dir) for n in ("baseline.yaml", "risk.defaults.yaml", "costs.yaml"))
    ind, sig, bar, ex = b["indicators"], b["signal"], b["barriers"], b["execution"]
    risk_pct = r["risk_ladder_pct"][stage]
    if risk_pct > r["risk_per_trade_hard_cap_pct"]:
        raise ValueError("ladder stage exceeds the hard risk cap")
    return Params(
        underlying_security_id=b["underlying_security_id"], lot_schedule=b["lot_schedule"], strike_step=b["strike_step"], expiry_schedule=b["expiry_schedule"],
        min_dte_days=b["min_dte_days"], iv=b["iv"],
        rsi_period=ind["rsi_period"], supertrend_period=ind["supertrend_period"],
        supertrend_mult=ind["supertrend_mult"], vwma_period=ind["vwma_period"],
        adx_period=ind["adx_period"], atr_period=ind["atr_period"],
        monthly_rsi_threshold=sig["monthly_rsi_threshold"], adx_min=sig["adx_min"],
        post_roll_block_bars=sig["post_roll_block_bars"],
        stop_pct=bar["stop_pct"], net_reward_risk=bar["net_reward_risk"],
        max_target_pct=bar["max_target_pct"], horizon_bars=bar["horizon_bars"],
        min_premium=bar["min_premium"], slippage_pct=ex["slippage_pct"], tick=ex["tick"],
        capital=r["capital_inr"], risk_pct=risk_pct,
        risk_hard_cap_pct=r["risk_per_trade_hard_cap_pct"],
        max_premium_outlay_pct=r["max_premium_outlay_pct"],
        daily_loss_limit_pct=r["daily_loss_limit_pct"], weekly_loss_limit_pct=r["weekly_loss_limit_pct"],
        drawdown_halt_pct=r["drawdown_halt_pct"], max_entries_per_day=r["max_entries_per_day"],
        max_consecutive_losses=r["max_consecutive_losses_halt"],
        entry_start=_t(r["entry_window"]["start"]), entry_end=_t(r["entry_window"]["end"]),
        square_off=_t(r["square_off_time"]), block_expiry_day_entries=r["block_expiry_day_entries"],
        costs=c, data=b["data"],
    )
