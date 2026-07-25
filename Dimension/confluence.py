"""
Dimension/confluence.py
=======================
Higher-timeframe confluence filter.

Takes any strategy's raw signal + current price and cross-checks it
against 4h and 1d swing structure to decide the FINAL trade direction.

Core idea
---------
  A raw signal is just a trigger.  The real direction is dictated by
  WHERE price is relative to higher-timeframe structure:

    price near HTF resistance  →  bias = SELL  (regardless of raw signal)
    price near HTF support     →  bias = BUY   (regardless of raw signal)
    price in open space        →  trust raw signal as-is

Decision table
--------------
  raw=BUY  + near resistance  →  SELL   (fade — price hit overhead supply)
  raw=BUY  + near support     →  BUY    (confirm — buying into demand)
  raw=SELL + near resistance  →  SELL   (confirm — selling into supply)
  raw=SELL + near support     →  BUY    (fade — price hit demand, expect bounce)
  raw=*    + open space       →  raw    (no override, follow the signal)

Public API
----------
    from Dimension.confluence import validate_signal

    result = validate_signal("IRCTC.NS", raw_signal="BUY", price=845.5)

    result = {
        "ticker"         : "IRCTC.NS",
        "raw_signal"     : "BUY",
        "final_signal"   : "SELL",           # overridden
        "action"         : "FADE",           # CONFIRM | FADE | FOLLOW
        "reason"         : "near 4h resistance @ 848.20",
        "nearest_level"  : 848.20,
        "level_type"     : "RESISTANCE",
        "timeframe"      : "4h",
        "proximity_pct"  : 0.032,            # % distance from level
        "overridden"     : True,
    }

Proximity thresholds
--------------------
  4h levels  :  0.3 %   (tighter — intraday precision)
  1d levels  :  0.6 %   (looser  — daily levels have wider influence)

  If price is within threshold of a level it is considered "near".
  1d levels take priority over 4h when both fire simultaneously.
"""

import os
import sys
import logging
from typing import Optional

# ── path bootstrap ────────────────────────────────────────────────────────
_HERE         = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from Data_Manager        import get_data
from Data_Manager.data   import MARKET_DATA
from Dictionary.Structure.Highs_Lows import get_confirmed_swings, get_common_ranges

# =========================================================
# CONSTANTS
# =========================================================

# How close price must be to a level to be considered "near" it
_PROXIMITY = {
    "1d": 0.006,   # 0.6 % — daily levels have a wider magnetic zone
    "4h": 0.003,   # 0.3 % — 4h levels are tighter
}

# Swing detection params (same as Ranges.py for consistency)
_SWING_WINDOW       = 3
_SWING_SIGNIFICANCE = 0.005
_SWING_CONFIRM_PCT  = 0.01


# =========================================================
# INTERNAL — level fetch
# =========================================================

def _get_levels(ticker: str, interval: str) -> dict[str, list[float]]:
    """
    Fetch confirmed swing-range levels for `ticker` on `interval`.

    Returns { "highs": [...resistance levels...],
              "lows" : [...support levels...] }
    Empty lists on any failure.
    """
    df = get_data(ticker, interval)
    if df is None or df.empty:
        logging.debug(f"[Confluence] {ticker}: no {interval} data.")
        return {"highs": [], "lows": []}

    swings = get_confirmed_swings(
        df,
        window       = _SWING_WINDOW,
        significance = _SWING_SIGNIFICANCE,
        confirm_pct  = _SWING_CONFIRM_PCT,
    )
    if not swings:
        logging.debug(f"[Confluence] {ticker}: no confirmed {interval} swings.")
        return {"highs": [], "lows": []}

    return get_common_ranges(swings)


# =========================================================
# INTERNAL — proximity check
# =========================================================

def _nearest_level(
    price    : float,
    levels   : dict[str, list[float]],
    threshold: float,
) -> Optional[dict]:
    """
    Scans all highs and lows in `levels` and returns a dict describing
    the closest level that is within `threshold` of `price`.

    Returns None if no level is within range.

    Return schema:
        {
            "level"      : float,   # the exact level price
            "level_type" : str,     # "RESISTANCE" | "SUPPORT"
            "diff_pct"   : float,   # percentage distance from price
        }
    """
    best = None

    # Check resistance levels (highs)
    for lvl in levels.get("highs", []):
        if lvl <= 0:
            continue
        diff_pct = abs(price - lvl) / lvl
        if diff_pct <= threshold:
            if best is None or diff_pct < best["diff_pct"]:
                best = {
                    "level"      : lvl,
                    "level_type" : "RESISTANCE",
                    "diff_pct"   : round(diff_pct * 100, 4),   # store as %
                }

    # Check support levels (lows)
    for lvl in levels.get("lows", []):
        if lvl <= 0:
            continue
        diff_pct = abs(price - lvl) / lvl
        if diff_pct <= threshold:
            if best is None or diff_pct < best["diff_pct"]:
                best = {
                    "level"      : lvl,
                    "level_type" : "SUPPORT",
                    "diff_pct"   : round(diff_pct * 100, 4),
                }

    return best


# =========================================================
# INTERNAL — decision logic
# =========================================================

