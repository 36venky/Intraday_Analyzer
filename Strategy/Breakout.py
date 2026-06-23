import logging
import time
import threading
import sys
import os
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from Data_Manager.data import get_data, Download
from Structure import *
from Data_Manager.tickers import get_ticker
from Dependencies.Utils import write, is_fluctuation, wait_until_next_candle
from Dependencies.Utils.Unique import state

logging.basicConfig(level=logging.INFO)

# =========================================================
# PENDING QUEUE  —  Option B background worker
#
# Structure of each entry:
#   {
#     ticker      : str,
#     type        : "BULL" | "BEAR",
#     bo_high     : float   (BULL only),
#     bd_low      : float   (BEAR only),
#     prev_high   : float,
#     prev_low    : float,
#     event_time  : pd.Timestamp,
#     r2          : float,
#     fire_at     : datetime,   ← wall-clock time to run confirmation
#   }
# =========================================================
_pending_queue: list  = []
_queue_lock           = threading.Lock()
_STALE_MINUTES        = 25


# =========================================================
# BACKGROUND WORKER  —  started once at module import
# =========================================================

def _worker_loop():
    """
    Daemon thread.
    Sleeps until the next 5m candle boundary (via wait_until_next_candle),
    then processes all entries that are now due.
    Never blocks the main thread.
    """
    while True:
        wait_until_next_candle("5m")
        time.sleep(2)          # small settle buffer after candle close
        _process_due_entries()


def _process_due_entries():
    now = datetime.now()

    with _queue_lock:
        due     = [e for e in _pending_queue if e["fire_at"] <= now]
        not_due = [e for e in _pending_queue if e["fire_at"] >  now]
        _pending_queue.clear()
        _pending_queue.extend(not_due)

    if not due:
        return

    tickers = [e["ticker"] for e in due]
    logging.info(f"[Worker] Processing {len(due)} due entries: {tickers}")

    closes_5m = _fetch_5m_closes_batch(tickers)
    results   = _apply_5m_confirmation(due, closes_5m)

    for r in results:
        _log_and_write(r)
        if r["final_signal"] in ("BUY", "SELL"):
            state.record("Breakout", r["ticker"], r["final_signal"])


# Start the single daemon worker at import time
_worker_thread = threading.Thread(
    target=_worker_loop,
    name="BreakoutWorker",
    daemon=True,
)
_worker_thread.start()

# =========================================================
# HELPERS
# =========================================================

def _next_5m_boundary() -> datetime:
    """Returns the wall-clock datetime of the next 5m candle close + 2s buffer.
    Used only to stamp fire_at on queue entries — no sleeping here."""
    now             = datetime.now()
    minutes_to_wait = 5 - (now.minute % 5)
    boundary        = now.replace(second=0, microsecond=0) + timedelta(minutes=minutes_to_wait)
    return boundary + timedelta(seconds=2)




def _breakout_is_fresh(breakout_open_time) -> bool:
    # candle_close = breakout_open_time + timedelta(minutes=15)
    # age = (datetime.now(breakout_open_time.tzinfo) - candle_close).total_seconds() / 60
    # return 0 <= age <= _STALE_MINUTES
    return True   # stale guard kept for future use


# =========================================================
# BATCH 5m FETCH
# =========================================================

def _fetch_5m_closes_batch(tickers: list) -> dict:
    """
    Single yf.download for all tickers at 5m interval.
    Returns { ticker: last_completed_close (float) | None }
    """
    try:
        data = yf.download(
            tickers   = tickers,
            interval  = "5m",
            period    = "1d",
            progress  = False,
            auto_adjust = True,
            group_by  = "ticker",
            threads   = True,
        )
    except Exception as e:
        logging.error(f"Batch 5m download failed: {e}")
        return {t: None for t in tickers}

    result = {}
    for ticker in tickers:
        try:
            df = (
                data[ticker][["Close"]].copy()
                if len(tickers) > 1
                else data[["Close"]].copy()
            )
            try:
                df.index = df.index.tz_convert("Asia/Kolkata")
            except Exception:
                df.index = df.index.tz_localize("UTC").tz_convert("Asia/Kolkata")

            df = df.between_time("09:15", "15:30")

            if df.empty or len(df) < 2:
                result[ticker] = None
                continue

            # iloc[-2] → last fully closed candle
            result[ticker] = float(df["Close"].iloc[-2])

        except Exception as e:
            logging.error(f"[{ticker}] 5m parse error: {e}")
            result[ticker] = None

    return result


