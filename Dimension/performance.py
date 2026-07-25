"""
Dimension/performance.py
========================
Performance matrix calculator for intraday strategy signals.

Reads closed-trade pairs from Signals/*.txt, applies Groww intraday
charge modelling (from Dependencies/Features/Tax.py), and returns a
structured performance dict that mirrors the reporting style used in
P&L_Plot.py.

Supported strategies
--------------------
  "regression"  → Signals/Reg.txt          (format: time,ticker,r2,smooth,ratio)
  "5ema"        → Signals/5EMA.txt         (format: ctime,stime,ticker,ema5,vwap,O,H,L,C)
  "ranges"      → Signals/ranges.txt       (format: dt,ctime,ticker,signal,type,level,price,tag,r2,vol)
  "breakout"    → Signals/Breakout_5m_Confirmation.txt
                  (format: dt,ticker,event,label,signal,ctime,O,H,L,C,vol,candle_label,r2)

Usage
-----
    from Dimension.performance import calculate_performance, print_report

    matrix = calculate_performance("regression", qty=1, capital=18_000)
    print_report(matrix)

    # or sweep multiple strategies at once
    from Dimension.performance import sweep
    for name, matrix in sweep(qty=1, capital=18_000).items():
        print_report(matrix, title=name)
"""

import os
import sys
import csv
import math
import logging
from datetime import datetime
from typing import Optional

# ── path bootstrap (works whether run directly or imported) ──────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from Dependencies.Features.Tax import calculate_groww_intraday

# ── constants ────────────────────────────────────────────────────────────
_SIGNALS_DIR = os.path.join(_PROJECT_ROOT, "Signals")

_SIGNAL_FILES = {
    "regression" : "Reg.txt",
    "5ema"       : "5EMA.txt",
    "ranges"     : "ranges.txt",
    "breakout"   : "Breakout_5m_Confirmation.txt",
}

# ── default assumptions when qty / capital not passed to each call ───────
_DEFAULT_QTY     = 1          # shares per trade (override via parameter)
_DEFAULT_CAPITAL = 50_000     # ₹ deployed — used for ROI %


# =========================================================
# PARSERS  — one per signal file layout
# =========================================================

def _parse_regression(path: str) -> list[dict]:
    """
    Reg.txt  →  time, ticker, r2, smooth, vol_ratio
    Returns every row as a flat dict.
    """
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 3:
                continue
            rows.append({
                "time"      : parts[0].strip(),
                "ticker"    : parts[1].strip(),
                "r2"        : _safe_float(parts[2]),
                "smooth"    : _safe_float(parts[3]) if len(parts) > 3 else None,
                "vol_ratio" : _safe_float(parts[4]) if len(parts) > 4 else None,
                "signal"    : "REG",
                "price"     : None,   # no entry price in this file
            })
    return rows


def _parse_5ema(path: str) -> list[dict]:
    """
    5EMA.txt  →  candle_time, scan_time, ticker, ema5, vwap, O, H, L, C
    We use Close as the entry price proxy.
    """
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 9:
                continue
            rows.append({
                "time"   : parts[1].strip(),   # scan_time
                "ticker" : parts[2].strip(),
                "ema5"   : _safe_float(parts[3]),
                "vwap"   : _safe_float(parts[4]),
                "open"   : _safe_float(parts[5]),
                "high"   : _safe_float(parts[6]),
                "low"    : _safe_float(parts[7]),
                "price"  : _safe_float(parts[8]),  # Close = entry proxy
                "signal" : "BEAR",
            })
    return rows


def _parse_ranges(path: str) -> list[dict]:
    """
    ranges.txt  →  datetime, candle_time, ticker, signal, type,
                   level, price, tag, r2, vol_ratio
    """
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 7:
                continue
            rows.append({
                "time"       : parts[0].strip(),
                "ticker"     : parts[2].strip(),
                "signal"     : parts[3].strip(),   # BUY / SELL
                "level_type" : parts[4].strip(),   # SUPPORT / RESISTANCE
                "level"      : _safe_float(parts[5]),
                "price"      : _safe_float(parts[6]),
                "tag"        : parts[7].strip() if len(parts) > 7 else "",
                "r2"         : _safe_float(parts[8]) if len(parts) > 8 else None,
                "vol_ratio"  : _safe_float(parts[9]) if len(parts) > 9 else None,
            })
    return rows