def _decide(
    raw_signal : str,
    level_type : str,
) -> tuple[str, str]:
    """
    Given the raw signal and the type of the nearest HTF level,
    return (final_signal, action).

    action:
        CONFIRM  — raw signal agrees with HTF structure
        FADE     — raw signal opposes HTF structure → flip direction
    """
    raw = raw_signal.upper()

    if level_type == "RESISTANCE":
        # Price is near overhead supply → expect rejection → SELL
        final  = "SELL"
        action = "CONFIRM" if raw == "SELL" else "FADE"

    else:   # SUPPORT
        # Price is near demand zone → expect bounce → BUY
        final  = "BUY"
        action = "CONFIRM" if raw == "BUY" else "FADE"

    return final, action


# =========================================================
# PUBLIC API
# =========================================================

def validate_signal(
    ticker     : str,
    raw_signal : str,
    price      : float,
) -> dict:
    """
    Cross-check a strategy's raw signal against 4h and 1d HTF structure.

    Parameters
    ----------
    ticker     : e.g. "IRCTC.NS"
    raw_signal : "BUY" or "SELL"  (case-insensitive)
    price      : current price to compare against levels

    Returns
    -------
    dict with keys:
        ticker, raw_signal, final_signal, action,
        reason, nearest_level, level_type, timeframe,
        proximity_pct, overridden
    """
    raw = raw_signal.upper()

    # ── 1d first (higher priority) ───────────────────────
    for interval in ("1d", "4h"):
        threshold = _PROXIMITY[interval]
        levels    = _get_levels(ticker, interval)
        hit       = _nearest_level(price, levels, threshold)

        if hit is None:
            continue

        final, action = _decide(raw, hit["level_type"])

        return {
            "ticker"        : ticker,
            "raw_signal"    : raw,
            "final_signal"  : final,
            "action"        : action,
            "reason"        : (
                f"near {interval} {hit['level_type'].lower()} "
                f"@ {hit['level']:.2f}  ({hit['diff_pct']:.3f}% away)"
            ),
            "nearest_level" : hit["level"],
            "level_type"    : hit["level_type"],
            "timeframe"     : interval,
            "proximity_pct" : hit["diff_pct"],
            "overridden"    : final != raw,
        }

    # ── No nearby HTF level — follow raw signal ───────────
    return {
        "ticker"        : ticker,
        "raw_signal"    : raw,
        "final_signal"  : raw,
        "action"        : "FOLLOW",
        "reason"        : "no nearby 4h or 1d level — following raw signal",
        "nearest_level" : None,
        "level_type"    : None,
        "timeframe"     : None,
        "proximity_pct" : None,
        "overridden"    : False,
    }


def validate_batch(
    signals: list[dict],
) -> list[dict]:
    """
    Validate a list of raw signals in one call.

    Each input dict must have: ticker, signal (or raw_signal), price.

    Returns the same list with a "confluence" key added to each item
    containing the full validate_signal result.

    Example
    -------
        raw = [
            {"ticker": "IRCTC.NS",   "signal": "BUY",  "price": 845.5},
            {"ticker": "CGPOWER.NS", "signal": "SELL", "price": 312.0},
        ]
        enriched = validate_batch(raw)
        for r in enriched:
            c = r["confluence"]
            print(c["ticker"], c["final_signal"], c["reason"])
    """
    results = []
    for item in signals:
        ticker     = item.get("ticker", "")
        raw_signal = item.get("signal") or item.get("raw_signal", "")
        price      = item.get("price")

        if not ticker or not raw_signal or price is None:
            logging.warning(f"[Confluence] Skipping incomplete item: {item}")
            results.append({**item, "confluence": None})
            continue

        confluence = validate_signal(ticker, raw_signal, float(price))
        results.append({**item, "confluence": confluence})

    return results


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    from Data_Manager import Download, download_daily_all

    tickers = ["IRCTC.NS", "CGPOWER.NS", "DABUR.NS", "DLF.NS"]

    print(f"Downloading data for {len(tickers)} tickers...")
    download_daily_all(tickers)
    Download(tickers)
    print()

    # ── Single signal validation ──────────────────────────
    test_cases = [
        ("IRCTC.NS",   "BUY",  496.5),
        ("CGPOWER.NS", "SELL", 312.0),
        ("DABUR.NS",   "BUY",  520.0),
        ("DLF.NS",     "SELL", 780.0),
    ]

    print(f"{'Ticker':<15} {'Raw':<6} {'Final':<6} {'Action':<8} Reason")
    print("-" * 80)
    for ticker, sig, price in test_cases:
        r = validate_signal(ticker, sig, price)
        tag = "⚡ FLIP" if r["overridden"] else "  ✅ ok"
        print(
            f"{r['ticker']:<15} {r['raw_signal']:<6} {r['final_signal']:<6} "
            f"{r['action']:<8} {r['reason']}  {tag}"
        )

    # ── Batch validation ──────────────────────────────────
    print("\n--- Batch ---")
    raw_signals = [
        {"ticker": "IRCTC.NS",   "signal": "BUY",  "price": 498.5},
        {"ticker": "CGPOWER.NS", "signal": "BUY",  "price": 312.0},
    ]
    for item in validate_batch(raw_signals):
        c = item["confluence"]
        print(f"  {c['ticker']}: {c['raw_signal']} → {c['final_signal']}  ({c['reason']})")
