"""Pre-registered volatility-expansion grid (docs/results/2026-10-27-volexp-preregistration.md).
All 12 variants on train; only the top 3 by train expectancy on validation. Test sealed."""
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
from lightning.orb import day_filters, generate_orb
from lightning.pricing import RealPricer
from lightning.report import direction_atr, row, window

ORS = {"OR30": 2, "OR60": 4}
FILTERS = ["none", "compression", "low_iv"]
HORIZONS = {"60m": 4, "EOD": 99}


def main():
    d = Path("data/NIFTY")
    p0 = dataclasses.replace(load_params(), drawdown_halt_pct=1e9)
    spot = store.load_intraday(d / "spot_15m.csv")
    cal = ExpiryCalendar(store.calendar_days(spot), p0.expiry_schedule)
    spot, _ = store.clean_intraday(spot)
    opt = store.load_options(d)
    daily = store.load_daily(d / "spot_daily.csv")
    f = build_features(store.attach_option_volume(spot, opt), daily, p0)
    flt = day_filters(f, daily, opt)
    print("filter days (all sessions):", {c: int(flt[c].sum()) for c in flt}, "of", len(flt))
    pricer = RealPricer(f, opt)

    results, trades_by, cands_by, params_by = [], {}, {}, {}
    for (orn, k), filt, (hn, hb) in itertools.product(ORS.items(), FILTERS, HORIZONS.items()):
        name = f"{orn}|{filt}|{hn}"
        cands = generate_orb(f, k, None if filt == "none" else flt[filt])
        p = dataclasses.replace(p0, horizon_bars=hb)
        t, _ = run(f, p, pricer, cal, cands=cands)
        trades_by[name], cands_by[name], params_by[name] = t, cands, p
        r = row(name, window(t, p0.splits["train"]), p.capital)
        dirn = window(direction_atr(f, cands, hb).rename("x").to_frame().rename_axis("ts").reset_index(), p0.splits["train"], "ts")["x"]
        r["dir_atr"] = round(dirn.mean(), 3) if len(dirn) else float("nan")
        results.append(r)
        print("train", r, flush=True)

    tr = pd.DataFrame(results).sort_values("exp_r", ascending=False)
    out = Path("data/out/volexp"); out.mkdir(parents=True, exist_ok=True)
    tr.to_csv(out / "train.csv", index=False)
    print("\nTRAIN (all 12, ranked):"); print(tr.to_string(index=False))

    top = tr[tr["n"] >= 60].head(3)["variant"].tolist()
    vals = []
    for n in top:
        r = row(n, window(trades_by[n], p0.splits["validation"]), p0.capital)
        dirn = window(direction_atr(f, cands_by[n], params_by[n].horizon_bars).rename("x").to_frame().rename_axis("ts").reset_index(),
                      p0.splits["validation"], "ts")["x"]
        r["dir_atr"] = round(dirn.mean(), 3) if len(dirn) else float("nan")
        vals.append(r)
    val = pd.DataFrame(vals)
    val.to_csv(out / "validation_top3.csv", index=False)
    print("\nVALIDATION (top 3 by train, rank order):"); print(val.to_string(index=False))
    c = val.iloc[0]
    ok = c["n"] > 0 and c["exp_r"] > 0 and c["ci90_lo"] > 0
    print(f"\nCandidate {c['variant']}: {'CONFIRMED' if ok else 'NOT CONFIRMED'} on validation")


if __name__ == "__main__":
    main()
