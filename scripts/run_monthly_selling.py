"""Pre-registered monthly hedged selling study (docs/results/2026-10-28-monthly-selling-preregistration.md)."""
import itertools
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lightning.config import load_params
from lightning.data import store
from lightning.monthly_selling import Chain, MonthlyVariant, simulate

TRAIN = (date(2016, 1, 1), date(2024, 6, 30))
VAL = (date(2024, 7, 1), date(2025, 9, 30))


def stats(name, t):
    if t.empty:
        return {"variant": name, "n": 0, "mean_r": float("-inf")}
    rng = np.random.default_rng(0)
    r = t["r"].to_numpy()
    boots = [rng.choice(r, len(r)).mean() for _ in range(4000)]
    eq = t["net"].cumsum()
    miss = t[t["exit_reason"] != "TARGET"]
    return {"variant": name, "n": len(t), "mean_r": round(r.mean(), 4), "ci90_lo": round(np.quantile(boots, .05), 4),
            "ci90_hi": round(np.quantile(boots, .95), 4), "target_hit": round((t["exit_reason"] == "TARGET").mean(), 3),
            "stop_hit": round((t["exit_reason"] == "STOP").mean(), 3), "mean_r_missed": round(miss["r"].mean(), 4) if len(miss) else None,
            "worst_inr": round(t["net"].min()), "net_inr": round(t["net"].sum()), "max_dd_inr": round((eq.cummax() - eq).max()),
            "median_days": float(t["days_held"].median()), "zero_vol_share": round(t["zero_vol_share"].mean(), 3)}


def window(t, w):
    return t[(t["entry_day"] >= w[0]) & (t["entry_day"] <= w[1])] if not t.empty else t


def main():
    clamp = "--clamp-spreads" in sys.argv  # sensitivity run, NOT the pre-registered test
    p = load_params()
    files = sorted((ROOT / "data" / "nse" / "nifty_monthly").glob("*.csv"))
    df = pd.concat([pd.read_csv(f, parse_dates=["date", "expiry"]) for f in files], ignore_index=True)
    df["date"], df["expiry"] = df["date"].dt.date, df["expiry"].dt.date
    print(f"bhavcopy days: {df['date'].nunique()} ({df['date'].min()} .. {df['date'].max()}), rows {len(df)}")
    chain = Chain(df)
    spot = store.load_daily(ROOT / "data" / "NIFTY" / "spot_daily.csv")["close"]
    res, trades = [], {}
    for st, en, sp in itertools.product(["fly", "condor_n", "condor_w"], ["early", "mid"], ["none", "stop10"]):
        name = f"{st}|{en}|{sp}"
        t, log = simulate(chain, spot, MonthlyVariant(st, en, sp, clamp_spreads=clamp), p, p.capital)
        trades[name] = t
        res.append(stats(name, window(t, TRAIN)))
        print("train", res[-1], flush=True)
    out = ROOT / "data" / "out" / ("monthly_selling_clamped" if clamp else "monthly_selling"); out.mkdir(parents=True, exist_ok=True)
    for k, t in trades.items():
        t.to_csv(out / f"{k.replace('|', '_')}.csv", index=False)
    tr = pd.DataFrame(res).sort_values("mean_r", ascending=False)
    tr.to_csv(out / "train.csv", index=False)
    print("\nTRAIN (ranked):"); print(tr.to_string(index=False))
    top = tr[tr["n"] >= 60].head(3)["variant"].tolist()
    if not top:
        print("no eligible variant (>= 60 train trades)"); return
    val = pd.DataFrame([stats(n, window(trades[n], VAL)) for n in top])
    val.to_csv(out / "validation_top3.csv", index=False)
    print("\nVALIDATION (top 3 by train):"); print(val.to_string(index=False))
    c = val.iloc[0]
    print(f"\nCandidate {c['variant']}: {'CONFIRMED' if c['n'] and c['mean_r'] > 0 and c['ci90_lo'] > 0 else 'NOT CONFIRMED'} on validation")


if __name__ == "__main__":
    main()
