"""Run baseline variant A.

Real data (from scripts/fetch_history.py):  python scripts/run_baseline.py --data-dir data/NIFTY
--synthetic runs the plumbing on fake data with modelled premiums; its results are meaningless."""
import argparse
import dataclasses
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lightning.backtest import run
from lightning.calendar import ExpiryCalendar
from lightning.config import load_params
from lightning.data import store, synthetic
from lightning.features import build_features
from lightning.metrics import summarize
from lightning.pricing import ModelPricer, RealPricer


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--data-dir"); a.add_argument("--synthetic", action="store_true")
    a.add_argument("--pricer", choices=["real", "model"], default="real")
    a.add_argument("--stage", default="shadow_paper"); a.add_argument("--out", default="data/out")
    a.add_argument("--research", action="store_true",
                   help="disable the drawdown halt so the rules are measured over the whole sample")
    a.add_argument("--periods", default="train,validation", help="comma list of splits to report")
    a.add_argument("--unseal-test", action="store_true", help="allow reporting the sealed test split")
    args = a.parse_args()
    p = load_params(args.stage)
    if args.research:
        p = dataclasses.replace(p, drawdown_halt_pct=1e9)
    periods = [x.strip() for x in args.periods.split(",")]
    if "test" in periods and not args.unseal_test:
        sys.exit("test split is sealed; freeze parameters first, then pass --unseal-test")
    if args.synthetic:
        print("*** SYNTHETIC DATA: plumbing check only, results mean nothing ***")
        spot, daily = synthetic.generate()
        f = build_features(spot, daily, p)
        pricer = ModelPricer(f, p.strike_step, p.iv)
        cal = ExpiryCalendar(f.index.date, p.expiry_schedule)
    else:
        if not args.data_dir:
            sys.exit("provide --data-dir, or --synthetic")
        d = Path(args.data_dir)
        spot, daily = store.load_intraday(d / "spot_15m.csv"), store.load_daily(d / "spot_daily.csv")
        cal_days = store.calendar_days(spot)
        spot, rep = store.clean_intraday(spot)
        print(f"cleaned: dropped {len(rep['dropped_sessions'])} special/partial sessions, "
              f"{rep['dropped_late_bars']} late bars, repaired {rep['repaired_ohlc']} OHLC rows")
        for pr in store.validate_intraday(spot):
            print("DATA WARNING:", pr)
        opt = store.load_options(d)
        if args.pricer == "real" and opt.empty:
            sys.exit("no option data found; run fetch_history.py or use --pricer model")
        spot = store.attach_option_volume(spot, opt) if not opt.empty else spot
        f = build_features(spot, daily, p)
        pricer = RealPricer(f, opt) if args.pricer == "real" else ModelPricer(f, p.strike_step, p.iv)
        cal = ExpiryCalendar(cal_days, p.expiry_schedule)
    if pricer.name == "model":
        print("*** Modelled premiums (constant IV, no spread): LOW FIDELITY. Not evidence of edge. ***")
    trades, log = run(f, p, pricer, cal)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    for name in periods:
        sp = p.splits[name]
        lo, hi = pd.Timestamp(sp["from"]).tz_localize("Asia/Kolkata"), pd.Timestamp(sp["to"]).tz_localize("Asia/Kolkata") + pd.Timedelta(days=1)
        t = trades[(trades["entry_ts"] >= lo) & (trades["entry_ts"] < hi)] if not trades.empty else trades
        lg = log[(log["ts"] >= lo) & (log["ts"] < hi)]
        t.to_csv(out / f"trades_{name}.csv", index=False); lg.to_csv(out / f"candidates_{name}.csv", index=False)
        print(f"\n=== {name} {sp['from']} .. {sp['to']} ===")
        print("candidate outcomes:", lg["status"].value_counts().to_dict())
        for k, v in summarize(t, p.capital).items():
            print(f"{k:>22}: {v}")
        if not t.empty:
            for side, g in t.groupby("side"):
                print(f"   {'CALL' if side == 1 else 'PUT '}: n={len(g)} exp_r={g['net_r'].mean():+.3f} win={(g['net'] > 0).mean():.2f}")

if __name__ == "__main__":
    main()
