from __future__ import annotations


def round_trip_costs(qty: float, buy_px: float, sell_px: float, c: dict) -> float:
    """INR costs for one buy and one sell of an option position (buyer)."""
    buy_t, sell_t = qty * buy_px, qty * sell_px
    brokerage = 2 * c["brokerage_per_order"]
    stt = c["stt_sell_pct"] * sell_t
    txn = c["exchange_txn_pct"] * (buy_t + sell_t)
    sebi = c["sebi_pct"] * (buy_t + sell_t)
    stamp = c["stamp_buy_pct"] * buy_t
    gst = c["gst_pct"] * (brokerage + txn + sebi)
    return brokerage + stt + txn + sebi + stamp + gst
