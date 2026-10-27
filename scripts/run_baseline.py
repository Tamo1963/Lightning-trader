"""Run baseline variant A.

Real data (from scripts/fetch_history.py):  python scripts/run_baseline.py --data-dir data/NIFTY
--synthetic runs the plumbing on fake data with modelled premiums; its results are meaningless."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lightning.backtest import run
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
    args = a.parse_args()
    p = load_params(args.stage)
    if args.synthetic:
        print("*** SYNTHETIC DATA: plumbing check only, results mean nothing ***")
        spot, daily = synthetic.generate()
        f = build_features(spot, daily, p)
        pricer = ModelPricer(f, p.strike_step, p.iv)
    else:
        if not args.data_dir:
            sys.exit("provide --data-dir, or --synthetic")
        d = Path(args.data_dir)
        spot, daily = store.load_intraday(d / "spot_15m.csv"), store.load_daily(d / "spot_daily.csv")
        problems = store.validate_intraday(spot)
        for pr in problems:
            print("DATA WARNING:", pr)
        opt = store.load_options(d)
        if args.pricer == "real" and opt.empty:
            sys.exit("no option data found; run fetch_history.py or use --pricer model")
        spot = store.attach_option_volume(spot, opt) if not opt.empty else spot
        f = build_features(spot, daily, p)
        pricer = RealPricer(f, opt) if args.pricer == "real" else ModelPricer(f, p.strike_step, p.iv)
    if pricer.name == "model":
        print("*** Modelled premiums (constant IV, no spread): LOW FIDELITY. Not evidence of edge. ***")
    trades, log = run(f, p, pricer)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out / "trades.csv", index=False); log.to_csv(out / "candidates.csv", index=False)
    print("candidate outcomes:", log["status"].value_counts().to_dict())
    for k, v in summarize(trades, p.capital).items():
        print(f"{k:>22}: {v}")


if __name__ == "__main__":
    main()
