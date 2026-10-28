"""Download NSE F&O bhavcopies and keep futures + near-strike monthly options for the hedged-futures study.
  python scripts/fetch_nse_multi.py --start 2016-01-01 --end 2025-09-30
Writes data/nse/multi/{YYYYMMDD}.csv.gz (resumable)."""
import argparse
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lightning.data.nse import NSEClient, parse_multi, slim


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--start", required=True); a.add_argument("--end", required=True)
    args = a.parse_args()
    syms = {"NIFTY", "BANKNIFTY"} | set(yaml.safe_load((ROOT / "config" / "stocks.yaml").read_text())["stocks"])
    out = ROOT / "data" / "nse" / "multi"; out.mkdir(parents=True, exist_ok=True)
    nofile = set((ROOT / "data" / "nse" / "nifty_monthly" / "_no_file.txt").read_text().split())  # known holidays
    done = {p.name[:8] for p in out.glob("*.csv.gz")}
    c = NSEClient()
    n = 0
    for d in pd.bdate_range(args.start, args.end).date:
        key = f"{d:%Y%m%d}"
        if key in done or key in nofile:
            continue
        try:
            raw = c.fetch(d)
        except Exception as e:  # noqa: BLE001
            print("FAILED", key, str(e)[:120], flush=True); continue
        if raw is None:
            continue
        slim(parse_multi(raw, syms)).to_csv(out / f"{key}.csv.gz", index=False)
        n += 1
        if n % 100 == 0:
            print(f"{key}: {n} saved", flush=True)
    print(f"done: {n} saved")


if __name__ == "__main__":
    main()
