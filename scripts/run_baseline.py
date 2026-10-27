"""Run baseline variant A. Real data: --fut data/NIFTY_fut_15m.csv --daily data/NIFTY_spot_daily.csv
--synthetic runs the plumbing on fake data; its results are meaningless."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lightning.backtest import run
from lightning.config import load_params
from lightning.data import store, synthetic
from lightning.features import build_features
from lightning.metrics import summarize


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--fut"); a.add_argument("--daily"); a.add_argument("--synthetic", action="store_true")
    a.add_argument("--stage", default="shadow_paper"); a.add_argument("--out", default="data/out")
    args = a.parse_args()
    p = load_params(args.stage)
    if args.synthetic:
        print("*** SYNTHETIC DATA: plumbing check only, results mean nothing ***")
        fut, daily = synthetic.generate()
    else:
        if not (args.fut and args.daily):
            sys.exit("provide --fut and --daily, or --synthetic")
        fut, daily = store.load_intraday(Path(args.fut)), store.load_daily(Path(args.daily))
        problems = store.validate_intraday(fut)
        if problems:
            sys.exit("data validation failed: " + "; ".join(problems))
    print("*** Modelled premiums (constant IV, no spread): LOW FIDELITY. Not evidence of edge. ***")
    trades, log = run(build_features(fut, daily, p), p)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    trades.to_csv(out / "trades.csv", index=False); log.to_csv(out / "candidates.csv", index=False)
    print("candidate outcomes:", log["status"].value_counts().to_dict())
    for k, v in summarize(trades, p.capital).items():
        print(f"{k:>22}: {v}")


if __name__ == "__main__":
    main()
