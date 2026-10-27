"""Pre-registered redesign grid (docs/results/2026-10-27-redesign-preregistration.md).
Runs all variants on train, then ONLY the top 3 by train expectancy on validation. Test stays sealed."""
import dataclasses
import itertools
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lightning.backtest import run
from lightning.calendar import ExpiryCalendar
from lightning.config import load_params
from lightning.data import store
from lightning.features import build_features
from lightning.pricing import RealPricer
from lightning.report import row as _row, window

HORIZONS = {"30m": 2, "60m": 4, "120m": 8, "EOD": 99}


def row(name, t, p):
    return _row(name, t, p.capital)


def main():
    d = Path("data/NIFTY")
    p0 = dataclasses.replace(load_params(), drawdown_halt_pct=1e9)
    spot = store.load_intraday(d / "spot_15m.csv")
    cal = ExpiryCalendar(store.calendar_days(spot), p0.expiry_schedule)
    spot, _ = store.clean_intraday(spot)
    opt = store.load_options(d)
    f = build_features(store.attach_option_volume(spot, opt), store.load_daily(d / "spot_daily.csv"), p0)
    pricer = RealPricer(f, opt)

    variants = {}
    for entry, (hname, hb), htf in itertools.product(["edge", "pullback"], HORIZONS.items(), ["full", "no_monthly", "none"]):
        variants[f"{entry}|{hname}|{htf}"] = dataclasses.replace(p0, entry_mode=entry, horizon_bars=hb, htf_filter=htf)

    results, trades_by = [], {}
    for name, p in variants.items():
        t, _ = run(f, p, pricer, cal)
        trades_by[name] = t
        results.append(row(name, window(t, p0.splits["train"]), p))
        print("train", results[-1], flush=True)
    tr = pd.DataFrame(results).sort_values("exp_r", ascending=False)
    out = Path("data/out/grid"); out.mkdir(parents=True, exist_ok=True)
    tr.to_csv(out / "train.csv", index=False)
    print("\nTRAIN (all 24, ranked):"); print(tr.to_string(index=False))

    top = tr[tr["n"] >= 100].head(3)["variant"].tolist()
    val = pd.DataFrame([row(n, window(trades_by[n], p0.splits["validation"]), variants[n]) for n in top])
    val.to_csv(out / "validation_top3.csv", index=False)
    print("\nVALIDATION (top 3 by train, rank order):"); print(val.to_string(index=False))
    c = val.iloc[0]
    ok = c["n"] > 0 and c["exp_r"] > 0 and c["ci90_lo"] > 0
    print(f"\nCandidate {c['variant']}: {'CONFIRMED' if ok else 'NOT CONFIRMED'} on validation")


if __name__ == "__main__":
    main()