def _parse_breakout(path: str) -> list[dict]:
    """
    Breakout_5m_Confirmation.txt  →
        datetime, ticker, event_time, label, final_signal,
        5m_time, 5m_open, 5m_high, 5m_low, 5m_close, 5m_volume,
        candle_label, r2
    Uses 5m_close as the entry price proxy.
    """
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 5:
                continue
            signal = parts[4].strip()
            if signal not in ("BUY", "SELL"):
                continue   # skip CONSOLIDATING
            rows.append({
                "time"    : parts[0].strip(),
                "ticker"  : parts[1].strip(),
                "label"   : parts[3].strip(),
                "signal"  : signal,
                "price"   : _safe_float(parts[9]) if len(parts) > 9 else None,  # 5m_close
                "r2"      : _safe_float(parts[12]) if len(parts) > 12 else None,
            })
    return rows


# ── parser dispatch table ────────────────────────────────────────────────
_PARSERS = {
    "regression" : _parse_regression,
    "5ema"       : _parse_5ema,
    "ranges"     : _parse_ranges,
    "breakout"   : _parse_breakout,
}


# =========================================================
# TRADE PAIRING
# =========================================================

def _pair_trades(rows: list[dict]) -> list[dict]:
    """
    Pairs consecutive BUY → SELL or SELL → BUY signals per ticker
    into closed trades.

    Each trade dict:
        {
            ticker   : str,
            position : "LONG" | "SHORT",
            entry    : float,
            exit     : float,
            entry_t  : str,
            exit_t   : str,
        }

    Rows without a price (e.g. Regression signals that have no entry
    price in the file) are skipped from pairing — they still contribute
    to the signal-count statistics.
    """
    open_positions: dict[str, dict] = {}   # ticker → pending trade
    trades: list[dict] = []

    for row in rows:
        ticker = row.get("ticker")
        price  = row.get("price")
        sig    = row.get("signal", "")
        ts     = row.get("time", "")

        if not ticker or price is None:
            continue

        if ticker not in open_positions:
            # open a new position
            position = "LONG" if sig in ("BUY", "REG", "BEAR") else "SHORT"
            open_positions[ticker] = {
                "ticker"   : ticker,
                "position" : position,
                "entry"    : price,
                "entry_t"  : ts,
            }
        else:
            # close the open position
            pending = open_positions.pop(ticker)
            trades.append({
                **pending,
                "exit"   : price,
                "exit_t" : ts,
            })

    return trades


# =========================================================
# METRICS
# =========================================================

