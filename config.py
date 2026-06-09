from dotenv import load_dotenv
import os
"""
config.py - Central config. Edit this file to add/remove markets.
"""
load_dotenv()
API_KEY = os.getenv('KALSHI_API_KEY') 

BASE_URL = "https://external-api.kalshi.com/trade-api/v2" 

# ── Markets to track ─────────────────────────────────────────────────────────
# Format: { "ticker": "MARKET", "series": "SERIES", "category": "..." }


MARKETS = [
    {"ticker": "KXMAYORLA-26-KBAS",        "series": "KXMAYORLA",         "category": "politics"},
    {"ticker": "KXFED-26JUN-T3.50",         "series": "KXFED",             "category": "macro"},
    {"ticker": "KXCBDECISIONBRAZIL-26JUN17-C25", "series": "KXCBDECISIONBRAZIL", "category": "macro"},
    {"ticker": "KXBTC15M-26JUN091730-30",   "series": "KXBTC15M",          "category": "crypto"},
    {"ticker": "KXHIGHLAX-26JUN09-B72.5",   "series": "KXHIGHLAX",         "category": "climate"},
]

# ── Tick logger settings ──────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 60   # how often to poll (60s = 1 tick/min per market)
DB_PATH = "data/kalshi_ticks.db"
LOG_PATH = "logs/logger.log"

# ── Signal settings ───────────────────────────────────────────────────────────
ZSCORE_WINDOW = 7            # rolling window for z-score (in ticks)
IMBALANCE_WINDOW = 20        # rolling window for imbalance baseline
SIGNAL_THRESHOLD = 1.5       # z-score level flagged as notable
