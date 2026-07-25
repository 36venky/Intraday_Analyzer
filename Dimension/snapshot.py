"""
Dimension/snapshot.py
=====================
Feature snapshot collector.

Gathers every technical parameter for a ticker at signal-fire time and
persists it to a SQLite database (Data_Sets/snapshots.db).  Each strategy
gets its own table so the schema stays clean and queries are fast.

Parameters collected
--------------------
  Indicators (15m unless noted)
    ema_5, ema_9, ema_15, ema_21          — EMA on 15m close
    vwap                                  — intraday VWAP (15m)
    volume_ratio                          — today avg / past-N-day avg
    vol_ma_20                             — 20-bar VMA on 15m volume
    latest_volume                         — most recent 15m volume bar

  Candle anatomy  (latest closed 15m candle)
    body_pct, upper_wick_pct, lower_wick_pct, candle_label

  Regression (1m)
    r2                                    — linear-regression R²

  Smooth (1m DTW)
    smooth_dist                           — best DTW distance to known patterns

  HTF structure
    htf_4h_resistance  (closest confluent high from 4h swings)
    htf_4h_support     (closest confluent low  from 4h swings)
    htf_1d_resistance  (closest confluent high from 1d swings)
    htf_1d_support     (closest confluent low  from 1d swings)

  Next-two 5m candles  (filled in by backfill_5m_candles() at EOD)
    c1_type, c1_body_pct                  — first  5m candle AFTER signal time
    c2_type, c2_body_pct                  — second 5m candle AFTER signal time

  Meta
    ticker, strategy, signal, price, timestamp

Two-phase design
----------------
  Phase 1 — capture() called at signal time
    Stores all indicator/HTF parameters immediately.
    c1 and c2 are left NULL because those candles haven't formed yet.

  Phase 2 — backfill_5m_candles() called at EOD (after 15:30)
    Queries every row WHERE c1_type IS NULL.
    Downloads 5m data for each unique ticker on that day.
    Finds the two 5m candles whose timestamps fall AFTER the signal's
    timestamp, marks them as c1 and c2, and UPDATEs the row.

Usage
-----
    from Dimension.snapshot import capture, backfill_5m_candles

    # at signal time (inside any strategy)
    capture("IRCTC.NS", strategy="regression", signal="BUY", price=845.5)

    # at EOD — call once after market closes
    backfill_5m_candles()
"""

import os
import sys
import sqlite3
import logging
import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import Optional

# ── path bootstrap ────────────────────────────────────────────────────────
_HERE         = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from Data_Manager                        import get_data
from Data_Manager.data                   import MARKET_DATA
from Dictionary.Indicators.EMA           import EMA
from Dictionary.Indicators.VWAP          import VWAP
from Dictionary.Indicators.Volume        import volume_ratio
from Dependencies.Utils.Fluctuation      import is_fluctuation
from Dependencies.Utils.Smooth           import smooth
from Dependencies.Utils.Percent          import candle_breakdown
from Dictionary.Structure.Highs_Lows    import get_confirmed_swings, get_common_ranges

# =========================================================
# CONSTANTS
# =========================================================

_DB_PATH      = os.path.join(_PROJECT_ROOT, "Data_Sets", "snapshots.db")
_VOL_MA_LEN   = 20
_HTF_INTERVALS = ("4h", "1d")

# Swing detection params — same as Ranges.py / confluence.py
_SW_WINDOW    = 3
_SW_SIG       = 0.005
_SW_CONFIRM   = 0.01

# =========================================================
# DATABASE BOOTSTRAP
# =========================================================

