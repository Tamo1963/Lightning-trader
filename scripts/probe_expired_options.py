"""One-minute check: does Dhan's expired-options endpoint answer for this machine and token?
  python scripts/probe_expired_options.py      (DHAN_ACCESS_TOKEN must be set)"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lightning.data.dhan import DhanClient

c = DhanClient(os.environ.get("DHAN_ACCESS_TOKEN") or sys.exit("set DHAN_ACCESS_TOKEN"), pause_s=0.5)
print("daily endpoint:", "OK" if len(c.daily("13", "IDX_I", "INDEX", "2026-10-20", "2026-10-28")) else "empty")
for flag, strike in (("WEEK", "ATM"), ("MONTH", "ATM"), ("MONTH", "ATM+10")):
    try:
        r = c.rolling_options(13, "2026-09-01", "2026-10-01", "CALL", strike, 1, expiry_flag=flag)
        print(f"expired options {flag} {strike}: OK, {len(r)} bars")
    except Exception as e:  # noqa: BLE001
        print(f"expired options {flag} {strike}: FAILED {str(e)[-110:]}")