def _compute_metrics(trades: list[dict], qty: int, capital: float) -> dict:
    """
    Runs every closed trade through calculate_groww_intraday and
    aggregates the standard performance matrix.
    """
    if not trades:
        return _empty_matrix()

    pnls            : list[float] = []
    gross_pnls      : list[float] = []
    total_charges   : float       = 0.0
    wins            : int         = 0
    losses          : int         = 0
    max_win         : float       = 0.0
    max_loss        : float       = 0.0
    consecutive_wins: int         = 0
    consecutive_loss: int         = 0
    _cur_win_streak : int         = 0
    _cur_loss_streak: int         = 0
    trade_details   : list[dict]  = []

    for t in trades:
        bp  = t["entry"]
        sp  = t["exit"]
        pos = t["position"]

        result = calculate_groww_intraday(bp, sp, qty, position=pos)

        net    = result["Net Profit"]
        gross  = result["Gross Profit"]
        charge = result["Total Charges"]

        pnls.append(net)
        gross_pnls.append(gross)
        total_charges += charge

        if net > 0:
            wins           += 1
            max_win         = max(max_win, net)
            _cur_win_streak += 1
            _cur_loss_streak = 0
            consecutive_wins = max(consecutive_wins, _cur_win_streak)
        else:
            losses           += 1
            max_loss          = min(max_loss, net)
            _cur_loss_streak += 1
            _cur_win_streak   = 0
            consecutive_loss  = max(consecutive_loss, _cur_loss_streak)

        trade_details.append({
            "ticker"         : t["ticker"],
            "position"       : pos,
            "entry"          : round(bp, 2),
            "exit"           : round(sp, 2),
            "entry_time"     : t.get("entry_t", ""),
            "exit_time"      : t.get("exit_t", ""),
            "gross_profit"   : round(gross, 2),
            "charges"        : round(charge, 4),
            "net_profit"     : round(net, 2),
        })

    total_trades  = len(pnls)
    net_pnl       = round(sum(pnls), 2)
    gross_pnl     = round(sum(gross_pnls), 2)
    accuracy      = round(wins / total_trades * 100, 2) if total_trades else 0.0
    avg_win       = round(sum(p for p in pnls if p > 0) / wins, 2) if wins else 0.0
    avg_loss      = round(sum(p for p in pnls if p <= 0) / losses, 2) if losses else 0.0
    profit_factor = (
        round(abs(sum(p for p in pnls if p > 0)) /
              abs(sum(p for p in pnls if p <= 0)), 2)
        if losses and sum(p for p in pnls if p <= 0) != 0 else float("inf")
    )
    roi_pct       = round(net_pnl / capital * 100, 2) if capital else 0.0
    expectancy    = round(net_pnl / total_trades, 2) if total_trades else 0.0

    # Max drawdown on cumulative curve
    max_drawdown = _max_drawdown(pnls)

    return {
        # ── Summary ──────────────────────────────────────────
        "total_signals"     : 0,   # filled in by calculate_performance
        "total_trades"      : total_trades,
        "wins"              : wins,
        "losses"            : losses,
        "accuracy_pct"      : accuracy,

        # ── P&L ──────────────────────────────────────────────
        "gross_pnl"         : gross_pnl,
        "total_charges"     : round(total_charges, 4),
        "net_pnl"           : net_pnl,
        "roi_pct"           : roi_pct,

        # ── Risk ─────────────────────────────────────────────
        "max_win"           : round(max_win, 2),
        "max_loss"          : round(max_loss, 2),
        "avg_win"           : avg_win,
        "avg_loss"          : avg_loss,
        "profit_factor"     : profit_factor,
        "expectancy_per_trade": expectancy,
        "max_drawdown"      : round(max_drawdown, 2),

        # ── Streaks ──────────────────────────────────────────
        "max_consecutive_wins"  : consecutive_wins,
        "max_consecutive_losses": consecutive_loss,

        # ── Trade log ────────────────────────────────────────
        "trades"            : trade_details,
    }


def _max_drawdown(pnls: list[float]) -> float:
    """
    Peak-to-trough max drawdown on the cumulative P&L curve.
    Returns the drawdown as a negative number (₹).
    """
    if not pnls:
        return 0.0
    peak = 0.0
    peak_equity = 0.0
    equity = 0.0
    for p in pnls:
        equity += p
        if equity > peak_equity:
            peak_equity = equity
        dd = equity - peak_equity
        if dd < peak:
            peak = dd
    return peak


def _empty_matrix() -> dict:
    return {
        "total_signals": 0, "total_trades": 0,
        "wins": 0, "losses": 0, "accuracy_pct": 0.0,
        "gross_pnl": 0.0, "total_charges": 0.0, "net_pnl": 0.0, "roi_pct": 0.0,
        "max_win": 0.0, "max_loss": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
        "profit_factor": 0.0, "expectancy_per_trade": 0.0, "max_drawdown": 0.0,
        "max_consecutive_wins": 0, "max_consecutive_losses": 0,
        "trades": [],
    }


# =========================================================
# PUBLIC API
# =========================================================

def calculate_performance(
    strategy : str,
    qty      : int   = _DEFAULT_QTY,
    capital  : float = _DEFAULT_CAPITAL,
) -> dict:
    """
    Calculates the full performance matrix for a named strategy.

    Parameters
    ----------
    strategy : one of "regression", "5ema", "ranges", "breakout"
    qty      : number of shares per trade (default 1)
    capital  : total capital deployed in ₹ (used for ROI %)

    Returns
    -------
    dict — see _compute_metrics() for full key list
    """
    strategy_key = strategy.lower().strip()

    if strategy_key not in _SIGNAL_FILES:
        raise ValueError(
            f"Unknown strategy '{strategy}'. "
            f"Valid options: {list(_SIGNAL_FILES.keys())}"
        )

    filename = _SIGNAL_FILES[strategy_key]
    path     = os.path.join(_SIGNALS_DIR, filename)

    if not os.path.exists(path):
        logging.warning(f"[Performance] Signal file not found: {path}")
        return _empty_matrix()

    parser = _PARSERS[strategy_key]
    rows   = parser(path)

    if not rows:
        logging.info(f"[Performance] No rows parsed from {filename}.")
        return _empty_matrix()

    trades = _pair_trades(rows)
    matrix = _compute_metrics(trades, qty=qty, capital=capital)
    matrix["total_signals"] = len(rows)

    write_report(matrix, strategy=strategy_key)

    return matrix


