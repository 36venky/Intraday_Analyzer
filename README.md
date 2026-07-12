# 📊 Intraday Analyzer

A real-time intraday stock analysis system for NSE (Indian market) that scans **1000+ tickers concurrently**, applies technical strategies every 15 minutes during market hours, and surfaces signals through a live Streamlit dashboard.

---

## 🖼️ What It Does

| Component | Description |
|---|---|
| **Analyzer Engine** | Downloads live OHLC data via yfinance, runs strategy logic on every closed 15m candle, and stores BUY/SELL signals |
| **Concurrent Scanner** | Splits 1000+ tickers into 11 batches, runs each as an independent subprocess — all batches execute simultaneously |
| **Signal Storage** | Persists signals to MongoDB (with market-hours gating) and flat-file logs under `Signals/` |
| **Live Dashboard** | Streamlit multi-page app with real-time candlestick charts, market structure overlays, and a searchable signal feed |

---

## 🏗️ Architecture

```
Main.py                          ← Entry point; spawns all analyzer subprocesses
│
├── Dependencies/Modules/        ← 11 subprocess scripts (mod_10_20.py … mod_175_200.py)
│   └── Each runs: while True → Analyzer(tickers) → wait_until_next_candle("15m")
│
├── Analyzer.py                  ← Per-cycle logic: Download → Regression → FiveEMA → scan_breakouts
│
├── Data_Manager/
│   ├── data.py                  ← yfinance bulk download, IST timezone handling, candle-close guard
│   └── tickers.py               ← 1000+ NSE ticker symbols split into 11 lists
│
├── Dictionary/
│   ├── Structure/
│   │   ├── Highs_Lows.py        ← Swing detection, confirmed swings, swing zone builder, PDH/PDL
│   │   ├── FVG.py               ← Fair Value Gap detection (vectorized numpy), mitigation tracking
│   │   └── Simmilar.py
│   └── Indicators/
│       ├── EMA.py  RSI.py  VWAP.py  Volume.py
│
├── Dependencies/
│   ├── Features/
│   │   ├── Database.py          ← MongoDB signal store/fetch/clear with market-hours guard
│   │   ├── Initializer.py       ← SignalState dedup tracker, Daily_Data one-shot downloader
│   │   ├── Messages.py          ← Telegram / notification dispatch
│   │   └── Tax.py  Url.py  P&L_Plot.py
│   └── Utils/
│       ├── Loggings.py          ← Custom log levels (BUY/SELL/THREAD/CYCLE/INVALID/VALID), colour formatter
│       ├── RollingSignal.py     ← Per-ticker rolling momentum tracker (last-3 value scoring)
│       ├── Smooth.py  Angle.py  Fluctuation.py  Percent.py  Xval.py
│       └── Sleep.py  Write.py  Unique.py
│
└── Dashboard/
    ├── App.py                   ← Streamlit entry point (streamlit run Dashboard/App.py)
    ├── pages/
    │   ├── 1_📈_Graph.py        ← Live candlestick chart with market-hours auto-refresh
    │   └── 2_📋_Signals.py      ← Searchable, filterable signal feed (auto-refreshes every 3s)
    ├── Features/
    │   ├── render_dashboard.py  ← Plotly chart builder: candles, EMA, swing zones, PDH/PDL, trendlines
    │   ├── market_structure.py  ← Swing points, S/R levels, trendline fitting (R² scored), FVG zones
    │   ├── fetch_clean_data.py  ← Cached yfinance fetch with IST conversion + market-hours filter
    │   └── UI.py                ← Sidebar controls (ticker input, interval, period, indicators)
    └── Utils/
        └── signals.py           ← Signal file parser
```

---

## ⚙️ Technical Concepts Implemented

**Market Structure**
- Swing high / low detection with rolling window
- Confirmed swings requiring ≥1% follow-through before recording
- Support & resistance zones built from swing candles with breakout tracking
- Trendline fitting using `sklearn.LinearRegression` with R² quality filter (≥0.85)