# Each strategy gets its own table; all share the same column set.
_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS "{strategy}" (
    id                INTEGER  PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT     NOT NULL,
    ticker            TEXT     NOT NULL,
    signal            TEXT,
    price             REAL,

    -- EMAs (15m)
    ema_5             REAL,
    ema_9             REAL,
    ema_15            REAL,
    ema_21            REAL,

    -- VWAP (15m)
    vwap              REAL,

    -- Volume
    volume_ratio      REAL,
    vol_ma_20         REAL,
    latest_volume     REAL,

    -- Candle anatomy (latest closed 15m candle)
    body_pct          REAL,
    upper_wick_pct    REAL,
    lower_wick_pct    REAL,
    candle_label      TEXT,

    -- Regression (1m)
    r2                REAL,

    -- Smooth DTW (1m)
    smooth_dist       REAL,

    -- HTF levels (nearest confluent level to price)
    htf_4h_resistance REAL,
    htf_4h_support    REAL,
    htf_1d_resistance REAL,
    htf_1d_support    REAL,

    -- Next two 5m candles
    c1_type           TEXT,
    c1_body_pct       REAL,
    c2_type           TEXT,
    c2_body_pct       REAL
);
"""

_INSERT_SQL = """
INSERT INTO "{strategy}" (
    timestamp, ticker, signal, price,
    ema_5, ema_9, ema_15, ema_21,
    vwap,
    volume_ratio, vol_ma_20, latest_volume,
    body_pct, upper_wick_pct, lower_wick_pct, candle_label,
    r2,
    smooth_dist,
    htf_4h_resistance, htf_4h_support,
    htf_1d_resistance, htf_1d_support,
    c1_type, c1_body_pct,
    c2_type, c2_body_pct
) VALUES (
    :timestamp, :ticker, :signal, :price,
    :ema_5, :ema_9, :ema_15, :ema_21,
    :vwap,
    :volume_ratio, :vol_ma_20, :latest_volume,
    :body_pct, :upper_wick_pct, :lower_wick_pct, :candle_label,
    :r2,
    :smooth_dist,
    :htf_4h_resistance, :htf_4h_support,
    :htf_1d_resistance, :htf_1d_support,
    :c1_type, :c1_body_pct,
    :c2_type, :c2_body_pct
);
"""


def _get_conn(strategy: str) -> sqlite3.Connection:
    """Open (or create) the SQLite DB and ensure the strategy table exists."""
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(_CREATE_SQL.format(strategy=strategy))
    conn.commit()
    return conn


# =========================================================
# COLLECTORS — one function per parameter group
# =========================================================

def _collect_emas(ticker: str) -> dict:
    """EMA 5/9/15/21 on 15m — return latest value of each."""
    result = {}
    for length in (5, 9, 15, 21):
        s = EMA(ticker, length, "15m")
        result[f"ema_{length}"] = round(float(s.iloc[-1]), 4) if not s.empty else None
    return result


def _collect_vwap(ticker: str) -> dict:
    """VWAP on 15m — latest value."""
    s = VWAP(ticker, "15m")
    return {"vwap": round(float(s.iloc[-1]), 4) if not s.empty else None}


def _collect_volume(ticker: str) -> dict:
    """volume_ratio + 20-bar VMA + latest raw volume on 15m."""
    out = {"volume_ratio": None, "vol_ma_20": None, "latest_volume": None}

    df = get_data(ticker, "15m")
    if df is None or df.empty or "Volume" not in df.columns:
        return out

    vol = df["Volume"].copy()

    # latest volume
    out["latest_volume"] = round(float(vol.iloc[-1]), 2)

    # 20-bar VMA
    vma = vol.rolling(_VOL_MA_LEN).mean()
    if not vma.empty and pd.notna(vma.iloc[-1]):
        out["vol_ma_20"] = round(float(vma.iloc[-1]), 2)

    # volume_ratio (today vs past N days)
    vr = volume_ratio(ticker, "15m")
    if vr is not None:
        out["volume_ratio"] = round(float(vr[0]), 4)

    return out


def _collect_candle(ticker: str) -> dict:
    """Body / wick percentages and label of the latest closed 15m candle."""
    out = {
        "body_pct": None, "upper_wick_pct": None,
        "lower_wick_pct": None, "candle_label": None,
    }
    df = get_data(ticker, "15m")
    if df is None or df.empty:
        return out

    row = df.iloc[-1]
    bd  = candle_breakdown(row["Open"], row["High"], row["Low"], row["Close"])
    out["body_pct"]       = bd.body_pct
    out["upper_wick_pct"] = bd.upper_wick_pct
    out["lower_wick_pct"] = bd.lower_wick_pct
    out["candle_label"]   = bd.label
    return out


def _collect_r2(ticker: str) -> dict:
    """1m linear-regression R²."""
    r2 = is_fluctuation(ticker)
    return {"r2": round(float(r2), 4) if r2 else None}


def _collect_smooth(ticker: str) -> dict:
    """1m DTW distance to nearest known pattern."""
    dist = smooth(ticker)
    return {"smooth_dist": round(float(dist), 4) if dist else None}


def _collect_htf_levels(ticker: str) -> dict:
    """
    Nearest confluent swing high (resistance) and swing low (support)
    on 4h and 1d, relative to the current 15m close price.

    Returns the single closest level of each type for each timeframe.
    If no confluence level exists on that timeframe, returns None.
    """
    out = {
        "htf_4h_resistance": None, "htf_4h_support": None,
        "htf_1d_resistance": None, "htf_1d_support": None,
    }

    # Current price reference — latest 15m close
    df_15 = get_data(ticker, "15m")
    price = float(df_15["Close"].iloc[-1]) if df_15 is not None and not df_15.empty else None

    for interval in _HTF_INTERVALS:
        df = get_data(ticker, interval)
        if df is None or df.empty:
            continue

        swings = get_confirmed_swings(df, window=_SW_WINDOW,
                                      significance=_SW_SIG,
                                      confirm_pct=_SW_CONFIRM)
        if not swings:
            continue

        ranges = get_common_ranges(swings)
        highs  = ranges.get("highs", [])
        lows   = ranges.get("lows",  [])

        prefix = f"htf_{interval}"   # "htf_4h" or "htf_1d"

        # nearest resistance above price (or closest high overall)
        if highs:
            if price:
                above = [h for h in highs if h >= price]
                nearest_res = min(above, key=lambda h: h - price) if above else min(highs, key=lambda h: abs(h - price))
            else:
                nearest_res = highs[-1]
            out[f"{prefix}_resistance"] = round(nearest_res, 2)

        # nearest support below price (or closest low overall)
        if lows:
            if price:
                below = [l for l in lows if l <= price]
                nearest_sup = max(below, key=lambda l: price - l) if below else min(lows, key=lambda l: abs(l - price))
            else:
                nearest_sup = lows[0]
            out[f"{prefix}_support"] = round(nearest_sup, 2)

    return out


def _collect_next_5m_candles(ticker: str) -> dict:
    """
    Placeholder — c1/c2 are always NULL at capture time.
    They are filled later by backfill_5m_candles().
    """
    return {"c1_type": None, "c1_body_pct": None,
            "c2_type": None, "c2_body_pct": None}


# =========================================================
# EOD BACKFILL — next-two 5m candles
# =========================================================

def _list_strategy_tables(conn: sqlite3.Connection) -> list[str]:
    """Return all user-created table names in the DB."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    ).fetchall()
    return [r[0] for r in rows]


