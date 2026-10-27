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
        print("  raw spot WARNING:", pr)
    cal_days = store.calendar_days(spot)
    spot, rep = store.clean_intraday(spot)
    print(f"  cleaned: dropped {rep['dropped_late_bars']} bars at/after 15:30, {len(rep['dropped_sessions'])} special/partial "
          f"sessions {rep['dropped_sessions']}, repaired {rep['repaired_ohlc']} OHLC rows")
    for pr in store.validate_intraday(spot):
        print("  clean spot WARNING:", pr)

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
    # calendar check: at 14:00 the near-expiry ATM straddle collapses on expiry day
    cal = ExpiryCalendar(cal_days, p.expiry_schedule)
    a14 = near_atm[near_atm["ts"].dt.strftime("%H:%M") == "14:00"]
    st = a14.groupby([a14["ts"].dt.date, "side"])["close"].last().unstack().sum(axis=1)
    is_exp = st.index.map(lambda x: cal.is_expiry(x))
    print(f"14:00 ATM straddle median: calendar expiry days {st[is_exp].median():.1f}, other days {st[~is_exp].median():.1f}")
    print(f"  non-expiry days with straddle < 25% of normal (possible missed expiry): "
          f"{sorted(st[~is_exp & (st < 0.25 * st[~is_exp].median())].index)}")

if __name__ == "__main__":
    main()