# =========================================================
# 15m BREAKOUT DETECTION
# =========================================================

def _find_bullish_breakout(df_today, prev_high, prev_low):
    """
    First 15m candle where open was inside yesterday's range
    and close broke above prev_high.
    Returns (index, bo_high, open_timestamp) or (None, None, None).
    """
    for i, (idx, row) in enumerate(df_today.iterrows()):
        if prev_low < row["Open"] < prev_high and row["Close"] > prev_high:
            return i, float(row["High"]), idx
    return None, None, None


def _find_bearish_breakdown(df_today, prev_high, prev_low):
    """
    First 15m candle where open was inside yesterday's range
    and close broke below prev_low.
    Returns (index, bd_low, open_timestamp) or (None, None, None).
    """
    for i, (idx, row) in enumerate(df_today.iterrows()):
        if prev_low < row["Open"] < prev_high and row["Close"] < prev_low:
            return i, float(row["Low"]), idx
    return None, None, None


# =========================================================
# PHASE 2  —  5m close confirmation logic  (pure, no I/O)
# =========================================================

def _apply_5m_confirmation(pending: list, closes_5m: dict) -> list:
    """
    BULL path:
        5m close > bo_high    → BUY          (broke out and held)
        5m close < prev_high  → SELL         (fake-out, pulled back)
        between               → CONSOLIDATING

    BEAR path:
        5m close < bd_low     → SELL         (broke down and held)
        5m close > prev_low   → BUY          (fake breakdown, recovered)
        between               → CONSOLIDATING
    """
    results = []
    for entry in pending:
        ticker   = entry["ticker"]
        close_5m = closes_5m.get(ticker)

        if close_5m is None:
            final = "CONSOLIDATING"

        elif entry["type"] == "BULL":
            if close_5m > entry["bo_high"]:
                final = "BUY"
            elif close_5m < entry["prev_high"]:
                final = "SELL"
            else:
                final = "CONSOLIDATING"

        else:  # BEAR
            if close_5m < entry["bd_low"]:
                final = "SELL"
            elif close_5m > entry["prev_low"]:
                final = "BUY"
            else:
                final = "CONSOLIDATING"

        results.append({**entry, "final_signal": final, "close_5m": close_5m})

    return results


# =========================================================
# LOG + WRITE
# =========================================================

def _write_raw_breakout(entry: dict):
    """
    Writes the raw 15m breakout/breakdown to a separate file
    BEFORE any 5m confirmation.  Format:
        timestamp, ticker, event_time, type, key_level, prev_high, prev_low, r2
    """
    now       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ticker    = entry["ticker"]
    bo_type   = entry["type"]
    event     = entry["event_time"]
    prev_high = entry["prev_high"]
    prev_low  = entry["prev_low"]
    r2        = entry["r2"]

    if bo_type == "BULL":
        key_level = entry["bo_high"]
        label     = "BULL_BREAKOUT"
    else:
        key_level = entry["bd_low"]
        label     = "BEAR_BREAKDOWN"

    write(
        "1Breakouts_raw.txt",
        f"{now},{ticker},{event},{label},{key_level:.2f},{prev_high:.2f},{prev_low:.2f},{r2:.2f}\n",
    )
    logging.info(f"[{ticker}] RAW {label} written | event={event} | level={key_level:.2f}")


def _log_and_write(r: dict):
    now       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ticker    = r["ticker"]
    label     = f"{r['type']}_BREAKOUT"
    final     = r["final_signal"]
    close_5m  = r.get("close_5m")
    r2        = r["r2"]
    close_str = f"{close_5m:.2f}" if close_5m is not None else "N/A"

    logging.info(
        f"[{ticker}] {label} | event={r['event_time']} | "
        f"5m_close={close_str} | signal={final} | r2={r2:.2f}"
    )

    if r2 > 0.75:
        write(
            "1Breakouts_v2.txt",
            f"{now},{ticker},{r['event_time']},{label},{final},{close_str},{r2:.2f}\n",
        )


# =========================================================
# PUBLIC API
# =========================================================

def reset_confirmed():
    """
    Clears confirmed signals and the pending queue.
    Call once at the start of each trading session.
    """
    state.reset_all()
    with _queue_lock:
        _pending_queue.clear()
    logging.info("[Breakout] Signal state reset for new session.")


