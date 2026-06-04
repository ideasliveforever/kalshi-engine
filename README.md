# Kalshi Alpha Engine

Prediction market microstructure analysis built on the Kalshi REST API.

## Project structure

```
kalshi_engine/
├── config.py              ← Edit this: add your API key and markets to track
├── database.py            ← SQLite schema (run once to set up)
├── logger.py              ← Passive tick collector — leave this running
├── fetch_history.py       ← Pull + store historical daily candles
├── signals/
│   └── engine.py          ← Reads DB, computes all signals
├── notebooks/
│   └── analysis_starter.py ← Weekly analysis workflow
├── data/                  ← DB + CSVs + charts (auto-created)
└── logs/                  ← Logger output (auto-created)
```

## Setup

```bash
pip install requests pandas matplotlib
```

Edit `config.py`:
- Add your Kalshi API key
- Add markets you want to track (see comments in file for how to find tickers)

## Daily workflow

**Step 1: Start the logger (run once, leave it running)**
```bash
python logger.py
```
This collects one tick per minute per market. Run it in a background terminal.
On Mac/Linux to keep it running after you close the terminal:
```bash
nohup python logger.py > logs/nohup.log 2>&1 &
```

**Step 2: Pull historical candles (run once per market, re-run weekly)**
```bash
python fetch_history.py
```

**Step 3: Check signals any time**
```bash
python -m signals.engine
```

**Step 4: Deep analysis (weekly, in Jupyter or as a script)**
```bash
cd notebooks
python analysis_starter.py
```

## Signals computed

| Signal | What it means |
|---|---|
| `price_z` | Z-score of mid price vs rolling mean. Your original signal. |
| `spread_z` | Is the bid-ask spread wider/narrower than usual? Wide = uncertainty. |
| `imbalance` | Buying vs selling pressure proxy. +1 = all bids, -1 = all asks. |
| `imbalance_z` | Imbalance relative to its recent baseline. |
| `momentum_1h` | Price change over last ~60 ticks (≈1 hour). |
| `vol_delta_z` | Volume accumulation rate vs baseline. Spike = news impact. |
| `signal_flag` | Human-readable summary of any signals above threshold. |

## What to look for

- **Wide spread + price z-score spike**: market is being repriced, possibly on news
- **High imbalance + flat price**: sustained buying/selling pressure not yet reflected in price — potential leading indicator
- **Volume surge**: something is happening — check the news
- **Spread z < -1.5**: unusually narrow spread — either high liquidity or market is very settled on a probability

## Next steps (Module 2)

Add `forecasts/` folder with:
- `prior_builder.py` — base rates from historical resolutions
- `bayesian_updater.py` — update priors with news/data
- `edge_tracker.py` — log your P vs market P at each resolution
