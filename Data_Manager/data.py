import sys
import time
import pandas as pd
import yfinance as yf
import logging
import os
from datetime import datetime, timedelta, time as dtime
from Data_Manager.tickers import get_ticker, get_all_tickers


# =========================================================
# LOGGING CONFIG
# =========================================================

os.makedirs(os.path.join(os.path.dirname(__file__), '..', 'Logs'), exist_ok=True)

logging.basicConfig(

    filename=os.path.join(os.path.dirname(__file__), '..', 'Logs', 'Main.log'),
    
    level=logging.INFO,

    format="%(asctime)s %(levelname)s %(message)s"
)

# =========================================================
# GLOBAL MARKET DATA
# =========================================================

MARKET_DATA = {}

# =========================================================
# DOWNLOAD FUNCTION
# =========================================================

def Download(tickers,INTERVAL = None):

    global MARKET_DATA


    if INTERVAL != None :
        int = INTERVAL
    else:
        int = "7d"
    
    configs = {  "1m": "1d",
                "15m": int}

    for interval, period in configs.items():

        try:

            data = yf.download(

                tickers=tickers,

                interval=interval,

                period=period,

                progress=False,

                auto_adjust=True,

                group_by='ticker',

                threads=True
            )

        except Exception as e:

            logging.error(
                f"{interval} download error : {e}"
            )

            continue

        for ticker in tickers:

            try:

                # MULTI TICKER
                if len(tickers) > 0:

                    df = data[ticker][
                        ['Open', 'High', 'Low', 'Close','Volume']
                    ].copy()

                # SINGLE TICKER
                else:

                    df = data[
                        ['Open', 'High', 'Low', 'Close','Volume']
                    ].copy()

            except KeyError:

                logging.warning(
                    f"[{ticker}] {interval} data not found."
                )

                continue

            # =================================================
            # TIMEZONE CONVERSION
            # =================================================

            try:

                df.index = df.index.tz_convert(
                    'Asia/Kolkata'
                )

            except:

                try:

                    df.index = (
                        df.index
                        .tz_localize('UTC')
                        .tz_convert('Asia/Kolkata')
                    )

                except Exception as e:

                    logging.error(
                        f"{ticker} timezone error : {e}"
                    )

            # =================================================
            # MARKET HOURS FILTER
            # =================================================

            if interval in ["1m", "5m", "15m"]:

                df = df.between_time(
                    '09:15',
                    '15:30'
                )

            # =================================================
            # CLEAN DATA
            # =================================================

            df.dropna(inplace=True)

            if df.empty:

                logging.warning(
                    f"[{ticker}] {interval} dataframe empty."
                )

                continue

            # =================================================
            # STORE DATA
            # =================================================

            if ticker not in MARKET_DATA:

                MARKET_DATA[ticker] = {}

            MARKET_DATA[ticker][interval] = df

        logging.info(
            f"[{len(ticker)}] {interval} stored successfully."
        )