def _fetch_5m_ist(ticker: str) -> pd.DataFrame:
    """
    Download today's 5m bars for `ticker` from yfinance and return
    a DataFrame with an IST-aware DatetimeIndex, filtered to 09:15–15:30.
    Returns an empty DataFrame on any failure.
    """
    try:
        data = yf.download(
            tickers     = ticker,
            interval    = "5m",
            period      = "1d",
            progress    = False,
            auto_adjust = True,
        )
    except Exception as e:
        logging.warning(f"[Backfill] {ticker} 5m download failed: {e}")
        return pd.DataFrame()

    if data is None or data.empty:
        return pd.DataFrame()

    # Flatten multi-index produced when a single ticker is passed as a list
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    # Normalise to IST
    try:
        data.index = data.index.tz_convert("Asia/Kolkata")
    except Exception:
        try:
            data.index = data.index.tz_localize("UTC").tz_convert("Asia/Kolkata")
        except Exception as e:
            logging.warning(f"[Backfill] {ticker} timezone conversion failed: {e}")
            return pd.DataFrame()

    return data.between_time("09:15", "15:30").dropna()


def _find_next_two(df_5m: pd.DataFrame, signal_ts: str) -> dict:
    """
    Given a 5m DataFrame (IST-aware index) and the signal timestamp string
    (format: 'YYYY-MM-DD HH:MM:SS'), return the candle breakdown for the
    first two bars whose open time is STRICTLY AFTER signal_ts.

    Returns dict with c1_type, c1_body_pct, c2_type, c2_body_pct.
    All values are None if fewer than two qualifying bars exist.
    """
    out = {"c1_type": None, "c1_body_pct": None,
           "c2_type": None, "c2_body_pct": None}

    if df_5m.empty:
        return out

    try:
        # Parse signal timestamp — make it tz-aware (IST) for comparison
        ist = "Asia/Kolkata"
        sig_dt = pd.Timestamp(signal_ts).tz_localize(ist)
    except Exception as e:
        logging.warning(f"[Backfill] Could not parse timestamp '{signal_ts}': {e}")
        return out

    # Keep only bars that opened STRICTLY after the signal fired
    future = df_5m[df_5m.index > sig_dt]

    if len(future) < 2:
        logging.debug(f"[Backfill] Less than 2 future 5m bars after {signal_ts}.")
        return out

    for key, row in [("c1", future.iloc[0]), ("c2", future.iloc[1])]:
        bd = candle_breakdown(
            float(row["Open"]), float(row["High"]),
            float(row["Low"]),  float(row["Close"])
        )
        out[f"{key}_type"]     = bd.label
        out[f"{key}_body_pct"] = bd.body_pct

    return out


