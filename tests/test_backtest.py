import numpy as np
import pandas as pd
import pytest

from lightning.backtest import simulate_trade, run
from lightning.config import load_params
from lightning.signals import BAR

IST = "Asia/Kolkata"


def path_frame(closes, start="2026-10-27 09:15"):  # Tuesday=expiry weekday; test uses own params so day is irrelevant
    idx = pd.date_range(start, periods=len(closes), freq="15min", tz=IST)
    c = np.array(closes, float)
    o = np.concatenate([[c[0]], c[:-1]])
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + 0.01, "low": np.minimum(o, c) - 0.01,
                         "close": c, "volume": 1000}, index=idx)


@pytest.fixture
def p():
    return load_params()


def test_call_target_hit_on_big_up_move(p):
    f = path_frame([25000, 25000, 25400, 25400, 25400])
    t, why = simulate_trade(f, 0, +1, p.capital, p)
    assert why is None and t["exit_reason"] == "TARGET" and t["net"] > 0


def test_call_stop_hit_on_big_down_move(p):
    f = path_frame([25000, 25000, 24600, 24600, 24600])
    t, _ = simulate_trade(f, 0, +1, p.capital, p)
    assert t["exit_reason"] in ("STOP", "STOP_GAP") and t["net"] < 0


def test_put_mirrors_call(p):
    f = path_frame([25000, 25000, 24600, 24600, 24600])
    t, _ = simulate_trade(f, 0, -1, p.capital, p)
    assert t["exit_reason"] == "TARGET" and t["net"] > 0


def test_time_exit_when_nothing_happens(p):
    f = path_frame([25000] * 6)
    t, _ = simulate_trade(f, 0, +1, p.capital, p)
    assert t["exit_reason"] == "TIME" and t["bars_held"] == p.horizon_bars and t["net"] < 0  # theta + costs


def test_risk_never_exceeds_budget(p):
    f = path_frame([25000] * 6)
    t, _ = simulate_trade(f, 0, +1, p.capital, p)
    assert t["risk_inr"] <= p.capital * p.risk_pct / 100 + 1e-6
    assert t["risk_inr"] <= p.capital * p.risk_hard_cap_pct / 100


def test_skips_when_one_lot_exceeds_budget(p):
    f = path_frame([25000] * 6)
    t, why = simulate_trade(f, 0, +1, 1_000.0, p)
    assert t is None and why == "LOTS_LT_1"


def test_entry_is_next_bar_open_and_pays_slippage(p):
    f = path_frame([25000, 25000, 25000, 25000])
    t, _ = simulate_trade(f, 0, +1, p.capital, p)
    assert t["entry_ts"] == f.index[1]
    assert t["entry"] > t["stop"] and t["target"] > t["entry"]


def test_reward_risk_after_costs_meets_target(p):
    f = path_frame([25000] * 6)
    t, _ = simulate_trade(f, 0, +1, p.capital, p)
    from lightning.costs import round_trip_costs
    qty = t["qty"]
    win = (t["target"] * (1 - p.slippage_pct) - t["entry"]) * qty - round_trip_costs(qty, t["entry"], t["target"], p.costs)
    loss = (t["entry"] - t["stop"] * (1 - p.slippage_pct)) * qty + round_trip_costs(qty, t["entry"], t["stop"], p.costs)
    assert win / loss >= p.net_reward_risk * 0.95  # small tolerance: costs estimated at entry price


def test_run_invariants_on_synthetic(feats, params):
    trades, log = run(feats, params)
    assert len(trades) > 20
    assert (trades["entry_ts"].sort_values().values == trades["entry_ts"].values).all()
    assert (trades["entry_ts"].iloc[1:].values >= trades["exit_ts"].iloc[:-1].values - BAR.to_timedelta64()).all()  # no overlap
    t_ = trades["entry_ts"].dt
    assert (t_.time >= params.entry_start).all()
    assert (trades["risk_inr"] <= params.capital * params.risk_hard_cap_pct / 100 * 1.5).all()
    assert (trades["entry_ts"].dt.weekday != params.expiry_weekday).all()  # expiry-day block
    assert trades.groupby(trades["entry_ts"].dt.date).size().max() <= params.max_entries_per_day
    assert log["status"].isin(["TRADED"]).sum() == len(trades)
