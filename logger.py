"""
logger.py - Passive tick collector. Run this and leave it running.

Usage:
    python logger.py

What it does:
    Every POLL_INTERVAL_SECONDS, hits the Kalshi REST API for each market
    in your MARKETS list and writes one row to the ticks table.

    Run it in a terminal tab while you're at work. It logs to logs/logger.log
    so you can check what happened when you get back.

    To run in the background (so terminal can close):
        nohup python logger.py &        (Mac/Linux)
        pythonw logger.py               (Windows)
"""

import requests
import time
import logging
import os
import sys

from config import API_KEY, BASE_URL, MARKETS, POLL_INTERVAL_SECONDS, LOG_PATH
from database import create_tables, insert_tick


# ── Logging setup ─────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH),
        logging.StreamHandler(sys.stdout),   # also print to terminal
    ]
)
log = logging.getLogger(__name__)


# ── API client ────────────────────────────────────────────────────────────────
HEADERS = {"Authorization": f"Bearer {API_KEY}"}


def fetch_market(ticker):
    """
    Pulls current market state from Kalshi.
    Returns the market dict, or None if the request fails.
    """
    url = f"{BASE_URL}/markets/{ticker}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
        return r.json().get("market")
    except requests.exceptions.HTTPError as e:
        log.warning(f"HTTP error for {ticker}: {e}")
    except requests.exceptions.Timeout:
        log.warning(f"Timeout for {ticker}")
    except requests.exceptions.RequestException as e:
        log.warning(f"Request failed for {ticker}: {e}")
    return None


# ── Main loop ─────────────────────────────────────────────────────────────────
def run():
    log.info("=== Kalshi tick logger starting ===")
    log.info(f"Tracking {len(MARKETS)} market(s), polling every {POLL_INTERVAL_SECONDS}s")
    for m in MARKETS:
        log.info(f"  {m['ticker']} ({m['category']})")

    create_tables()   # safe to call every time — only creates if not exists

    tick_count = 0

    while True:
        poll_start = time.time()

        for market_cfg in MARKETS:
            ticker   = market_cfg["ticker"]
            series   = market_cfg["series"]
            category = market_cfg["category"]

            data = fetch_market(ticker)

            if data is None:
                log.warning(f"Skipping {ticker} this tick — no data returned")
                continue

            insert_tick(ticker, series, category, data)

            # Log a summary line so you can see what's happening at a glance
            yes_bid = data.get("yes_bid", "?")
            yes_ask = data.get("yes_ask", "?")
            vol     = data.get("volume", "?")
            log.info(f"{ticker} | bid={yes_bid}¢  ask={yes_ask}¢  vol={vol}")

        tick_count += 1
        if tick_count % 60 == 0:
            log.info(f"--- {tick_count} ticks collected so far ---")

        # Sleep for the remainder of the interval
        # (subtracts time spent fetching so drift doesn't accumulate)
        elapsed = time.time() - poll_start
        sleep_time = max(0, POLL_INTERVAL_SECONDS - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        log.info("Logger stopped by user.")