def backfill_5m_candles(strategies: list[str] = None) -> dict[str, int]:
    """
    EOD pass — fills in c1/c2 for every snapshot row where c1_type IS NULL.

    Call this once after market close (15:30+). It:
      1. Scans every strategy table (or only those in `strategies` if provided)
      2. Finds all rows with c1_type IS NULL (i.e. not yet backfilled today)
      3. Groups them by ticker to minimise yfinance API calls
         (one download per ticker regardless of how many signals fired)
      4. For each row, finds the two 5m bars strictly after the signal timestamp
      5. UPDATEs the row in-place

    Parameters
    ----------
    strategies : list of table names to process; if None all tables are scanned

    Returns
    -------
    dict mapping strategy name → number of rows updated
    """
    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)

    # Discover tables
    all_tables = _list_strategy_tables(conn)
    targets    = strategies if strategies else all_tables

    summary: dict[str, int] = {}

    for strategy in targets:
        if strategy not in all_tables:
            logging.warning(f"[Backfill] Table '{strategy}' not found — skipping.")
            continue

        # ── Fetch all unfilled rows ───────────────────────
        conn.row_factory = sqlite3.Row
        pending = conn.execute(
            f'SELECT id, ticker, timestamp FROM "{strategy}" WHERE c1_type IS NULL'
        ).fetchall()
        conn.row_factory = None

        if not pending:
            logging.info(f"[Backfill] {strategy}: nothing to fill.")
            summary[strategy] = 0
            continue

        # ── Group by ticker — one 5m download per ticker ─
        by_ticker: dict[str, list] = {}
        for row in pending:
            by_ticker.setdefault(row["ticker"], []).append(
                {"id": row["id"], "timestamp": row["timestamp"]}
            )

        updated_count = 0

        for ticker, rows in by_ticker.items():
            df_5m = _fetch_5m_ist(ticker)

            if df_5m.empty:
                logging.warning(
                    f"[Backfill] {ticker}: no 5m data — {len(rows)} row(s) left unfilled."
                )
                continue

            for r in rows:
                candles = _find_next_two(df_5m, r["timestamp"])

                # Skip if still no data (market not closed yet for this candle)
                if candles["c1_type"] is None:
                    logging.debug(
                        f"[Backfill] {ticker} @ {r['timestamp']}: "
                        f"future candles not yet available."
                    )
                    continue

                conn.execute(
                    f"""UPDATE "{strategy}"
                           SET c1_type     = :c1_type,
                               c1_body_pct = :c1_body_pct,
                               c2_type     = :c2_type,
                               c2_body_pct = :c2_body_pct
                         WHERE id = :id""",
                    {**candles, "id": r["id"]},
                )
                updated_count += 1

        conn.commit()
        summary[strategy] = updated_count
        logging.info(f"[Backfill] {strategy}: {updated_count}/{len(pending)} rows filled.")

    conn.close()

    # ── Console summary ───────────────────────────────────
    print("\n[Backfill] EOD 5m candle fill complete:")
    for strat, n in summary.items():
        print(f"  {strat:<20} → {n} rows updated")

    return summary


# =========================================================
# PUBLIC API
# =========================================================