def _resample_1h_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """
    Resample 1h IST bars into broker-accurate NSE 4h candles.

    NSE session  : 09:15 – 15:30 IST
    Window rules :
      W1  09:15 → 13:14  (1h bars with  09 ≤ hour < 13)
      W2  13:15 → 15:30  (1h bars with  13 ≤ hour < 16)

    yfinance labels the 1h bar at the START of the hour (09:30 bar = 09:30–10:29).
    Candle timestamp = first bar of the window  →  matches Zerodha / TradingView.
    """

    IST = "Asia/Kolkata"

    # ── ensure IST index ─────────────────────────────────
    if df_1h.index.tz is None:
        idx_ist = df_1h.index.tz_localize("UTC").tz_convert(IST)
    else:
        idx_ist = df_1h.index.tz_convert(IST)

    opens  = df_1h["Open"].to_numpy()
    highs  = df_1h["High"].to_numpy()
    lows   = df_1h["Low"].to_numpy()
    closes = df_1h["Close"].to_numpy()
    vols   = df_1h["Volume"].to_numpy()

    # ── assign each bar to a string bucket key ───────────
    # key format:  "YYYY-MM-DD_W<0|1>"   (sortable, hashable, no tuple issues)

    bucket_keys = []

    for ts in idx_ist:
        h = ts.hour
        if 9 <= h < 13:
            bucket_keys.append(f"{ts.date()}_W0")
        elif 13 <= h < 16:
            bucket_keys.append(f"{ts.date()}_W1")
        else:
            bucket_keys.append(None)   # pre/post-market

    # ── aggregate per bucket ─────────────────────────────
    from collections import OrderedDict

    buckets = OrderedDict()   # preserves insertion (chronological) order

    for i, key in enumerate(bucket_keys):

        if key is None:
            continue

        if key not in buckets:
            buckets[key] = {
                "ts"    : idx_ist[i],   # timestamp of first bar in window
                "open"  : opens[i],
                "high"  : highs[i],
                "low"   : lows[i],
                "close" : closes[i],
                "volume": vols[i],
            }
        else:
            b = buckets[key]
            b["high"]   = max(b["high"],  highs[i])
            b["low"]    = min(b["low"],   lows[i])
            b["close"]  = closes[i]          # last close wins
            b["volume"] += vols[i]

    if not buckets:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])

    # ── build DataFrame ──────────────────────────────────
    rows = list(buckets.values())

    df_4h = pd.DataFrame(
        {
            "Open"  : [r["open"]   for r in rows],
            "High"  : [r["high"]   for r in rows],
            "Low"   : [r["low"]    for r in rows],
            "Close" : [r["close"]  for r in rows],
            "Volume": [r["volume"] for r in rows],
        },
        index=pd.DatetimeIndex([r["ts"] for r in rows], name=df_1h.index.name)
    )

    df_4h.dropna(inplace=True)

    return df_4h


def download_daily_all(tickers=None):
    """Download 1d and 1h interval data for all tickers.
    
    - 1d  : 1 year period  → stored as-is
    - 1h  : 60 day period  → stored as-is
    - 4h  : resampled from 1h data → stored in MARKET_DATA
    """

    if tickers is None:
        tickers = get_all_tickers()

    global MARKET_DATA

    # ─────────────────────────────────────────────────────
    # 1.  DAILY  (1d / 1y)
    # ─────────────────────────────────────────────────────

    logging.info(
        f"Starting 1d download for {len(tickers)} tickers."
    )

    try:

        data_1d = yf.download(

            tickers=tickers,

            interval="1d",

            period="1y",

            progress=False,

            auto_adjust=True,

            group_by='ticker',

            threads=True
        )

    except Exception as e:

        logging.error(f"1d bulk download error : {e}")

        data_1d = None

    if data_1d is not None:

        for ticker in tickers:

            try:

                df = data_1d[ticker][
                    ['Open', 'High', 'Low', 'Close', 'Volume']
                ].copy()

            except KeyError:

                logging.warning(f"[{ticker}] 1d data not found.")

                continue

            df.dropna(inplace=True)

            if df.empty:

                logging.warning(f"[{ticker}] 1d dataframe empty.")

                continue

            if ticker not in MARKET_DATA:

                MARKET_DATA[ticker] = {}

            MARKET_DATA[ticker]["1d"] = df

        logging.info(f"[{len(tickers)}] 1d stored successfully.")

    # ─────────────────────────────────────────────────────
    # 2.  HOURLY  (1h / 60d)  +  4h resample
    # ─────────────────────────────────────────────────────

    logging.info(
        f"Starting 1h download for {len(tickers)} tickers (60d period)."
    )

    try:

        data_1h = yf.download(

            tickers=tickers,

            interval="1h",

            period="60d",

            progress=False,

            auto_adjust=True,

            group_by='ticker',

            threads=True
        )

    except Exception as e:

        logging.error(f"1h bulk download error : {e}")

        data_1h = None

    if data_1h is not None:

        for ticker in tickers:

            try:

                df_1h = data_1h[ticker][
                    ['Open', 'High', 'Low', 'Close', 'Volume']
                ].copy()

            except KeyError:

                logging.warning(f"[{ticker}] 1h data not found.")

                continue

            # ── timezone conversion ──────────────────────

            try:

                df_1h.index = df_1h.index.tz_convert('Asia/Kolkata')

            except Exception:

                try:

                    df_1h.index = (
                        df_1h.index
                        .tz_localize('UTC')
                        .tz_convert('Asia/Kolkata')
                    )

                except Exception as e:

                    logging.error(f"[{ticker}] 1h timezone error : {e}")

            df_1h.dropna(inplace=True)

            if df_1h.empty:

                logging.warning(f"[{ticker}] 1h dataframe empty.")

                continue

            # ── store 1h ────────────────────────────────

            if ticker not in MARKET_DATA:

                MARKET_DATA[ticker] = {}

            MARKET_DATA[ticker]["1h"] = df_1h

            # ── compute & store 4h ──────────────────────

            try:

                df_4h = _resample_1h_to_4h(df_1h)

                if not df_4h.empty:

                    MARKET_DATA[ticker]["4h"] = df_4h

                    logging.info(
                        f"[{ticker}] 4h resampled — {len(df_4h)} candles."
                    )

                else:

                    logging.warning(f"[{ticker}] 4h resample produced empty df.")

            except Exception as e:

                logging.error(f"[{ticker}] 4h resample error : {e}")

        logging.info(f"[{len(tickers)}] 1h/4h stored successfully.")

    logging.info("download_daily_all complete.")

