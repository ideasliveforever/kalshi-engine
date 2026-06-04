"""
signals/engine.py - Reads tick data from the DB and computes signals.

This is the analytical layer that sits on top of the raw data logger.
Run this any time to get the latest signal state across all your markets.

Usage:
    python -m signals.engine                    # print signal summary
    from signals.engine import get_signals      # use in a notebook
"""

import pandas as pd
import sqlite3
from config import DB_PATH, ZSCORE_WINDOW, IMBALANCE_WINDOW, SIGNAL_THRESHOLD


def load_ticks(ticker, hours_back=48):
    """
    Loads the most recent tick rows for a given ticker.
    hours_back=48 means "give me the last 48 hours of data".

    Returns a DataFrame with all tick columns.
    """
    conn = sqlite3.connect(DB_PATH)

    cutoff_ts = int(__import__("time").time()) - (hours_back * 3600)

    df = pd.read_sql_query("""
        SELECT *
        FROM ticks
        WHERE ticker = ?
          AND timestamp >= ?
        ORDER BY timestamp ASC
    """, conn, params=(ticker, cutoff_ts))

    conn.close()

    if df.empty:
        return df

    df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df = df.set_index("datetime")
    return df


def compute_signals(df):
    """
    Takes a tick DataFrame and adds all signal columns.

    Signals computed:
      price_z       - z-score of mid_price (your original signal, now on ticks)
      spread_z      - is the spread unusually wide right now?
      imbalance_z   - is order book imbalance unusually high/low?
      momentum_1h   - price change over the last ~60 ticks (roughly 1 hour)
      signal_flag   - human-readable summary of what's notable right now
    """
    if df.empty or len(df) < ZSCORE_WINDOW:
        return df

    w  = ZSCORE_WINDOW
    wi = IMBALANCE_WINDOW

    # ── 1. Price z-score (your existing signal, now on tick data) ────────────
    df["price_mean"] = df["mid_price"].rolling(window=w).mean()
    df["price_std"]  = df["mid_price"].rolling(window=w).std()
    df["price_z"]    = (df["mid_price"] - df["price_mean"]) / df["price_std"].replace(0, float("nan"))

    # ── 2. Spread z-score ────────────────────────────────────────────────────
    # Wide spreads signal uncertainty or thin liquidity.
    # Narrow spreads signal consensus or high liquidity.
    df["spread_mean"] = df["spread"].rolling(window=w).mean()
    df["spread_std"]  = df["spread"].rolling(window=w).std()
    df["spread_z"]    = (df["spread"] - df["spread_mean"]) / df["spread_std"].replace(0, float("nan"))

    # ── 3. Imbalance z-score ─────────────────────────────────────────────────
    # Persistent high imbalance = sustained buying or selling pressure.
    # Mean-reversion: extreme imbalance often precedes price correction.
    df["imbal_mean"] = df["imbalance"].rolling(window=wi).mean()
    df["imbal_std"]  = df["imbalance"].rolling(window=wi).std()
    df["imbalance_z"] = (df["imbalance"] - df["imbal_mean"]) / df["imbal_std"].replace(0, float("nan"))

    # ── 4. Short-term momentum ───────────────────────────────────────────────
    # How much has the mid price moved in the last ~60 ticks?
    # With 60s polling, 60 ticks ≈ 1 hour.
    df["momentum_1h"] = df["mid_price"].diff(periods=60)
    df["momentum_pct"] = df["mid_price"].pct_change(periods=60) * 100   # as percentage

    # ── 5. Volume delta ───────────────────────────────────────────────────────
    # How fast is volume accumulating? Surge = news/event impact.
    df["volume_delta"] = df["volume"].diff(periods=10)    # new contracts in last 10 ticks
    df["vol_delta_z"]  = (
        (df["volume_delta"] - df["volume_delta"].rolling(w).mean())
        / df["volume_delta"].rolling(w).std().replace(0, float("nan"))
    )

    # ── 6. Composite signal flag ─────────────────────────────────────────────
    # Simple rule-based flag. You'll replace this with a Bayesian model in Module 2.
    # For now it just tells you what's worth looking at.
    def flag_row(row):
        flags = []
        t = SIGNAL_THRESHOLD
        pz = row.get("price_z")
        sz = row.get("spread_z")
        iz = row.get("imbalance_z")
        vz = row.get("vol_delta_z")

        if pd.notna(pz):
            if pz >  t: flags.append(f"PRICE_HIGH z={pz:.1f}")
            if pz < -t: flags.append(f"PRICE_LOW  z={pz:.1f}")
        if pd.notna(sz) and sz > t:
            flags.append(f"SPREAD_WIDE z={sz:.1f}")
        if pd.notna(iz):
            if iz >  t: flags.append(f"IMBAL_BUY  z={iz:.1f}")
            if iz < -t: flags.append(f"IMBAL_SELL z={iz:.1f}")
        if pd.notna(vz) and vz > t:
            flags.append(f"VOL_SURGE  z={vz:.1f}")

        return " | ".join(flags) if flags else "—"

    df["signal_flag"] = df.apply(flag_row, axis=1)

    return df


def get_signals(hours_back=24):
    """
    Returns a dict of { ticker -> DataFrame } with all signals computed.
    Use this in your notebooks: from signals.engine import get_signals
    """
    conn = sqlite3.connect(DB_PATH)
    tickers = pd.read_sql_query(
        "SELECT DISTINCT ticker FROM ticks", conn
    )["ticker"].tolist()
    conn.close()

    results = {}
    for ticker in tickers:
        df = load_ticks(ticker, hours_back=hours_back)
        if not df.empty:
            results[ticker] = compute_signals(df)

    return results


def print_summary():
    """
    Prints a clean signal summary for all tracked markets.
    Run this to see what's interesting right now.
    """
    signals = get_signals(hours_back=48)

    if not signals:
        print("No tick data found. Has the logger been running? Check data/kalshi_ticks.db")
        return

    print("\n" + "=" * 65)
    print("  KALSHI SIGNAL SUMMARY")
    print("=" * 65)

    for ticker, df in signals.items():
        if df.empty:
            continue

        latest = df.iloc[-1]
        n_ticks = len(df)

        print(f"\n{ticker}  ({n_ticks} ticks in last 48h)")
        print(f"  Mid price:    {latest.get('mid_price', 'N/A'):.1f}¢")
        print(f"  Spread:       {latest.get('spread', 'N/A'):.1f}¢")
        print(f"  Price z:      {latest.get('price_z', float('nan')):.2f}")
        print(f"  Spread z:     {latest.get('spread_z', float('nan')):.2f}")
        print(f"  Imbalance z:  {latest.get('imbalance_z', float('nan')):.2f}")
        print(f"  Momentum 1h:  {latest.get('momentum_pct', float('nan')):.1f}%")

        # Show any active flags in last 10 ticks
        recent_flags = df["signal_flag"].tail(10)
        active = recent_flags[recent_flags != "—"]
        if not active.empty:
            print(f"  ⚡ Recent signals:")
            for ts, flag in active.items():
                print(f"     {ts.strftime('%H:%M')}  {flag}")
        else:
            print(f"  No signals above threshold in last 10 ticks")

    print("\n" + "=" * 65)


if __name__ == "__main__":
    print_summary()
