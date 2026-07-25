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
from Dimension.confluence import validate_signal
from Dimension.snapshot   import capture as snap

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

    # ── Deduplication (early exit) ────────────────────────
    if state.has_fired("5ema", ticker, "BEAR"):
        return

    # ── Scan every candle (index >= 2) to find the first
    #    one where all five conditions are true ────────────
    trigger_idx    = None
    trigger_candle = None
    trigger_ema5   = None
    trigger_vwap   = None

    for i in range(2, len(df)):
        candle  = df.iloc[i]
        idx     = candle.name
        prev1   = df.iloc[i - 1]
        prev2   = df.iloc[i - 2]

        try:
            ema5_val = ema5[idx]
            vwap_val = vwap[idx]
        except KeyError:
            continue

        if math.isnan(ema5_val) or math.isnan(vwap_val):
            continue

        o = float(candle["Open"])
        h = float(candle["High"])
        l = float(candle["Low"])
        c = float(candle["Close"])

        bearish        = c < o
        above_ema5     = o > ema5_val and h > ema5_val and l > ema5_val and c > ema5_val
        prev1_strong   = _is_strong_bullish(prev1)
        prev2_strong   = _is_strong_bullish(prev2)
        ema_above_vwap = ema5_val > vwap_val

        if bearish and above_ema5 and prev1_strong and prev2_strong and ema_above_vwap:
            trigger_idx    = idx
            trigger_candle = candle
            trigger_ema5   = ema5_val
            trigger_vwap   = vwap_val
            break   # first match wins

    if trigger_candle is None:
        # Log the latest candle as invalid for diagnostics
        last        = df.iloc[-1]
        last_idx    = last.name
        try:
            e = ema5[last_idx]
            v = vwap[last_idx]
        except KeyError:
            return
        if not (math.isnan(e) or math.isnan(v)):
            ts          = datetime.now().strftime("%H:%M:%S")
            candle_time = last_idx.strftime("%H:%M")
            line = (
                f"{candle_time},{ts},{ticker},"
                f"{e:.2f},{v:.2f},"
                f"{last['Low']:.2f},{last['Close']:.2f}\n"
            )
            write("Invalid_5EMA.txt", line)
        return

    # ── Record then write — candle_time is the trigger candle ─────
    state.record("5ema", ticker, "BEAR")

    ts          = datetime.now().strftime("%H:%M:%S")
    candle_time = trigger_idx.strftime("%H:%M")
    o = float(trigger_candle["Open"])
    h = float(trigger_candle["High"])
    l = float(trigger_candle["Low"])
    c = float(trigger_candle["Close"])

    # ── HTF confluence check ──────────────────────────────
    # 5EMA fires a bearish pattern — default raw is SELL.
    # HTF structure may override to BUY if price is near support.
    cf     = validate_signal(ticker, "SELL", c)
    final  = cf["final_signal"]
    cf_tag = f"{cf['action']}:{cf['timeframe'] or 'raw'}"
    # ─────────────────────────────────────────────────────

    line = (
        f"{candle_time},{ts},{ticker},"
        f"{trigger_ema5:.2f},{trigger_vwap:.2f},"
        f"{o:.2f},{h:.2f},{l:.2f},{c:.2f},"
        f"{final},{cf_tag}\n"
    )
    write("5EMA.txt", line)
    snap(ticker, strategy="5ema", signal=final, price=c)


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    from Data_Manager import Download, get_ticker

    tickers = get_all_tickers()
    print(f"Downloading 15m data for {len(tickers)} tickers...")
    Download(tickers)
    
    print(f"  Running FiveEMA ...")
    for ticker in tickers:
        FiveEMA(ticker)

    print("✅ Done. Check Signals/5EMA.txt")