def sweep(
    qty     : int   = _DEFAULT_QTY,
    capital : float = _DEFAULT_CAPITAL,
) -> dict[str, dict]:
    """
    Runs calculate_performance over every strategy and returns
    a dict keyed by strategy name.

    Example
    -------
        results = sweep(qty=5, capital=50_000)
        for name, m in results.items():
            print_report(m, title=name)
    """
    return {
        name: calculate_performance(name, qty=qty, capital=capital)
        for name in _SIGNAL_FILES
    }


# =========================================================
# FILE OUTPUT
# =========================================================

def write_report(matrix: dict, strategy: str = "strategy") -> None:
    """
    Writes the full performance matrix + every trade (with entry/exit
    timestamps) to Signals/Performance_<strategy>.txt.

    File layout
    -----------
    Section 1 — run header
        generated_at, strategy, total_signals, total_trades, accuracy_pct

    Section 2 — summary metrics (key = value lines)

    Section 3 — trade log CSV block
        #  | ticker | position | entry_time | entry | exit_time | exit
           | gross_profit | charges | net_profit | result

    The file is overwritten on each call so it always reflects the
    latest run (mirrors how Signals/*.txt files are used in this project).
    """
    os.makedirs(_SIGNALS_DIR, exist_ok=True)
    out_path = os.path.join(_SIGNALS_DIR, f"Performance_{strategy}.txt")

    m   = matrix
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sep = "=" * 60

    lines = []

    # ── Header ────────────────────────────────────────────
    lines += [
        sep,
        f"  Performance Matrix  —  {strategy.upper()}",
        f"  Generated : {now}",
        sep,
        "",
    ]

    # ── Summary ───────────────────────────────────────────
    lines += [
        "[ Signals & Trades ]",
        f"  Total Signals            : {m['total_signals']}",
        f"  Closed Trades            : {m['total_trades']}",
        f"  Winning Trades           : {m['wins']}",
        f"  Losing  Trades           : {m['losses']}",
        f"  Accuracy                 : {m['accuracy_pct']:.2f}%",
        "",
        "[ P&L ]",
        f"  Gross P&L                : {m['gross_pnl']:,.2f}",
        f"  Total Charges            : {m['total_charges']:,.4f}",
        f"  Net P&L                  : {m['net_pnl']:,.2f}",
        f"  ROI                      : {m['roi_pct']:.2f}%",
        "",
        "[ Risk / Edge ]",
        f"  Max Win                  : {m['max_win']:,.2f}",
        f"  Max Loss                 : {m['max_loss']:,.2f}",
        f"  Avg Win                  : {m['avg_win']:,.2f}",
        f"  Avg Loss                 : {m['avg_loss']:,.2f}",
        f"  Profit Factor            : {m['profit_factor']:.2f}x",
        f"  Expectancy / Trade       : {m['expectancy_per_trade']:,.2f}",
        f"  Max Drawdown             : {m['max_drawdown']:,.2f}",
        "",
        "[ Streaks ]",
        f"  Max Consecutive Wins     : {m['max_consecutive_wins']}",
        f"  Max Consecutive Losses   : {m['max_consecutive_losses']}",
        "",
    ]

    # ── Trade log ─────────────────────────────────────────
    if m["trades"]:
        # column widths
        lines.append("[ Trade Log ]")
        hdr = (
            f"  {'#':<4} {'Ticker':<15} {'Pos':<6} "
            f"{'Entry Time':<22} {'Entry':>8}  "
            f"{'Exit Time':<22} {'Exit':>8}  "
            f"{'Gross':>8} {'Charges':>8} {'Net P&L':>10}  Result"
        )
        lines.append(hdr)
        lines.append("  " + "-" * (len(hdr) - 2))

        for i, t in enumerate(m["trades"], start=1):
            result = "WIN " if t["net_profit"] > 0 else "LOSS"
            line = (
                f"  {i:<4} {t['ticker']:<15} {t['position']:<6} "
                f"{t['entry_time']:<22} {t['entry']:>8.2f}  "
                f"{t['exit_time']:<22} {t['exit']:>8.2f}  "
                f"{t['gross_profit']:>8.2f} {t['charges']:>8.4f} "
                f"{t['net_profit']:>10.2f}  {result}"
            )
            lines.append(line)

        lines.append("")

    lines.append(sep)

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    logging.info(f"[Performance] Report written → {out_path}")
    print(f"  ✅ Report saved → {out_path}")


