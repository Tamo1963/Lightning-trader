"""Check the two live inputs of covered-call shadow mode (run once with your credentials):
  python scripts/probe_cc_shadow.py"""
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from lightning.data.dhan import DhanClient
from lightning.live.covered_call import DhanCCSource

cfg = yaml.safe_load((ROOT / "config" / "shadow_cc.yaml").read_text())
stocks = yaml.safe_load((ROOT / "config" / "stocks.yaml").read_text())["stocks"]
c = DhanClient(os.environ.get("DHAN_ACCESS_TOKEN") or sys.exit("set DHAN_ACCESS_TOKEN"),
               client_id=os.environ.get("DHAN_CLIENT_ID") or sys.exit("set DHAN_CLIENT_ID"))
sym = cfg["symbols"][0]
for seg in ("NSE_EQ", "NSE_FNO", "IDX_I"):
    try:
        print(f"option-chain expiry list, segment {seg}:", c.expiry_list(stocks[sym]["security_id"], seg)[:4])
    except Exception as e:  # noqa: BLE001
        print(f"option-chain expiry list, segment {seg}: FAILED {str(e)[-90:]}")
path = ROOT / cfg["scrip_master"]
if not path.exists():
    sys.exit(f"put the Dhan scrip master CSV at {path}")
src = DhanCCSource(c, path, {sym: stocks[sym]["security_id"]}, cfg["option_chain_segment"])
exps = src.futures_expiries(sym)
print(f"{sym} futures expiries from scrip master:", exps[:3])
print("futures quote:", src.fut_quote(sym, exps[0]))
calls = src.calls(sym, exps[0])
print(f"calls in chain: {len(calls)}; sample:", list(calls.items())[:2])