def scan_breakouts(tickers: list) -> list:
    """
    Phase 1 — runs synchronously on the main thread.

    1. Scans all tickers on 15m for a fresh breakout/breakdown.
    2. For each match, calculates when the next 5m candle will close
       and enqueues the entry with that fire_at timestamp.
    3. Returns the list of newly-enqueued pending entries immediately
       so the main loop is never blocked.

    Phase 2 (5m confirmation) runs in the background worker thread
    once fire_at has passed.
    """
    pending_new = _scan_all_15m(tickers)

    if not pending_new:
        logging.info("[Breakout] No fresh breakout/breakdown signals this cycle.")
        return []

    fire_at = _next_5m_boundary()   # next 5m boundary + 2s buffer

    # Deduplicate: skip if ticker already queued or confirmed today
    with _queue_lock:
        for entry in pending_new:
            ticker = entry["ticker"]
            # Already sitting in the queue waiting for confirmation
            if state.has_fired("Breakout", ticker, "QUEUED"):
                continue
            entry["fire_at"] = fire_at
            _pending_queue.append(entry)
            state.record("Breakout", ticker, "QUEUED")

            # ── Raw breakout log (pre-confirmation) ──────────────
            _write_raw_breakout(entry)

            logging.info(
                f"[Breakout] Queued {ticker} ({entry['type']}) "
                f"→ fires at {fire_at.strftime('%H:%M:%S')}"
            )

    logging.info(
        f"[Breakout] {len(pending_new)} breakout(s) enqueued. "
        f"Worker confirms at {fire_at.strftime('%H:%M:%S')}."
    )
    return pending_new


# =========================================================
# PHASE 1  —  scan all tickers on 15m  (internal)
# =========================================================

def _scan_all_15m(tickers: list) -> list:
    """
    Scans every ticker for a fresh breakout/breakdown on 15m.
    Returns list of pending dicts — no 5m fetch, no sleep.
    """
    pending = []

    for ticker in tickers:

        # Skip if already confirmed or queued today
        if state.has_fired("Breakout", ticker, "BUY") \
                or state.has_fired("Breakout", ticker, "SELL") \
                or state.has_fired("Breakout", ticker, "QUEUED"):
            logging.debug(f"[{ticker}] already handled today — skip.")
            continue

        prev_high, prev_low = previous_day_levels(ticker)
        if prev_high is None or prev_low is None:
            continue

        df_15m = get_data(ticker, "15m")
        if df_15m is None:
            continue

        today    = df_15m.index.date[-1]
        df_today = df_15m[df_15m.index.date == today]
        if df_today.empty:
            continue

        r2 = is_fluctuation(ticker)

        # --- Bullish breakout ---
        bo_index, bo_high, bo_time = _find_bullish_breakout(df_today, prev_high, prev_low)
        if bo_index is not None:
            if not _breakout_is_fresh(bo_time):
                logging.debug(f"[{ticker}] BULL breakout stale ({bo_time}) — skip.")
            else:
                pending.append({
                    "ticker"    : ticker,
                    "type"      : "BULL",
                    "bo_high"   : bo_high,
                    "prev_high" : float(prev_high),
                    "prev_low"  : float(prev_low),
                    "event_time": bo_time,
                    "r2"        : r2,
                })
                continue   # one signal per ticker

        # --- Bearish breakdown ---
        bd_index, bd_low, bd_time = _find_bearish_breakdown(df_today, prev_high, prev_low)
        if bd_index is not None:
            if not _breakout_is_fresh(bd_time):
                logging.debug(f"[{ticker}] BEAR breakdown stale ({bd_time}) — skip.")
                continue
            pending.append({
                "ticker"    : ticker,
                "type"      : "BEAR",
                "bd_low"    : bd_low,
                "prev_high" : float(prev_high),
                "prev_low"  : float(prev_low),
                "event_time": bd_time,
                "r2"        : r2,
            })

    return pending


# =========================================================
# MAIN  (test usage)
# =========================================================

def main():
    tickers = get_all_tickers()
    print("Started")
    download_daily_all(tickers)
    Download(tickers)
    print("Downloaded")
    scan_breakouts(tickers)
    print("Scan done")

    # Keep process alive long enough for the worker to fire
    logging.info("Main done. Waiting 10 min for worker confirmation...")
    time.sleep(600)


if __name__ == "__main__":
    main()
