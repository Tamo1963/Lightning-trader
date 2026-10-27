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
from lightning.metrics import summarize
from lightning.pricing import RealPricer

IST = "Asia/Kolkata"
HORIZONS = {"30m": 2, "60m": 4, "120m": 8, "EOD": 99}


def window(trades, sp):
    lo = pd.Timestamp(sp["from"]).tz_localize(IST)
    hi = pd.Timestamp(sp["to"]).tz_localize(IST) + pd.Timedelta(days=1)
    return trades[(trades["entry_ts"] >= lo) & (trades["entry_ts"] < hi)] if not trades.empty else trades


def row(name, t, p):
    s = summarize(t, p.capital)
    if s["n_trades"] == 0:
        return {"variant": name, "n": 0}
    calls = int((t["side"] == 1).sum())
    return {"variant": name, "n": s["n_trades"], "calls": calls, "puts": s["n_trades"] - calls,
            "win": round(s["win_rate"], 3), "exp_r": round(s["expectancy_r"], 4),
            "ci90_lo": round(s["expectancy_r_ci90"][0], 4), "ci90_hi": round(s["expectancy_r_ci90"][1], 4),
            "pf": round(s["profit_factor"], 3), "pnl": round(s["total_pnl_inr"]), "max_dd_pct": round(s["max_drawdown_pct"], 1),
            "time_exits": round(s["exit_reasons"].get("TIME", 0) / s["n_trades"], 2)}


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
