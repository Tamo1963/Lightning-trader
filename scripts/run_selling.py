"""Pre-registered option-selling grid (docs/results/2026-10-27-selling-preregistration.md).
All 16 variants on train; only the top 3 by train expectancy on validation. Test sealed."""
import dataclasses
import itertools
import sys
from datetime import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lightning.calendar import ExpiryCalendar
from lightning.config import load_params
from lightning.data import store
from lightning.features import build_features
from lightning.orb import day_filters
from lightning.report import row, window
from lightning.spreads import OptionBook, SpreadVariant, run_selling


def stats(name, t, capital, book_share):
    r = row(name, t, capital)
    r.pop("calls", None); r.pop("puts", None)
    if not t.empty:
        r["worst_day_inr"] = round(t["net"].min())
        r["exits"] = t["exit_reason"].value_counts().to_dict()
    r["modelled_leg_share"] = book_share
    return r


def main():
    d = Path("data/NIFTY")
    p = dataclasses.replace(load_params(), drawdown_halt_pct=1e9)
    spot = store.load_intraday(d / "spot_15m.csv")
    cal = ExpiryCalendar(store.calendar_days(spot), p.expiry_schedule)
    spot, _ = store.clean_intraday(spot)
    opt = store.load_options(d)
    daily = store.load_daily(d / "spot_daily.csv")
    f = build_features(store.attach_option_volume(spot, opt), daily, p)
    flt = day_filters(f, daily, opt)

    results, trades_by, share_by = [], {}, {}
    for st, et, ex, flt_name in itertools.product(["fly", "condor"], [time(10, 0), time(12, 0)], ["time", "stop_tp"], ["none", "iv_high"]):
        name = f"{st}|{et.strftime('%H%M')}|{ex}|{flt_name}"
        book = OptionBook(f, opt)
        t, log = run_selling(f, book, SpreadVariant(st, et, ex), p, cal, None if flt_name == "none" else flt[flt_name])
        share = round(book.modelled / max(book.lookups, 1), 3)
        trades_by[name], share_by[name] = t, share
        results.append(stats(name, window(t, p.splits["train"]), p.capital, share))
        print("train", results[-1], flush=True)
        if name.endswith("time|none") and st == "fly" and et == time(10, 0):
            print("  log statuses (all periods):", log["status"].value_counts().to_dict())

    tr = pd.DataFrame(results).sort_values("exp_r", ascending=False)
    out = Path("data/out/selling"); out.mkdir(parents=True, exist_ok=True)
    tr.to_csv(out / "train.csv", index=False)
    print("\nTRAIN (all 16, ranked):"); print(tr.drop(columns=["exits"]).to_string(index=False))

    top = tr[tr["n"] >= 100].head(3)["variant"].tolist()
    val = pd.DataFrame([stats(n, window(trades_by[n], p.splits["validation"]), p.capital, share_by[n]) for n in top])
    val.to_csv(out / "validation_top3.csv", index=False)
    print("\nVALIDATION (top 3 by train, rank order):"); print(val.to_string(index=False))
    c = val.iloc[0]
    ok = c["n"] > 0 and c["exp_r"] > 0 and c["ci90_lo"] > 0
    print(f"\nCandidate {c['variant']}: {'CONFIRMED' if ok else 'NOT CONFIRMED'} on validation")


if __name__ == "__main__":
    main()