# =========================================================
# REPORTING
# =========================================================

def print_report(matrix: dict, title: str = "Strategy") -> None:
    """
    Prints a formatted performance report to stdout.
    Matches the style of the existing P&L_Plot.py print block.
    """
    m = matrix
    sep = "=" * 50

    print(f"\n{sep}")
    print(f"  Performance Matrix  —  {title.upper()}")
    print(sep)

    print(f"\n── Signals & Trades ─────────────────────────────")
    print(f"  Total Signals         : {m['total_signals']}")
    print(f"  Closed Trades         : {m['total_trades']}")
    print(f"  Winning Trades        : {m['wins']}")
    print(f"  Losing  Trades        : {m['losses']}")
    print(f"  Accuracy              : {m['accuracy_pct']:.2f}%")

    print(f"\n── P&L ──────────────────────────────────────────")
    print(f"  Gross P&L             : ₹{m['gross_pnl']:>10,.2f}")
    print(f"  Total Charges         : ₹{m['total_charges']:>10,.4f}")
    print(f"  Net P&L               : ₹{m['net_pnl']:>10,.2f}")
    print(f"  ROI                   : {m['roi_pct']:.2f}%")

    print(f"\n── Risk / Edge ──────────────────────────────────")
    print(f"  Max Win               : ₹{m['max_win']:>10,.2f}")
    print(f"  Max Loss              : ₹{m['max_loss']:>10,.2f}")
    print(f"  Avg Win               : ₹{m['avg_win']:>10,.2f}")
    print(f"  Avg Loss              : ₹{m['avg_loss']:>10,.2f}")
    print(f"  Profit Factor         : {m['profit_factor']:.2f}x")
    print(f"  Expectancy / Trade    : ₹{m['expectancy_per_trade']:>10,.2f}")
    print(f"  Max Drawdown          : ₹{m['max_drawdown']:>10,.2f}")

    print(f"\n── Streaks ──────────────────────────────────────")
    print(f"  Max Consecutive Wins  : {m['max_consecutive_wins']}")
    print(f"  Max Consecutive Losses: {m['max_consecutive_losses']}")

    if m["trades"]:
        print(f"\n── Trade Log (last 5) ───────────────────────────")
        print(f"  {'Ticker':<15} {'Pos':<6} {'Entry Time':<22} {'Entry':>8}  {'Exit Time':<22} {'Exit':>8} {'Net P&L':>10}")
        print(f"  {'-'*15} {'-'*6} {'-'*22} {'-'*8}  {'-'*22} {'-'*8} {'-'*10}")
        for t in m["trades"][-5:]:
            print(
                f"  {t['ticker']:<15} {t['position']:<6} "
                f"{t['entry_time']:<22} {t['entry']:>8.2f}  "
                f"{t['exit_time']:<22} {t['exit']:>8.2f} "
                f"₹{t['net_profit']:>9,.2f}"
            )

    print(f"\n{sep}\n")


# =========================================================
# HELPERS
# =========================================================

def _safe_float(value: str) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


# =========================================================
# TRAIL RUN
# =========================================================

if __name__ == "__main__":
    print("Running performance sweep across all strategies...\n")

    results = sweep(qty=1, capital=18_000)

    # for strategy_name, matrix in results.items():
    #     print_report(matrix, title=strategy_name)
