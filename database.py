"""
database.py - Creates and manages the SQLite database.

Two tables:
  ticks       - one row per API poll (raw market state at that moment)
  candlesticks - daily OHLC data you pull on demand (like your existing code)

Run this file once to create the DB: python database.py
"""

import sqlite3
import os
from config import DB_PATH


def get_connection():
    """Returns a connection to the SQLite DB. Creates the file if it doesn't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return sqlite3.connect(DB_PATH)


def create_tables():
    """Creates all tables. Safe to run multiple times (IF NOT EXISTS)."""
    conn = get_connection()
    c = conn.cursor()

    # ── ticks table ───────────────────────────────────────────────────────────
    # One row per poll. This is your core dataset for microstructure analysis.
    # yes_bid/yes_ask: what you pay to buy YES / what you receive selling YES (cents)
    # no_bid/no_ask:   same for NO side
    # imbalance: computed on insert = (bid_depth - ask_depth) / (bid_depth + ask_depth)
    #            ranges -1 to +1. Positive = more buying pressure on YES side.
    c.execute("""
        CREATE TABLE IF NOT EXISTS ticks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL,
            series          TEXT    NOT NULL,
            category        TEXT    NOT NULL,
            timestamp       INTEGER NOT NULL,   -- unix timestamp (seconds)

            yes_bid         REAL,               -- cents (0-100)
            yes_ask         REAL,               -- cents (0-100)
            no_bid          REAL,
            no_ask          REAL,

            spread          REAL,               -- yes_ask - yes_bid
            imbalance       REAL,               -- (bid_depth - ask_depth) / total depth
            mid_price       REAL,               -- (yes_bid + yes_ask) / 2

            volume          INTEGER,            -- total contracts traded (cumulative)
            open_interest   INTEGER,            -- open contracts outstanding
            last_price      REAL                -- last traded price
        )
    """)

    # ── candlesticks table ────────────────────────────────────────────────────
    # Daily OHLC — same structure as your existing code, now stored persistently.
    # period_interval: minutes per candle (1440 = daily)
    c.execute("""
        CREATE TABLE IF NOT EXISTS candlesticks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker          TEXT    NOT NULL,
            series          TEXT    NOT NULL,
            end_period_ts   INTEGER NOT NULL,

            open_price      REAL,
            high_price      REAL,
            low_price       REAL,
            close_price     REAL,
            volume          INTEGER,

            UNIQUE(ticker, end_period_ts)       -- prevent duplicate candles
        )
    """)

    # ── index for fast lookups ────────────────────────────────────────────────
    # When you query "give me all AAPL ticks in the last hour" this makes it fast.
    c.execute("CREATE INDEX IF NOT EXISTS idx_ticks_ticker_ts ON ticks (ticker, timestamp)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_candles_ticker ON candlesticks (ticker, end_period_ts)")

    conn.commit()
    conn.close()
    print(f"Database ready at: {DB_PATH}")


def insert_tick(ticker, series, category, market_data):
    """
    Inserts one tick row. Called by the logger every POLL_INTERVAL_SECONDS.

    market_data is the raw dict from the Kalshi /markets/{ticker} endpoint.
    We extract what we need and compute spread/imbalance/mid here.
    """
    conn = get_connection()
    c = conn.cursor()

    import time

    # Pull raw values — Kalshi returns prices in cents (0-100)
    yes_bid = market_data.get("yes_bid")        # e.g. 62
    yes_ask = market_data.get("yes_ask")        # e.g. 64
    no_bid  = market_data.get("no_bid")
    no_ask  = market_data.get("no_ask")

    # Kalshi also returns order book depth separately sometimes,
    # but best proxy from REST is just bid vs ask as a simple imbalance.
    # We use prices here: if yes_bid is high relative to mid, buying pressure is high.
    spread    = None
    imbalance = None
    mid_price = None

    if yes_bid is not None and yes_ask is not None:
        spread    = yes_ask - yes_bid
        mid_price = (yes_bid + yes_ask) / 2

        # Simple price-based imbalance proxy.
        # True depth-based imbalance needs the orderbook endpoint (websocket/FIX).
        # For now: how far is yes_bid from the midpoint?
        # Positive = bid close to ask = buying pressure. Negative = wide on bid side.
        if spread > 0:
            imbalance = (yes_bid - (mid_price - spread / 2)) / spread
        else:
            imbalance = 0.0

    c.execute("""
        INSERT INTO ticks
            (ticker, series, category, timestamp,
             yes_bid, yes_ask, no_bid, no_ask,
             spread, imbalance, mid_price,
             volume, open_interest, last_price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ticker, series, category, int(time.time()),
        yes_bid, yes_ask, no_bid, no_ask,
        spread, imbalance, mid_price,
        market_data.get("volume"),
        market_data.get("open_interest"),
        market_data.get("last_price"),
    ))

    conn.commit()
    conn.close()


def insert_candlestick(ticker, series, candle):
    """
    Inserts one daily candle. Called by fetch_history.py.
    Uses INSERT OR IGNORE to avoid duplicates on re-fetch.
    """
    conn = get_connection()
    c = conn.cursor()

    close_raw = candle.get("yes_ask", {})
    open_raw  = candle.get("yes_bid", {})

    # Kalshi returns nested dicts for OHLC inside yes_ask/yes_bid
    close_price = float(close_raw.get("close_dollars", 0)) if isinstance(close_raw, dict) else None
    open_price  = float(open_raw.get("open_dollars",  0)) if isinstance(open_raw,  dict) else None
    high_price  = float(close_raw.get("high_dollars",  0)) if isinstance(close_raw, dict) else None
    low_price   = float(close_raw.get("low_dollars",   0)) if isinstance(close_raw, dict) else None

    c.execute("""
        INSERT OR IGNORE INTO candlesticks
            (ticker, series, end_period_ts, open_price, high_price, low_price, close_price, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        ticker, series,
        candle.get("end_period_ts"),
        open_price, high_price, low_price, close_price,
        candle.get("volume"),
    ))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_tables()
