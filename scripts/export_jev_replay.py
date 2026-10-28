"""Export baseline-A traded candidates (train + validation) with word-only Jev states and outcomes."""
import dataclasses
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lightning.backtest import run
from lightning.calendar import ExpiryCalendar
from lightning.config import load_params
from lightning.data import store
from lightning.features import build_features
from lightning.live.jev import build_state, has_numbers
from lightning.pricing import RealPricer
from lightning.signals import BAR

IST = "Asia/Kolkata"


def main():
    d = ROOT / "data" / "NIFTY"
    p = dataclasses.replace(load_params(), drawdown_halt_pct=1e9)
    raw = store.load_intraday(d / "spot_15m.csv")
    cal = ExpiryCalendar(store.calendar_days(raw), p.expiry_schedule)
    spot, _ = store.clean_intraday(raw)
    opt = store.load_options(d)
    f = build_features(store.attach_option_volume(spot, opt), store.load_daily(d / "spot_daily.csv"), p)
    trades, _ = run(f, p, RealPricer(f, opt), cal)
    pos = {t: k for k, t in enumerate(f.index)}
    rows = []
    for _, t in trades.iterrows():
        e = t["entry_ts"]
        split = next((n for n in ("train", "validation") if pd.Timestamp(p.splits[n]["from"], tz=IST) <= e <
                      pd.Timestamp(p.splits[n]["to"], tz=IST) + pd.Timedelta(days=1)), None)
        if split is None:
            continue  # test split stays sealed
        i = pos[e] - 1
        state = build_state(f, i, int(t["side"]))
        assert not has_numbers(state)
        rows.append({"id": f"A|{(f.index[i] + BAR).isoformat()}", "split": split, "side": int(t["side"]),
                     "decision_ts": (f.index[i] + BAR).isoformat(), "state_json": json.dumps(state), "net_r": round(t["net_r"], 6)})
    out = ROOT / "research" / "jev_replay" / "candidates.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    df = pd.DataFrame(rows)
    print(f"wrote {len(df)} candidates to {out}:", df.groupby("split").size().to_dict())


if __name__ == "__main__":
    main()
