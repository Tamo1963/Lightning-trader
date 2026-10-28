"""Download NSE F&O bhavcopies and keep Nifty options of the two nearest monthly expiries.
  python scripts/fetch_nse_bhavcopy.py --start 2016-01-01 --end 2025-09-30
Writes data/nse/nifty_monthly/{YYYYMMDD}.csv (resumable; NSE holidays are skipped)."""
import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lightning.data.nse import NSEClient, keep_near_monthlies, parse


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--start", required=True); a.add_argument("--end", required=True)
    args = a.parse_args()
    out = ROOT / "data" / "nse" / "nifty_monthly"; out.mkdir(parents=True, exist_ok=True)
    done = {p.stem for p in out.glob("*.csv")}
    missing = out / "_no_file.txt"
    skip = set(missing.read_text().split()) if missing.exists() else set()
    c = NSEClient()
    n_ok = n_none = 0
    for d in pd.bdate_range(args.start, args.end).date:
        key = f"{d:%Y%m%d}"
        if key in done or key in skip:
            continue
        try:
            raw = c.fetch(d)
        except Exception as e:  # noqa: BLE001
            print("FAILED", key, str(e)[:120], flush=True)
            continue
        if raw is None:
            with missing.open("a") as fh:
                fh.write(key + "\n")
            n_none += 1
            continue
        keep_near_monthlies(parse(raw)).to_csv(out / f"{key}.csv", index=False)
        n_ok += 1
        if n_ok % 100 == 0:
            print(f"{key}: {n_ok} files saved, {n_none} holidays", flush=True)
    print(f"done: {n_ok} saved, {n_none} no-file days")


if __name__ == "__main__":
    main()