# =========================================================
# COMMON FETCH FUNCTION
# =========================================================

def get_data(ticker, interval):

    global MARKET_DATA

    try:

        df = MARKET_DATA[ticker][interval]

    except KeyError:

        logging.warning(
            f"{ticker} {interval} not available."
        )

        return None

    # =====================================================
    # CANDLE CLOSE CHECK
    # =====================================================
    # Only return data if the last candle has fully closed.
    # i.e. last candle timestamp + interval duration <= now

    interval_minutes = {
        "1m"  : 1,
        "5m"  : 5,
        "15m" : 15,
        "1h"  : 60,
        "4h"  : 240,
        "1d"  : 1440,
    }

    minutes = interval_minutes.get(interval)

    if minutes:

        last_candle_time  = df.index[-1]

        # For 1d candles, close is 15:30 of the same day — not midnight + 1440min
        if interval == "1d":
            candle_close_time = last_candle_time.normalize().replace(
                hour=15, minute=30
            )
        else:
            candle_close_time = last_candle_time + pd.Timedelta(minutes=minutes)

        # Match timezone awareness between index and now
        if candle_close_time.tzinfo is not None:
            now = pd.Timestamp.now(tz=candle_close_time.tzinfo)
        else:
            now = pd.Timestamp.now()

        # After market close (15:15) — return full df including today's candle
        market_close = now.replace(hour=15, minute=15, second=0, microsecond=0)
        if now > market_close:
            logging.info(f"[{ticker}] Market closed. Returning full df.")
            return df

        if candle_close_time > now:
            logging.info(
                f"[{ticker}] {interval} last candle not closed yet. "
                f"Closes at {candle_close_time.strftime('%H:%M:%S')}. "
                f"Returning [-2] candle."
            )
            return df.iloc[:-1]

    return df

# =========================================================
# TRAIL RUN
# =========================================================

def main():
    start = time.perf_counter()

    TEST_TICKERS = ["RELIANCE.NS", "TCS.NS"]

    print(f"\n{'─'*50}")
    print(f"Trail run → download_daily_all({TEST_TICKERS})")
    print(f"{'─'*50}")

    download_daily_all(TEST_TICKERS)

    # ── Report what was stored ──────────────────────────
    for ticker in TEST_TICKERS:
        td = MARKET_DATA.get(ticker, {})
        print(f"\n[{ticker}]")
        for interval, df in td.items():
            print(f"  {interval:>4s}  →  {len(df):>5d} candles  "
                  f"| {df.index[0].strftime('%Y-%m-%d')} "
                  f"→ {df.index[-1].strftime('%Y-%m-%d')}")

        # ── 4h candle preview ───────────────────────────
        if "4h" in td:
            print(f"\n  Last 6 × 4h candles for {ticker}:")
            preview = td["4h"].tail(6).copy()
            preview.index = preview.index.strftime("%Y-%m-%d  %H:%M %Z")
            print(preview.to_string())

    end = time.perf_counter()
    print(f"\nExecution Time: {end - start:.2f} seconds\n")


if __name__ == "__main__":
    main()