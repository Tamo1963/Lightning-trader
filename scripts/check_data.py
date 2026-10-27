"""Data-quality report for data/<NAME>/ before any backtest is trusted."""
import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lightning.calendar import ExpiryCalendar
from lightning.config import load_params
from lightning.data import store


def main():
    a = argparse.ArgumentParser(); a.add_argument("--data-dir", default="data/NIFTY")
    d = Path(a.parse_args().data_dir)
    p = load_params()
    spot = store.load_intraday(d / "spot_15m.csv")
    daily = store.load_daily(d / "spot_daily.csv")
    print(f"spot_15m: {len(spot)} bars, {spot.index[0]} .. {spot.index[-1]}, {spot.index.normalize().nunique()} sessions")
    print(f"spot_daily: {len(daily)} days, {daily.index[0].date()} .. {daily.index[-1].date()}")
    for pr in store.validate_intraday(spot):
        print("  spot WARNING:", pr)

    opt = store.load_options(d)
    if opt.empty:
        print("no options data"); return
    print(f"options: {len(opt)} rows")
    cov = opt.groupby(["slot", "side", "offset"]).size().unstack("offset")
    print("bars per series (rows: slot/side, cols: strike offset):"); print(cov.to_string())
    near_atm = opt[(opt.slot == 0) & (opt.offset == 0)]
    for side in ("CE", "PE"):
        s = near_atm[near_atm.side == side].set_index("ts")
        miss = spot.index.difference(s.index)
        print(f"near ATM {side}: missing {len(miss)} of {len(spot)} spot bars ({len(miss)/len(spot):.1%}); "
              f"zero-volume {(s.volume == 0).mean():.1%}; iv==0 {(s.iv == 0).mean():.1%}")
    # strike vs spot sanity
    gap = (near_atm["strike"] - near_atm["spot"]).abs()
    print(f"|ATM strike - spot|: median {gap.median():.1f}, 99th pct {gap.quantile(.99):.1f} (strike step {p.strike_step})")
    # calendar check: near-contract last close should be ~intrinsic on expiry days
    cal = ExpiryCalendar(spot.index.date, p.expiry_schedule)
    last = near_atm[near_atm.side == "CE"].groupby(near_atm["ts"].dt.date)["close"].last()
    tiny_days = set(last[last <= 1.0].index)
    exp_days = {e for e in cal.expiries if spot.index[0].date() <= e <= spot.index[-1].date()}
    print(f"calendar expiries in range: {len(exp_days)}; days where near ATM call closed <= 1: {len(tiny_days)}")
    print(f"  tiny-close days not in calendar: {sorted(tiny_days - exp_days)[:15]}")
    print(f"  calendar expiries without tiny close: {sorted(exp_days - tiny_days)[:15]}")


if __name__ == "__main__":
    main()
