import math
import sys
import os
from datetime import datetime

# Ensure the project root is on sys.path so package imports resolve
# regardless of the working directory when this file is run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Dictionary.Indicators import EMA, VWAP
from Data_Manager import get_data,get_all_tickers
from Dependencies.Utils.Write import write
from Dependencies.Utils.Unique import state

# =========================================================
# CONSTANTS
# =========================================================

STRONG_BODY_THRESHOLD = 70

# =========================================================
# HELPERS
# =========================================================

def _is_strong_bullish(row) -> bool:
    """
    Returns True if the candle is a Strong_Bullish_Candle:
      - Close > Open (bullish)
      - High != Low  (non-zero range)
      - (Close - Open) / (High - Low) >= STRONG_BODY_THRESHOLD / 100
    """
    o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
    if c <= o:
        return False
    if h == l:
        return False
    return (c - o) / (h - l) >= STRONG_BODY_THRESHOLD / 100


# =========================================================
# 5EMA STRATEGY
# =========================================================

def FiveEMA(ticker: str) -> None:
    """
    Detects a 5EMA bearish confluence pattern on 15-minute candles.
    Writes a signal to Signals/5EMA.txt when all five conditions are met.
    Skips if the same signal already fired this session.
    """

    # ── Data guard ────────────────────────────────────────
    df = get_data(ticker, "15m")
    if df is None or df.empty or len(df) < 4:
        return

    # ── Indicator guards ──────────────────────────────────
    ema5 = EMA(ticker, 5, "15m")
    if ema5.empty:
        return

    vwap = VWAP(ticker, "15m")
    if vwap.empty:
        return

    # ── Candle references ─────────────────────────────────
    current_candle = df.iloc[-1]
    prev_candle_1  = df.iloc[-2]
    prev_candle_2  = df.iloc[-3]

    current_idx = current_candle.name

    # ── Indicator value extraction (label-based, KeyError guard) ──
    try:
        ema5_val = ema5[current_idx]
        vwap_val = vwap[current_idx]
    except KeyError:
        return

    # ── NaN guard ─────────────────────────────────────────
    if math.isnan(ema5_val) or math.isnan(vwap_val):
        return

    # ── Deduplication (early exit) ────────────────────────
    if state.has_fired("5ema", ticker, "BEAR"):
        return

    # ── Five signal conditions ────────────────────────────
    o = float(current_candle["Open"])
    h = float(current_candle["High"])
    l = float(current_candle["Low"])
    c = float(current_candle["Close"])

    # (a) Bearish candle
    bearish = c < o

    # (b) Entire candle is strictly above the 5 EMA
    above_ema5 = o > ema5_val and h > ema5_val and l > ema5_val and c > ema5_val

    # (c) Prev_Candle_1 is a Strong_Bullish_Candle
    prev1_strong = _is_strong_bullish(prev_candle_1)

    # (d) Prev_Candle_2 is a Strong_Bullish_Candle
    prev2_strong = _is_strong_bullish(prev_candle_2)

    # (e) EMA_5 > VWAP
    ema_above_vwap = ema5_val > vwap_val

    if not (bearish and above_ema5 and prev1_strong and prev2_strong and ema_above_vwap):
        ts   = datetime.now().strftime("%H:%M:%S")
        candle_time = current_idx.strftime("%H:%M")
        line = f"{candle_time},{ts},{ticker},{ema5_val:.2f},{vwap_val:.2f},{l:.2f},{c:.2f}\n"
        write("Invalid_5EMA.txt", line)
        return

    # ── Record then write ─────────────────────────────────
    state.record("5ema", ticker, "BEAR")

    ts          = datetime.now().strftime("%H:%M:%S")
    candle_time = current_idx.strftime("%H:%M")
    line = f"{candle_time},{ts},{ticker},{ema5_val:.2f},{vwap_val:.2f},{o:.2f},{h:.2f},{l:.2f},{c:.2f}\n"
    write("5EMA.txt", line)


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    from Data_Manager import Download, get_ticker

    tickers = get_all_tickers()
    print(f"Downloading 15m data for {len(tickers)} tickers...")
    Download(tickers)

    for ticker in tickers:
        print(f"  Running FiveEMA on {ticker}...")
        FiveEMA(ticker)

    print("✅ Done. Check Signals/5EMA.txt")