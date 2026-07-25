"""
FastAPI backend for the React Intraday Analyzer Dashboard.

Endpoints
─────────
GET  /api/ohlc          ?ticker= &interval= &period=
GET  /api/signals        ?file=   &limit=   &signal= &search=
GET  /api/signal_files   — list available Signals/*.txt files
GET  /api/indicators     ?ticker= &interval= &period=  → EMA9, EMA21, VWAP, RSI
GET  /api/structure      ?ticker= &interval= &period=  → swings, supports, resistance, TL, zones, FVG
GET  /api/pdh_pdl        ?ticker=
GET  /api/market_status  — returns { open: bool, now_ist: str }
"""

import os
import sys
import math
import logging
from datetime import datetime, time as dtime
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ─── project root on sys.path ───────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ─── optional project imports (graceful degradation if env not set up) ──────
try:
    from Dictionary.Structure.Highs_Lows import (
        get_confirmed_swings,
        build_swing_zones,
    )
    from Dictionary.Structure.FVG import detect_fvg, active_fvg
    _structure_ok = True
except Exception as e:
    logging.warning(f"Structure imports failed: {e}")
    _structure_ok = False

# ─── FastAPI app ─────────────────────────────────────────────────────────────
app = FastAPI(title="Intraday Analyzer API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

IST = "Asia/Kolkata"
SIGNALS_DIR = os.path.join(PROJECT_ROOT, "Signals")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_ohlcv(ticker: str, interval: str, period: str) -> Optional[pd.DataFrame]:
    """Fetch OHLCV from yfinance, filter to market hours, return or None."""
    try:
        df = yf.download(
            ticker,
            interval=interval,
            period=period,
            progress=False,
            auto_adjust=True,
        )
    except Exception as e:
        logging.error(f"yfinance error [{ticker}]: {e}")
        return None

    if df is None or df.empty:
        return None

    # Flatten MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
    df = df[cols].copy()

    # Timezone → IST
    try:
        df.index = df.index.tz_convert(IST) if df.index.tz else df.index.tz_localize("UTC").tz_convert(IST)
    except Exception:
        pass

    # Market hours filter for intraday
    if interval in ("1m", "2m", "5m", "15m", "30m"):
        df = df.between_time("09:15", "15:30")

    df = df.apply(pd.to_numeric, errors="coerce").dropna()
    return df if not df.empty else None


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta    = series.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _vwap(df: pd.DataFrame) -> pd.Series:
    tp = (df["High"] + df["Low"] + df["Close"]) / 3
    date_key = df.index.normalize()
    tp_vol   = tp * df["Volume"]
    cumvol   = df.groupby(date_key)["Volume"].cumsum()
    cumtpvol = tp_vol.groupby(date_key).cumsum()
    return cumtpvol / cumvol


def _safe_float(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return float(v)


def _series_to_list(s: pd.Series):
    """Convert a Series to [{t: iso, v: float}] dropping NaN."""
    out = []
    for ts, val in s.items():
        if pd.isna(val):
            continue
        out.append({"t": ts.isoformat(), "v": round(float(val), 4)})
    return out


def _swing_points(highs, lows, window=3):
    n = len(highs)
    if n < 2 * window + 1:
        return [], []
    h = pd.Series(highs)
    l = pd.Series(lows)
    roll_max = h.rolling(2 * window + 1, center=True).max()
    roll_min = l.rolling(2 * window + 1, center=True).min()
    valid = np.arange(window, n - window)
    sh = valid[highs[valid] == roll_max.values[valid]].tolist()
    sl = valid[lows[valid]  == roll_min.values[valid]].tolist()
    return sl, sh


def _filter_swings(indices, values, min_move=0.005):
    if not indices:
        return []
    filtered = [indices[0]]
    for idx in indices[1:]:
        if abs(values[idx] - values[filtered[-1]]) / values[filtered[-1]] >= min_move:
            filtered.append(idx)
    return filtered


def _count_touches(series, start_idx, level, buffer=0.001):
    return [i for i in range(start_idx + 1, len(series))
            if abs(series[i] - level) / level <= buffer]


def _fit_line(indices, values):
    from sklearn.linear_model import LinearRegression
    X = np.array(indices).reshape(-1, 1)
    y = values[indices]
    m = LinearRegression().fit(X, y)
    y_p = m.predict(X)
    ss_res = np.sum((y - y_p) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot else 0
    return float(m.coef_[0]), float(m.intercept_), float(r2)


def _build_trendlines(indices, values, tol=0.004, min_pts=3, r2_min=0.85):
    lines = []
    n = len(indices)
    i = 0
    while i < n - 1:
        current = [indices[i], indices[i + 1]]
        j = i + 2
        while j < n:
            trial = current + [indices[j]]
            slope, intercept, _ = _fit_line(trial, values)
            ok = all(
                abs(values[k] - (slope * k + intercept)) / abs(slope * k + intercept) <= tol
                for k in trial
            )
            if ok:
                current.append(indices[j])
                j += 1
            else:
                break
        if len(current) >= min_pts:
            slope, intercept, r2 = _fit_line(current, values)
            if r2 >= r2_min:
                lines.append({
                    "slope"    : round(slope, 6),
                    "intercept": round(intercept, 4),
                    "points"   : current,
                    "r2"       : round(r2, 4),
                })
        i += 1
    return lines


def _extract_structure_local(df):
    """Fallback structure extraction without project imports."""
    highs = df["High"].to_numpy()
    lows  = df["Low"].to_numpy()

    sl, sh = _swing_points(highs, lows, window=3)
    sl = _filter_swings(sl, lows)
    sh = _filter_swings(sh, highs)

    supports    = []
    resistances = []
    used_s, used_r = [], []

    for idx in sl:
        level = lows[idx]
        if all(abs(level - x) / x > 0.001 for x in used_s):
            touches = _count_touches(lows, idx, level)
            if len(touches) >= 2:
                used_s.append(level)
                supports.append({"index": int(idx), "price": round(float(level), 4), "touches": touches})

    for idx in sh:
        level = highs[idx]
        if all(abs(level - x) / x > 0.001 for x in used_r):
            touches = _count_touches(highs, idx, level)
            if len(touches) >= 2:
                used_r.append(level)
                resistances.append({"index": int(idx), "price": round(float(level), 4), "touches": touches})

    try:
        support_tl    = _build_trendlines(sl, lows)
        resistance_tl = _build_trendlines(sh, highs)
    except Exception:
        support_tl, resistance_tl = [], []

    return {
        "swing_lows"            : [{"index": int(i), "price": round(float(lows[i]), 4)} for i in sl],
        "swing_highs"           : [{"index": int(i), "price": round(float(highs[i]), 4)} for i in sh],
        "supports"              : supports,
        "resistances"           : resistances,
        "support_trendlines"    : support_tl,
        "resistance_trendlines" : resistance_tl,
    }


def _parse_signal_line(file: str, parts: list):
    if "Buy" in file or "Sell" in file:
        if len(parts) != 8:
            return None
        keys = ["Ticker", "Price", "DateTime", "Time", "Score", "Metric1", "Array", "FinalScore"]
    elif "Invalid" in file:
        if len(parts) != 5:
            return None
        keys = ["Time", "Ticker", "Value1", "Value2", "Array"]
    elif "Smooth" in file:
        if len(parts) != 5:
            return None
        keys = ["Time", "Ticker", "Value", "Score", "SignalType"]
    elif "Reg" in file:
        if len(parts) > 9:
            return None
        keys = ["Time", "Ticker", "Value", "Score", "SignalType", "Metric1", "Metric2", "Metric3", "Array"]
    elif "Valid" in file:
        if len(parts) > 9:
            return None
        keys = ["Time", "Ticker", "Value", "Score", "SignalType", "Metric1", "Metric2", "Metric3", "Array"]
    elif "Count" in file:
        if len(parts) > 9:
            return None
        keys = ["Time", "Ticker", "Value", "Score", "SignalType", "Metric1", "Metric2", "Metric3", "Array"]
    else:
        return None
    return dict(zip(keys, parts))


# ─────────────────────────────────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/market_status")
def market_status():
    now = pd.Timestamp.now(tz=IST)
    is_open = (
        now.weekday() < 5
        and dtime(9, 15) <= now.time() <= dtime(15, 30)
    )
    return {"open": is_open, "now_ist": now.strftime("%H:%M IST")}


@app.get("/api/ohlc")
def get_ohlc(
    ticker  : str = Query(...),
    interval: str = Query("15m"),
    period  : str = Query("5d"),
):
    df = _fetch_ohlcv(ticker.upper(), interval, period)
    if df is None:
        raise HTTPException(404, f"No data for {ticker}")

    cols  = ["Open", "High", "Low", "Close"] + (["Volume"] if "Volume" in df.columns else [])
    rows  = []
    for ts, row in df[cols].iterrows():
        r = {
            "t": ts.isoformat(),
            "o": _safe_float(row["Open"]),
            "h": _safe_float(row["High"]),
            "l": _safe_float(row["Low"]),
            "c": _safe_float(row["Close"]),
        }
        if "Volume" in cols:
            r["v"] = _safe_float(row["Volume"])
        rows.append(r)
    return {"ticker": ticker.upper(), "interval": interval, "period": period, "candles": rows}


@app.get("/api/indicators")
def get_indicators(
    ticker  : str = Query(...),
    interval: str = Query("15m"),
    period  : str = Query("5d"),
):
    df = _fetch_ohlcv(ticker.upper(), interval, period)
    if df is None:
        raise HTTPException(404, f"No data for {ticker}")

    result: dict = {}

    # EMA 9 & 21
    result["ema9"]  = _series_to_list(_ema(df["Close"], 9))
    result["ema21"] = _series_to_list(_ema(df["Close"], 21))

    # RSI 14
    result["rsi"] = _series_to_list(_rsi(df["Close"]))

    # VWAP (only meaningful for intraday)
    if "Volume" in df.columns and interval in ("1m", "5m", "15m", "30m", "1h"):
        result["vwap"] = _series_to_list(_vwap(df))
    else:
        result["vwap"] = []

    # Volume MA 5
    if "Volume" in df.columns:
        result["volume"]    = _series_to_list(df["Volume"])
        result["volume_ma"] = _series_to_list(df["Volume"].rolling(5).mean())

    return result


@app.get("/api/structure")
def get_structure(
    ticker  : str = Query(...),
    interval: str = Query("15m"),
    period  : str = Query("5d"),
):
    df = _fetch_ohlcv(ticker.upper(), interval, period)
    if df is None:
        raise HTTPException(404, f"No data for {ticker}")

    ts_list = [t.isoformat() for t in df.index]

    # ── Market structure ──────────────────────────────────────────
    struct = _extract_structure_local(df)

    # Convert index → ISO timestamp
    def idx_to_ts(idx):
        if 0 <= idx < len(ts_list):
            return ts_list[idx]
        return None

    result = {
        "swing_highs": [
            {"t": idx_to_ts(s["index"]), "price": s["price"], "index": s["index"]}
            for s in struct["swing_highs"]
        ],
        "swing_lows": [
            {"t": idx_to_ts(s["index"]), "price": s["price"], "index": s["index"]}
            for s in struct["swing_lows"]
        ],
        "supports": [
            {
                "price"  : s["price"],
                "x0"     : idx_to_ts(s["index"]),
                "x1"     : idx_to_ts(s["touches"][-1]) if s["touches"] else idx_to_ts(s["index"]),
                "touches": len(s["touches"]),
            }
            for s in struct["supports"]
        ],
        "resistances": [
            {
                "price"  : r["price"],
                "x0"     : idx_to_ts(r["index"]),
                "x1"     : idx_to_ts(r["touches"][-1]) if r["touches"] else idx_to_ts(r["index"]),
                "touches": len(r["touches"]),
            }
            for r in struct["resistances"]
        ],
        "support_trendlines": [
            {
                "points": [{"t": idx_to_ts(p), "y": round(float(line["slope"]) * p + float(line["intercept"]), 4)} for p in line["points"]],
                "r2"    : line["r2"],
            }
            for line in struct["support_trendlines"]
        ],
        "resistance_trendlines": [
            {
                "points": [{"t": idx_to_ts(p), "y": round(float(line["slope"]) * p + float(line["intercept"]), 4)} for p in line["points"]],
                "r2"    : line["r2"],
            }
            for line in struct["resistance_trendlines"]
        ],
    }

    # ── Swing zones ───────────────────────────────────────────────
    if _structure_ok:
        try:
            swings = get_confirmed_swings(df, window=3, significance=0.005, confirm_pct=0.01)
            zones  = build_swing_zones(df, swings)
            result["swing_zones"] = [
                {
                    "type"   : z["type"],
                    "x0"     : idx_to_ts(z["left"]),
                    "x1"     : idx_to_ts(z["right"]),
                    "top"    : round(float(z["top"]), 4),
                    "bottom" : round(float(z["bottom"]), 4),
                    "broken" : bool(z["broken"]),
                }
                for z in zones
            ]
            result["confirmed_swings"] = [
                {"t": idx_to_ts(s["index"]), "price": round(float(s["price"]), 4), "type": s["type"]}
                for s in swings
            ]
        except Exception as e:
            logging.warning(f"swing_zones error: {e}")
            result["swing_zones"] = []
            result["confirmed_swings"] = []
    else:
        result["swing_zones"] = []
        result["confirmed_swings"] = []

    # ── FVG ───────────────────────────────────────────────────────
    if _structure_ok:
        try:
            fvg_df = detect_fvg(df, mitigated=True)
            if not fvg_df.empty:
                result["fvg"] = [
                    {
                        "t"          : row["Timestamp"].isoformat(),
                        "direction"  : row["Direction"],
                        "top"        : round(float(row["Top"]), 4),
                        "bottom"     : round(float(row["Bottom"]), 4),
                        "mitigated"  : bool(row.get("Mitigated", False)),
                        "mitigated_at": row["Mitigated_At"].isoformat()
                            if pd.notna(row.get("Mitigated_At")) else None,
                    }
                    for _, row in fvg_df.iterrows()
                ]
            else:
                result["fvg"] = []
        except Exception as e:
            logging.warning(f"FVG error: {e}")
            result["fvg"] = []
    else:
        result["fvg"] = []

    return result


@app.get("/api/pdh_pdl")
def get_pdh_pdl(ticker: str = Query(...)):
    """Fetch previous day's High/Low via yfinance (no MARKET_DATA dependency)."""
    try:
        df = yf.download(ticker, interval="1d", period="5d", progress=False, auto_adjust=True)
        if df is None or df.empty:
            raise HTTPException(404, "No daily data")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] for c in df.columns]
        df = df.dropna(subset=["High", "Low", "Open", "Close"])
        idx_ist = df.index.tz_convert(IST) if df.index.tz else df.index.tz_localize("UTC").tz_convert(IST)
        today   = pd.Timestamp.now(tz=IST).date()
        prev_df = df[idx_ist.date < today]
        if prev_df.empty:
            raise HTTPException(404, "No previous day data")
        prev = prev_df.iloc[-1]
        return {"pdh": round(float(prev["High"]), 2), "pdl": round(float(prev["Low"]), 2)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/api/signal_files")
def signal_files():
    if not os.path.exists(SIGNALS_DIR):
        return {"files": []}
    files = sorted([f for f in os.listdir(SIGNALS_DIR) if f.endswith(".txt")])
    return {"files": files}


@app.get("/api/signals")
def get_signals(
    file  : Optional[str] = Query(None),
    limit : int           = Query(200),
    signal: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    if not os.path.exists(SIGNALS_DIR):
        return {"signals": []}

    data = []
    for fname in os.listdir(SIGNALS_DIR):
        if not fname.endswith(".txt"):
            continue
        if file and fname != file:
            continue

        path = os.path.join(SIGNALS_DIR, fname)
        try:
            with open(path, "r") as f:
                lines = f.readlines()[-limit:]
            for line in reversed(lines):
                parts  = line.strip().split(",")
                parsed = _parse_signal_line(fname, parts)
                if not parsed:
                    continue
                if search and search.lower() not in line.lower():
                    continue
                if signal:
                    if parsed.get("SignalType") != signal and parsed.get("Score") != signal:
                        continue
                parsed["Source"] = fname
                data.append(parsed)
        except Exception as e:
            logging.warning(f"Error reading {fname}: {e}")

    data.sort(key=lambda x: x.get("Time", ""), reverse=True)
    return {"signals": data}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
