# Intraday Analyzer

Real-time NSE stock market monitoring system that scans **1,000+ Indian equities** concurrently across multiple trading strategies and delivers automated BUY/SELL alerts via WhatsApp.

---

## Overview

The analyzer runs as a set of parallel subprocesses — one per ticker batch — that each download fresh OHLCV data every 15 minutes, apply strategy logic, and write signals to flat files and MongoDB. A Streamlit dashboard sits on top for live charting and signal review.

```
Main.py  →  spawns mod_10_20.py … mod_175_200.py  (11 parallel processes)
              └─ each process calls Analyzer() every 15 minutes
                    ├─ Download()       — yfinance bulk fetch (1m + 15m)
                    ├─ Regression()     — R² + volume + DTW smooth
                    ├─ FiveEMA()        — 5 EMA bearish confluence
                    └─ scan_breakouts() — PDH/PDL breakout + 5m confirmation
```

---

## Features

### Trading Strategies

| Strategy | Timeframe | Signal Logic |
|---|---|---|
| **Regression** | 15m | R² ≥ 0.93 + volume ratio ≥ 1.7 → `REG` signal; R² ≥ 0.85 + smooth ≤ 0.03 + vol ratio > 1.5 → `VOL` signal |
| **5 EMA** | 15m | Bearish candle above 5 EMA, two prior strong bullish candles, EMA₅ > VWAP |
| **Breakout** | 15m + 5m | Candle opens inside PDH/PDL range and closes outside → confirmed by next 5m close |
| **RegHistory** | 15m | Rolling R² momentum tracker — flags accelerating trend strength |

### Data Pipeline

- **Intervals downloaded**: `1m`, `15m`, `1h`, `4h` (resampled), `1d`
- **4h candles**: Custom-resampled from 1h data matching NSE session windows (09:15–13:14 and 13:15–15:30)
- **Candle close guard**: Strategies only run on fully closed candles — live unfinished candles are excluded
- **Timezone**: All data normalized to `Asia/Kolkata`
- **Tickers**: 11 batches of ~90 stocks each (`ticker1` … `ticker11`), covering large-cap, mid-cap, and small-cap NSE equities

### Infrastructure

- **Parallel execution**: `Main.py` spawns one subprocess per ticker batch using `subprocess.Popen`, all running simultaneously
- **Signal deduplication**: `SignalState` class prevents the same signal from firing twice in a session for the same ticker
- **WhatsApp alerts**: Twilio integration with a background queue worker — non-blocking, auto-started on first send
- **MongoDB**: Signals stored per strategy collection via `store_signal()` / `get_signals()`
- **SQLite**: Breakout data cached in `Data_Sets/breakout_data.db`
- **Logging**: Custom log levels (`BUY`, `SELL`, `CYCLE`, `THREAD`, `INVALID`, `VALID`) written to `Logs/Main.log` with color output in terminal
- **Session reset**: `reset_session()` wipes signal state and re-arms the daily data download at market open

### Dashboard (Streamlit)

Run with:
```
streamlit run Dashboard/App.py
```

| Page | Description |
|---|---|
| **Graph** | Interactive candlestick / line charts with EMA, swing zones, support/resistance, trendlines, PDH/PDL overlays. Click any candle for OHLCV detail. |
| **Signals** | Live signal table auto-refreshing every 3 seconds. Filter by ticker, signal type, or source file. |

### Utilities

| File | Purpose |
|---|---|
| `Tax.py` | Groww intraday brokerage + charges calculator (STT, GST, SEBI, stamp) |
| `P&L_Plot.py` | Plot realized P&L bar chart, cumulative curve, and daily P&L from a Groww Excel export |
| `Clean_Up.py` | Wipes `Signals/` and `Logs/` folders — run before each session |

---

## Project Structure

