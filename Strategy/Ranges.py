import logging
from datetime import datetime
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Data_Manager import get_data
from Data_Manager.data import MARKET_DATA
from Dictionary.Structure.Highs_Lows import (
    get_confirmed_swings,
    get_common_ranges,
)
from Dependencies.Utils.Write import write
from Dependencies.Utils.Unique import state
from Dependencies.Utils.Fluctuation import is_fluctuation 

# =========================================================
# CONSTANTS
# =========================================================

_PROXIMITY_PCT = 0.001   # 0.1 % — "near" threshold


# =========================================================
# HELPERS
# =========================================================

def _get_4h_levels(ticker: str) -> dict[str, list[float]]:
    """
    Pull the 4h range levels from MARKET_DATA for `ticker`.

    Returns get_common_ranges output:
        { "highs": [...], "lows": [...] }
    or empty lists on any failure.
    """
    df_4h = get_data(ticker, "4h")
    if df_4h is None or df_4h.empty:
        logging.warning(f"[Ranges] {ticker}: no 4h data in MARKET_DATA.")
        return {"highs": [], "lows": []}

    swings = get_confirmed_swings(df_4h, window=3, significance=0.005, confirm_pct=0.01)
    if not swings:
        logging.debug(f"[Ranges] {ticker}: no confirmed 4h swings.")
        return {"highs": [], "lows": []}

    return get_common_ranges(swings)


def _find_trigger_candle(ticker: str, level: float):
    """
    Scans the 15m dataframe from the oldest bar forward and returns
    (price, candle_time, vol_ratio) of the FIRST candle whose close
    satisfies the proximity condition against `level`.

    vol_ratio = that candle's volume / 20-bar rolling average at that point.
    Falls back to 1m if 15m is unavailable.
    Returns (None, None, None) if no such candle exists.
    """
    for interval in ("15m", "1m"):
        df = MARKET_DATA.get(ticker, {}).get(interval)
        if df is None or df.empty:
            continue

        closes  = df["Close"].to_numpy()
        volumes = df["Volume"].to_numpy() if "Volume" in df.columns else None

        for i, (ts, row) in enumerate(df.iterrows()):
            price = float(closes[i])
            if _classify(price, level) is None:
                continue

            # Found the first candle that triggered the condition
            candle_time = ts.strftime("%H:%M")

            # Volume ratio: candle volume vs rolling 20-bar avg up to this bar
            if volumes is not None and i > 0:
                start    = max(0, i - 19)
                avg_vol  = volumes[start : i + 1].mean()
                vol_ratio = round(float(volumes[i]) / avg_vol, 2) if avg_vol > 0 else 0.0
            else:
                vol_ratio = 0.0

            return price, candle_time, vol_ratio

        # No trigger found in this interval — try fallback
        break

    logging.warning(f"[Ranges] {ticker}: no trigger candle found for level {level:.2f}.")
    return None, None, None


def _classify(price: float, level: float) -> str | None:
    """
    Returns the proximity label relative to a key level:
      - "CROSS_ABOVE"  : price crossed above (price > level  and within 0.1 %)
      - "CROSS_BELOW"  : price crossed below (price < level  and within 0.1 %)
      - "AT_LEVEL"     : price is essentially on the level (diff == 0 or < 0.001 %)
      - None           : price is not close to this level
    """
    if level <= 0:
        return None

    diff_pct = abs(price - level) / level

    if diff_pct > _PROXIMITY_PCT:
        return None   # too far away

    if diff_pct < 1e-5:
        return "AT_LEVEL"

    return "CROSS_ABOVE" if price > level else "CROSS_BELOW"


# =========================================================
# PUBLIC API
# =========================================================

def Ranges(ticker: str) -> None:
    """
    Range-level proximity strategy.

    Logic
    -----
    1. Fetch confluent 4h swing-high / swing-low levels from MARKET_DATA.
    2. Compare the latest 15m close against every level.
    3. If the price has crossed or is within 0.1 % of a level, write a
       BUY (price near a support / low level) or SELL (price near a
       resistance / high level) signal to Signals/ranges.txt.

    One signal per ticker per session (deduplication via state).
    """
    # ── Already fired today ──────────────────────────────
    if state.has_fired("Ranges", ticker, "BUY") or \
       state.has_fired("Ranges", ticker, "SELL"):
        return

    # ── R² from 1m linear regression ─────────────────────
    r2 = is_fluctuation(ticker)

    levels = _get_4h_levels(ticker)
    high_levels = levels.get("highs", [])
    low_levels  = levels.get("lows",  [])

    if not high_levels and not low_levels:
        logging.debug(f"[Ranges] {ticker}: no 4h levels available.")
        return

    # ── Check resistance (high) levels → SELL signal ─────
    for level in high_levels:
        price, candle_time, vol_ratio = _find_trigger_candle(ticker, level)
        if price is None:
            continue

        tag = _classify(price, level)
        if tag is None:
            continue

        signal     = "SELL"
        level_type = "RESISTANCE"
        state.record("Ranges", ticker, signal)

        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = (
            f"{ts},{candle_time},{ticker},{signal},{level_type},"
            f"{level:.2f},{price:.2f},{tag},{r2:.2f},{vol_ratio:.2f}\n"
        )
        write("ranges.txt", line)
        logging.info(
            f"[Ranges] {ticker} | {signal} near {level_type} {level:.2f} | "
            f"candle={candle_time} price={price:.2f} | tag={tag} | "
            f"r2={r2:.2f} | vol_ratio={vol_ratio:.2f}"
        )
        return   # one signal per ticker

    # ── Check support (low) levels → BUY signal ──────────
    for level in low_levels:
        price, candle_time, vol_ratio = _find_trigger_candle(ticker, level)
        if price is None:
            continue

        tag = _classify(price, level)
        if tag is None:
            continue

        signal     = "BUY"
        level_type = "SUPPORT"
        state.record("Ranges", ticker, signal)

        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = (
            f"{ts},{candle_time},{ticker},{signal},{level_type},"
            f"{level:.2f},{price:.2f},{tag},{r2:.2f},{vol_ratio:.2f}\n"
        )
        write("ranges.txt", line)
        logging.info(
            f"[Ranges] {ticker} | {signal} near {level_type} {level:.2f} | "
            f"candle={candle_time} price={price:.2f} | tag={tag} | "
            f"r2={r2:.2f} | vol_ratio={vol_ratio:.2f}"
        )
        return   # one signal per ticker


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    from Data_Manager import Download, download_daily_all, get_ticker,get_all_tickers
    from Dependencies.Utils.Write import _write_queue

    tickers = get_ticker(5)
    print(f"Downloading data for {len(tickers)} tickers...")
    download_daily_all(tickers)
    Download(tickers,"1d")

    print("Scanning 4h range levels...\n")
    for ticker in tickers:
        Ranges(ticker)

    _write_queue.join()   # flush async writer before exit
    print("✅ Done. Check Signals/ranges.txt")