def capture(
    ticker   : str,
    strategy : str,
    signal   : str,
    price    : Optional[float] = None,
) -> dict:
    """
    Collect all parameters for `ticker` and write one row to the
    SQLite table named after `strategy`.

    Parameters
    ----------
    ticker   : e.g. "IRCTC.NS"
    strategy : table name — e.g. "regression", "breakout", "5ema", "ranges"
    signal   : "BUY" | "SELL" | any label from the strategy
    price    : entry price; if None, the latest 15m close is used

    Returns
    -------
    The row dict that was inserted (useful for logging / debugging).
    """
    # ── Resolve price ─────────────────────────────────────
    if price is None:
        df = get_data(ticker, "15m")
        price = float(df["Close"].iloc[-1]) if df is not None and not df.empty else None

    # ── Collect all parameter groups ──────────────────────
    row: dict = {
        "timestamp" : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ticker"    : ticker,
        "signal"    : signal.upper() if signal else None,
        "price"     : round(price, 4) if price is not None else None,
    }

    row.update(_collect_emas(ticker))
    row.update(_collect_vwap(ticker))
    row.update(_collect_volume(ticker))
    row.update(_collect_candle(ticker))
    row.update(_collect_r2(ticker))
    row.update(_collect_smooth(ticker))
    row.update(_collect_htf_levels(ticker))
    row.update(_collect_next_5m_candles(ticker))

    # ── Persist ───────────────────────────────────────────
    try:
        conn = _get_conn(strategy)
        conn.execute(_INSERT_SQL.format(strategy=strategy), row)
        conn.commit()
        conn.close()
        logging.info(
            f"[Snapshot] ✅ {strategy}/{ticker} | {signal} @ {price} stored."
        )
    except sqlite3.Error as e:
        logging.error(f"[Snapshot] ❌ DB write failed for {ticker}: {e}")

    return row


def fetch(
    strategy : str,
    ticker   : str = None,
    limit    : int = 100,
) -> list[dict]:
    """
    Read rows back from a strategy table.

    Parameters
    ----------
    strategy : table name
    ticker   : optional filter — if None returns all tickers
    limit    : max rows returned (most recent first)

    Returns
    -------
    list of dicts, newest first
    """
    try:
        conn  = _get_conn(strategy)
        where = "WHERE ticker = ?" if ticker else ""
        args  = (ticker,) if ticker else ()
        sql   = (
            f'SELECT * FROM "{strategy}" {where} '
            f'ORDER BY id DESC LIMIT {limit}'
        )
        conn.row_factory = sqlite3.Row
        rows  = [dict(r) for r in conn.execute(sql, args).fetchall()]
        conn.close()
        return rows
    except sqlite3.Error as e:
        logging.error(f"[Snapshot] fetch failed: {e}")
        return []


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    from Data_Manager import Download, download_daily_all

    tickers = ["IRCTC.NS", "CGPOWER.NS"]

    print(f"Downloading data for {tickers}...")
    download_daily_all(tickers)
    Download(tickers)
    print()

    # ── Phase 1: capture at signal time ──────────────────
    for ticker in tickers:
        print(f"Capturing snapshot for {ticker}...")
        row = capture(ticker, strategy="regression", signal="BUY")

        print(f"\n{'─'*50}")
        print(f"  {ticker}  |  strategy=regression  |  signal=BUY")
        print(f"{'─'*50}")

        groups = {
            "EMAs"       : ["ema_5","ema_9","ema_15","ema_21"],
            "VWAP"       : ["vwap"],
            "Volume"     : ["volume_ratio","vol_ma_20","latest_volume"],
            "Candle"     : ["body_pct","upper_wick_pct","lower_wick_pct","candle_label"],
            "Regression" : ["r2"],
            "Smooth"     : ["smooth_dist"],
            "HTF 4h"     : ["htf_4h_resistance","htf_4h_support"],
            "HTF 1d"     : ["htf_1d_resistance","htf_1d_support"],
            "Next 5m"    : ["c1_type","c1_body_pct","c2_type","c2_body_pct"],
        }

        for section, keys in groups.items():
            print(f"\n  [{section}]")
            for k in keys:
                val = row.get(k)
                flag = "  ← filled at EOD" if k in ("c1_type","c2_type","c1_body_pct","c2_body_pct") else ""
                print(f"    {k:<25} : {val}{flag}")

    # ── Phase 2: EOD backfill ─────────────────────────────
    print("\n\nRunning EOD backfill (Phase 2)...")
    summary = backfill_5m_candles(strategies=["regression"])

    print("\nPost-backfill rows:")
    for r in fetch("regression", limit=5):
        print(
            f"  {r['ticker']:<15} {r['timestamp']}  "
            f"c1={r['c1_type']}({r['c1_body_pct']}%)  "
            f"c2={r['c2_type']}({r['c2_body_pct']}%)"
        )

    print("\n✅ Done. Check Data_Sets/snapshots.db")