```
Intraday_Analyzer/
├── Main.py                      # Entry point — spawns all analyzer processes
├── Analyzer.py                  # Per-cycle logic: Download → strategies → wait
├── Clean_Up.py                  # Session cleanup utility
│
├── Strategy/
│   ├── Regression.py            # R² + volume strategy
│   ├── FiveEMA.py               # 5 EMA bearish confluence
│   └── Breakout.py              # PDH/PDL breakout with 5m confirmation
│
├── Data_Manager/
│   ├── data.py                  # yfinance download, 4h resampler, get_data()
│   └── tickers.py               # 11 ticker lists (ticker1 … ticker11)
│
├── Dependencies/
│   ├── Features/
│   │   ├── Database.py          # MongoDB signal store/fetch/clear
│   │   ├── Initializer.py       # SignalState + Daily_Data + reset_session
│   │   ├── Messages.py          # Twilio WhatsApp queue worker
│   │   ├── Tax.py               # Brokerage calculator
│   │   └── P&L_Plot.py          # P&L visualization
│   ├── Modules/
│   │   └── mod_10_20.py … mod_175_200.py   # Per-batch subprocess workers
│   └── Utils/
│       ├── Loggings.py          # Custom log levels + color formatter
│       ├── Fluctuation.py       # R² (is_fluctuation)
│       ├── Smooth.py            # DTW smooth score
│       ├── RollingSignal.py     # Rolling R² history (add_value)
│       ├── Percent.py           # Percent breakdown label
│       ├── Write.py             # Thread-safe file writer
│       ├── Unique.py            # Global SignalState instance
│       ├── Sleep.py             # wait_until_next_candle()
│       └── Angle.py / Xval.py  # Geometry helpers
│
├── Dictionary/
│   ├── Indicators/              # EMA, RSI, VWAP, Volume ratio
│   └── Structure/               # FVG, Highs/Lows, swing detection
│
├── Dashboard/
│   ├── App.py                   # Streamlit entry point
│   ├── pages/
│   │   ├── 1_📈_Graph.py        # Chart page
│   │   └── 2_📋_Signals.py      # Signals table page
│   ├── Features/
│   │   ├── render_dashboard.py  # Plotly chart renderer
│   │   ├── market_structure.py  # Swing zones, PDH/PDL
│   │   ├── Indicators.py        # Dashboard indicator overlays
│   │   └── fetch_clean_data.py  # Data fetch for dashboard
│   └── Utils/
│       └── signals.py           # Signal file parser + Streamlit table
│
├── Data_Sets/
│   └── breakout_data.db         # SQLite breakout cache
│
├── Signals/                     # Strategy output .txt files (generated at runtime)
├── Logs/                        # Main.log (generated at runtime)
└── Pairs_Trading/               # Separate pairs trading sub-project
```

---

## Setup

### 1. Clone and install

```bash
git clone <repo-url>
cd Intraday_Analyzer
pip install -e .
```

Or install dependencies directly:

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
MONGO_URI=<your MongoDB Atlas connection string>
SID=<Twilio Account SID>
TOKEN=<Twilio Auth Token>
TO_NUMBER=whatsapp:+91XXXXXXXXXX
```

### 3. Run the analyzer

```bash
python Main.py
```

This spawns all 11 subprocess workers. Each worker downloads data for its ticker batch and runs all strategies in a loop, sleeping until the next 15m candle close.

### 4. Cleanup before a new session

```bash
python Clean_Up.py
```

### 5. Launch the dashboard

```bash
streamlit run Dashboard/App.py
```

---

## Signal Files

Strategy output is written to the `Signals/` folder as CSV-style `.txt` files:

| File | Strategy | Columns |
|---|---|---|
| `Reg.txt` | Regression | `time, ticker, r2, smooth, vol_ratio` |
| `Vol.txt` | Regression (vol) | `time, ticker, r2, smooth, vol_ratio` |
| `Invalid_Reg.txt` | Regression (no signal) | `time, ticker, r2, smooth, vol_ratio` |
| `5EMA.txt` | 5 EMA | `candle_time, ts, ticker, ema5, vwap, open, high, low, close` |
| `Breakout_15m.txt` | Breakout (phase 1) | `ts, ticker, event_time, label, level, prev_high, prev_low, r2` |
| `Breakout_5m_Confirmation.txt` | Breakout (phase 2) | `ts, ticker, event_time, label, signal, 5m candle OHLCV, r2` |
| `RegHistory.txt` | Rolling R² | `ts, ticker, r2, mean_diff, near, history` |

---

## Requirements

- Python 3.10+
- MongoDB Atlas account (free tier works)
- Twilio account with WhatsApp sandbox enabled
- Active internet connection during market hours (09:15–15:30 IST, Mon–Fri)

Key dependencies: `yfinance`, `pandas`, `numpy`, `scikit-learn`, `streamlit`, `plotly`, `pymongo`, `twilio`, `python-dotenv`, `dtaidistance`

---

## Notes

- The analyzer is designed for **Indian market hours** (NSE). All candle logic, timezone handling, and PDH/PDL calculations are NSE-specific.
- `Main.py` must be run from the project root so `PYTHONPATH` resolves correctly for all subprocesses.
- Signals are deduplicated per session — the same signal won't fire twice for the same ticker until `reset_session()` is called at the next market open.
