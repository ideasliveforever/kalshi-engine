"""
fetch_history.py - Pulls historical daily candles for all tracked markets.

This is your existing script, refactored to:
  - Loop over all markets in config.py (not just one)
  - Store results in SQLite (not just a CSV)
  - Still produce the same z-score chart you had — now for any market

Usage:
    python fetch_history.py                        # fetch all markets
    python fetch_history.py KXMAYORLA-26-KBAS      # fetch one specific ticker
"""

import requests
import pandas as pd
import matplotlib.pyplot as plt
import sys
import time
from datetime import datetime

from config import API_KEY, BASE_URL, MARKETS
from database import create_tables, insert_candlestick, get_connection


HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def fetch_candles(ticker, series, period_interval=1440):
    """
    Pulls all daily candlestick data for a market from its open date until now.
    period_interval=1440 = daily candles (minutes in a day).

    Returns a list of raw candle dicts from the API.
    """
    # Step 1: get market open time (same logic as your original code)
    market_url = f"{BASE_URL}/markets/{ticker}"
    r = requests.get(market_url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    market = r.json()["market"]

    open_time = market["open_time"]
    open_dt   = datetime.fromisoformat(open_time.replace("Z", "+00:00"))
    start_ts  = int(open_dt.timestamp())
    end_ts    = int(time.time())

    print(f"  {ticker}: fetching candles from {open_dt.strftime('%Y-%m-%d')} to now")

    # Step 2: fetch candlesticks
    url = f"{BASE_URL}/series/{series}/markets/{ticker}/candlesticks"
    params = {
        "start_ts":        start_ts,
        "end_ts":          end_ts,
        "period_interval": period_interval,
    }
    r = requests.get(url, headers=HEADERS, params=params, timeout=10)
    r.raise_for_status()

    candles = r.json().get("candlesticks", [])
    print(f"  {ticker}: got {len(candles)} candles")
    return candles, market


def candles_to_dataframe(candles):
    """
    Converts raw Kalshi candlestick list to a clean DataFrame.
    Adds rolling mean, std, z-score, spread columns.
    """
    df = pd.DataFrame(candles)
    if df.empty:
        return df

    df["date"] = pd.to_datetime(df["end_period_ts"], unit="s")
    df = df.set_index("date")

    # Close price from yes_ask nested dict
    df["close_price"] = df["yes_ask"].apply(
        lambda x: float(x["close_dollars"]) if isinstance(x, dict) else None
    )
    df["open_price"] = df["yes_bid"].apply(
        lambda x: float(x["open_dollars"]) if isinstance(x, dict) else None
    )

    # Spread: difference between ask and bid at close
    # This is a crude daily spread proxy — tick logger gives you real-time spread
    df["daily_spread"] = df.apply(
        lambda row: (
            float(row["yes_ask"]["close_dollars"]) - float(row["yes_bid"]["close_dollars"])
            if isinstance(row["yes_ask"], dict) and isinstance(row["yes_bid"], dict)
            else None
        ),
        axis=1,
    )

    # ── Signals (your existing z-score, now with extras) ──────────────────────
    window = 7

    df["rolling_mean"] = df["close_price"].rolling(window=window).mean()
    df["rolling_std"]  = df["close_price"].rolling(window=window).std()
    df["z_score"]      = (df["close_price"] - df["rolling_mean"]) / df["rolling_std"]

    # Price momentum: close vs close 3 days ago (normalized)
    df["momentum_3d"] = df["close_price"].pct_change(periods=3)

    # Spread z-score: is today's spread unusually wide or narrow?
    df["spread_mean"] = df["daily_spread"].rolling(window=window).mean()
    df["spread_std"]  = df["daily_spread"].rolling(window=window).std()
    df["spread_z"]    = (df["daily_spread"] - df["spread_mean"]) / df["spread_std"]

    return df


def plot_market(df, ticker):
    """
    Your original 2-panel plot, extended to 3 panels with spread z-score.
    """
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 8))
    fig.suptitle(ticker, fontsize=13, fontweight="bold")

    # Panel 1: price
    df[["close_price", "rolling_mean"]].plot(ax=ax1, title="Close price vs rolling mean")
    ax1.set_ylabel("Price (¢)")

    # Panel 2: z-score
    df["z_score"].plot(ax=ax2, title="Price z-score", color="steelblue")
    ax2.axhline(y= 1.5, color="red",   linestyle="--", alpha=0.5, label="+1.5")
    ax2.axhline(y=-1.5, color="green", linestyle="--", alpha=0.5, label="-1.5")
    ax2.legend(fontsize=8)

    # Panel 3: spread z-score (new)
    df["spread_z"].plot(ax=ax3, title="Spread z-score (wide = red)", color="darkorange")
    ax3.axhline(y= 1.5, color="red",   linestyle="--", alpha=0.5)
    ax3.axhline(y=-1.5, color="green", linestyle="--", alpha=0.5)
    ax3.set_ylabel("Spread z")

    plt.tight_layout()
    plt.savefig(f"data/{ticker.replace('/', '_')}_chart.png", dpi=120)
    plt.show()
    print(f"  Chart saved to data/{ticker}_chart.png")


def run(tickers_filter=None):
    """
    Main function. Fetches candles for all markets (or a filtered subset),
    stores in DB, prints tail, and plots.
    """
    create_tables()

    markets = MARKETS
    if tickers_filter:
        markets = [m for m in MARKETS if m["ticker"] in tickers_filter]
        if not markets:
            print(f"Ticker '{tickers_filter}' not found in config.py MARKETS list.")
            return

    for market_cfg in markets:
        ticker = market_cfg["ticker"]
        series = market_cfg["series"]

        print(f"\nFetching: {ticker}")
        try:
            candles, _ = fetch_candles(ticker, series)
        except Exception as e:
            print(f"  ERROR fetching {ticker}: {e}")
            continue

        # Store in DB
        for candle in candles:
            insert_candlestick(ticker, series, candle)
        print(f"  Stored {len(candles)} candles in DB")

        # Build DataFrame and compute signals
        df = candles_to_dataframe(candles)
        if df.empty:
            print(f"  No data to display for {ticker}")
            continue

        # Print tail (same as your original)
        print(f"\n  Last 10 rows for {ticker}:")
        print(df[["close_price", "rolling_mean", "z_score", "daily_spread", "spread_z"]].tail(10).to_string())

        # Plot
        plot_market(df, ticker)

        # Also save CSV per market (keeps your original workflow)
        csv_path = f"data/{ticker.replace('/', '_')}_history.csv"
        df.to_csv(csv_path)
        print(f"  CSV saved: {csv_path}")


if __name__ == "__main__":
    filter_ticker = sys.argv[1] if len(sys.argv) > 1 else None
    run([filter_ticker] if filter_ticker else None)