**Fair Value Gaps (FVG)**
- Vectorized numpy detection of bullish and bearish gaps (3-candle pattern)
- Mitigation tracking: marks gaps as filled when price closes back inside

**Data Pipeline**
- Multi-interval download: `1m`, `15m`, `1h`, `1d`
- 4h candles resampled from 1h data using NSE-accurate session windows (09:15–13:14, 13:15–15:30)
- Candle-close guard: returns `df[:-1]` when the last candle hasn't closed yet
- IST timezone handling throughout (UTC localize → Asia/Kolkata convert)

**Signal Deduplication**
- `SignalState` class prevents the same signal firing on consecutive candles for the same ticker
- `RollingSignal` scores momentum from the last 3 readings (mean diff + threshold checks)

**Concurrency**
- `subprocess.Popen` launches 11 independent processes, each handling ~90 tickers
- `PYTHONPATH` propagated to subprocesses so imports resolve without `pip install -e .`

**Logging**
- Custom `logging` levels: `BUY (25)`, `SELL (26)`, `THREAD (27)`, `CYCLE (28)`, `INVALID (29)`, `VALID (30)`
- ANSI colour formatter in console; structured `%(asctime)s | %(levelname)s | %(message)s` to `Logs/Main.log`

---

## 🖥️ Dashboard Features

**Graph Page (`1_📈_Graph.py`)**
- Plotly dark-theme candlestick / line chart
- Toggleable overlays: EMA 9/21, swing highs/lows, support/resistance lines, trendlines, swing zones, PDH/PDL
- Click a candle → shows OHLC detail (open, high, low, close, delta) inline
- Auto-refresh only during market hours (09:15–15:15 IST), pauses when market is closed
- Manual refresh button that clears the data cache

**Signals Page (`2_📋_Signals.py`)**
- Reads all `.txt` log files from `Signals/` directory
- Filters: free-text search, BUY/SELL filter, per-file filter, row limit
- Auto-refreshes every 3 seconds
- Parses multiple log formats (Buy/Sell, Smooth, Regression, Valid, Count, Invalid)

---

## 🚀 Getting Started

### Prerequisites

```bash
pip install yfinance pandas numpy streamlit plotly scikit-learn pymongo python-dotenv streamlit-autorefresh pytz
```

### Environment Setup

Create a `.env` file in the project root:

```env
MONGO_URI=mongodb+srv://<user>:<password>@<cluster>.mongodb.net/
```

### Run the Analyzer (market hours)

```bash
python Main.py
```

This spawns all 11 subprocess scanners. Each scanner downloads data and runs strategy logic on every closed 15-minute candle.

### Run the Dashboard

```bash
streamlit run Dashboard/App.py
```

Navigate to `http://localhost:8501` in your browser.

---

## 📁 Data & Logs

| Path | Contents |
|---|---|
| `Signals/` | Flat-file signal logs written by each strategy (`Buy.txt`, `Sell.txt`, `Smooth.txt`, etc.) |
| `Logs/Main.log` | Structured application log (all levels) |
| `Data_Sets/breakout_data.db` | SQLite database for breakout pattern storage |

---

## 🛠️ Tech Stack

| Category | Library |
|---|---|
| Data | `yfinance`, `pandas`, `numpy` |
| ML / Stats | `scikit-learn` (LinearRegression for trendlines) |
| Database | `pymongo` (MongoDB Atlas), `sqlite3` |
| Dashboard | `streamlit`, `plotly` |
| Concurrency | `subprocess`, Python standard library |
| Config | `python-dotenv` |

---

## 📈 Ticker Universe

Covers **1000+ NSE-listed stocks** across large-cap, mid-cap, and small-cap segments including NIFTY 50 components (RELIANCE, TCS, INFY, SBIN, HDFC), sectoral picks (IRCTC, CGPOWER, SUZLON, ADANIGREEN), and high-liquidity small-caps — split into 11 ticker lists for parallel processing.
