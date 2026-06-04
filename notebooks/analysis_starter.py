"""
notebooks/analysis_starter.py
Run as a script OR copy cells into a Jupyter notebook.

This is your weekly analysis workflow:
  1. Load tick data from DB
  2. Compute signals
  3. Plot everything
  4. Look for patterns

When you start Module 2 (Bayesian), this is where you'll add your
probability estimates and compare them to market prices.
"""

# ── Imports ───────────────────────────────────────────────────────────────────
import sys
sys.path.append("..")   # so imports work when run from notebooks/ folder

import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from config import DB_PATH
from signals.engine import load_ticks, compute_signals, get_signals


# ── 1. Load data ──────────────────────────────────────────────────────────────
# Change hours_back to look at more or less history
TICKER     = "KXMAYORLA-26-KBAS"   # change to whichever market you want to analyze
HOURS_BACK = 72                     # last 72 hours of ticks

df_raw = load_ticks(TICKER, hours_back=HOURS_BACK)
print(f"Loaded {len(df_raw)} ticks for {TICKER}")

if df_raw.empty:
    print("No data yet — make sure logger.py has been running.")
else:
    # ── 2. Compute signals ────────────────────────────────────────────────────
    df = compute_signals(df_raw.copy())
    print(f"Computed signals. Columns: {list(df.columns)}")

    # ── 3. Latest snapshot ────────────────────────────────────────────────────
    latest = df.iloc[-1]
    print("\n── LATEST SNAPSHOT ──────────────────────────────")
    print(f"  Time:         {df.index[-1].strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Mid price:    {latest['mid_price']:.1f}¢")
    print(f"  Spread:       {latest['spread']:.1f}¢")
    print(f"  Price z:      {latest['price_z']:.2f}")
    print(f"  Spread z:     {latest['spread_z']:.2f}")
    print(f"  Imbalance z:  {latest['imbalance_z']:.2f}")
    print(f"  Momentum 1h:  {latest['momentum_pct']:.1f}%")
    print(f"  Signal:       {latest['signal_flag']}")

    # ── 4. Plot ───────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(13, 10))
    fig.suptitle(f"{TICKER}  —  last {HOURS_BACK}h", fontsize=12, fontweight="bold")
    gs = gridspec.GridSpec(4, 1, figure=fig, hspace=0.45)

    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])
    ax3 = fig.add_subplot(gs[2])
    ax4 = fig.add_subplot(gs[3])

    # Panel 1: Mid price + rolling mean
    ax1.plot(df.index, df["mid_price"],   label="Mid price", linewidth=1.2)
    ax1.plot(df.index, df["price_mean"],  label="Rolling mean", linestyle="--", linewidth=1)
    ax1.set_ylabel("Price (¢)")
    ax1.set_title("Mid price")
    ax1.legend(fontsize=8)
    ax1.grid(alpha=0.3)

    # Panel 2: Price z-score (your original)
    ax2.plot(df.index, df["price_z"], color="steelblue", linewidth=1)
    ax2.axhline(y= 1.5, color="red",   linestyle="--", alpha=0.6, linewidth=0.8)
    ax2.axhline(y=-1.5, color="green", linestyle="--", alpha=0.6, linewidth=0.8)
    ax2.axhline(y= 0,   color="gray",  linestyle="-",  alpha=0.3, linewidth=0.5)
    ax2.set_ylabel("z-score")
    ax2.set_title("Price z-score")
    ax2.grid(alpha=0.3)

    # Panel 3: Spread (new)
    ax3.plot(df.index, df["spread"],  color="darkorange", linewidth=1, label="Spread")
    ax3_twin = ax3.twinx()
    ax3_twin.plot(df.index, df["spread_z"], color="coral", linewidth=0.8,
                  linestyle="--", alpha=0.7, label="Spread z")
    ax3.set_ylabel("Spread (¢)")
    ax3_twin.set_ylabel("Spread z", color="coral")
    ax3.set_title("Bid-ask spread")
    ax3.grid(alpha=0.3)

    # Panel 4: Imbalance + volume delta
    ax4.plot(df.index, df["imbalance"], color="purple", linewidth=1, label="Imbalance")
    ax4.axhline(y= 0.5, color="red",   linestyle="--", alpha=0.5, linewidth=0.8)
    ax4.axhline(y=-0.5, color="green", linestyle="--", alpha=0.5, linewidth=0.8)
    ax4.axhline(y= 0,   color="gray",  linestyle="-",  alpha=0.3, linewidth=0.5)
    ax4.set_ylabel("Imbalance")
    ax4.set_title("Order book imbalance  (positive = buying pressure)")
    ax4.grid(alpha=0.3)

    # Highlight active signal rows with a vertical line on all panels
    signal_rows = df[df["signal_flag"] != "—"]
    for ts in signal_rows.index:
        for ax in [ax1, ax2, ax3, ax4]:
            ax.axvline(x=ts, color="gold", alpha=0.25, linewidth=0.8)

    plt.savefig(f"../data/{TICKER.replace('/', '_')}_tick_analysis.png", dpi=130, bbox_inches="tight")
    plt.show()
    print(f"\nChart saved to data/{TICKER}_tick_analysis.png")

    # ── 5. Signal summary table ───────────────────────────────────────────────
    print("\n── ACTIVE SIGNALS (last 100 ticks) ──────────────────")
    active = df["signal_flag"].tail(100)
    active = active[active != "—"]
    if active.empty:
        print("  No signals above threshold in last 100 ticks.")
    else:
        for ts, flag in active.items():
            print(f"  {ts.strftime('%Y-%m-%d %H:%M')}  {flag}")

    # ── 6. Basic stats ────────────────────────────────────────────────────────
    print("\n── DESCRIPTIVE STATS ────────────────────────────────")
    print(df[["mid_price", "spread", "imbalance", "price_z"]].describe().round(3).to_string())
