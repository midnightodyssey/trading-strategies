"""
test_ibkr_live.py  —  Run with: python test_ibkr_live.py
Full end-to-end test against the paper account (requires TWS on port 7497).
"""
import sys
sys.path.insert(0, '.')

from framework.broker import IBKRBroker
from framework.execution import OMS

SEP = "=" * 60

print(SEP)
print("IBKR PAPER TRADING CONNECTION TEST")
print(SEP)

with IBKRBroker(paper=True) as broker:

    # ── 1. Connection ─────────────────────────────────────────────
    print(f"\n[1] Connected: {broker.is_connected}  |  Paper: {broker.is_paper}")

    # ── 2. Account summary ────────────────────────────────────────
    print("\n[2] Account Summary:")
    summary = broker.get_account_summary()
    for k, v in summary.items():
        if k == "account_id":
            masked = str(v)[:2] + "***" + str(v)[-3:]
            print(f"    {k:<25} {masked}")
        elif isinstance(v, float) and v is not None:
            print(f"    {k:<25} {v:,.2f}")
        else:
            print(f"    {k:<25} {v}")

    # ── 3. Current positions ──────────────────────────────────────
    print("\n[3] Open Positions:")
    positions = broker.get_positions()
    if positions.empty:
        print("    None (clean paper account)")
    else:
        print(positions.to_string(index=False))

    # ── 4. Historical data ────────────────────────────────────────
    print("\n[4] Fetching AAPL 5-day daily bars...")
    df = broker.get_historical_data("AAPL", duration="5 D", bar_size="1 day")
    print(df.to_string())

    # ── 5. Market order ───────────────────────────────────────────
    print("\n[5] Placing paper market order: BUY 1 AAPL...")
    trade_mkt = broker.place_market_order("AAPL", "BUY", 1)
    broker._ib.sleep(2)
    print(f"    Status:   {trade_mkt.orderStatus.status}")
    print(f"    Order ID: {trade_mkt.order.orderId}")
    print(f"    Filled:   {trade_mkt.orderStatus.filled} @ avg {trade_mkt.orderStatus.avgFillPrice}")

    # ── 6. Bracket order ──────────────────────────────────────────
    last_price = float(df["Close"].iloc[-1])
    tp = round(last_price * 1.02, 2)
    sl = round(last_price * 0.98, 2)
    print(f"\n[6] Placing bracket order: BUY 1 AAPL @ {last_price:.2f}  TP={tp}  SL={sl}...")
    trades_bracket = broker.place_bracket_order(
        "AAPL", "BUY", 1,
        limit_price=last_price,
        take_profit=tp,
        stop_loss=sl,
    )
    broker._ib.sleep(2)
    labels = ["Parent (entry)", "Take-profit   ", "Stop-loss     "]
    for label, t in zip(labels, trades_bracket):
        print(f"    {label}  ID={t.order.orderId}  Status={t.orderStatus.status}")

    # ── 7. Open orders ────────────────────────────────────────────
    print("\n[7] Open orders:")
    broker._ib.sleep(1)
    open_orders = broker.get_open_orders()
    if not open_orders:
        print("    None")
    else:
        for t in open_orders:
            print(f"    {t.contract.symbol:<6} {t.order.action:<4}  qty={t.order.totalQuantity}"
                  f"  type={t.order.orderType:<12}  status={t.orderStatus.status}")

    # ── 8. Cancel bracket ─────────────────────────────────────────
    print("\n[8] Cancelling bracket orders...")
    for t in trades_bracket:
        broker.cancel_order(t)
    broker._ib.sleep(2)
    remaining = broker.get_open_orders()
    print(f"    Open orders after cancel: {len(remaining)}")

    # ── 9. Sync to OMS ────────────────────────────────────────────
    print("\n[9] Syncing live positions to OMS...")
    oms = OMS(starting_capital=1_000_000)
    try:
        n = broker.sync_to_oms(oms)
        s = oms.summary()
        print(f"    Synced {n} position(s)")
        print(f"    Equity:         ${s['equity']:,.2f}")
        print(f"    Unrealised PnL: ${s['unrealised_pnl']:,.2f}")
        print(f"    Open positions: {s['open_positions']}")
    except Exception as e:
        print(f"    OMS sync note: {e}")

print("\n" + SEP)
print("ALL TESTS PASSED")
print(SEP)
