import sys
import time
import pandas as pd
import yfinance as yf
import logging
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Data_Manager.tickers import get_ticker, get_all_tickers


# =========================================================
# LOGGING CONFIG
# =========================================================

os.makedirs("logs", exist_ok=True)

logging.basicConfig(

    filename="Logs/market_data.log",
    
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

def Download(tickers):

    global MARKET_DATA

    configs = {

        "1m": "1d",
        "15m": "15d",
    }

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
                if len(tickers) > 1:

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
                f"[{ticker}] {interval} stored successfully."
            )


def download_daily_all(tickers=None):
    """Download 1d interval data for all tickers."""

    if tickers is None:
        tickers = get_all_tickers()

    global MARKET_DATA

    logging.info(
        f"Starting 1d download for {len(tickers)} tickers."
    )

    try:

        data = yf.download(

            tickers=all_tickers,

            interval="1d",

            period="5d",

            progress=False,

            auto_adjust=True,

            group_by='ticker',

            threads=True
        )

    except Exception as e:

        logging.error(f"1d bulk download error : {e}")

        return

    for ticker in all_tickers:

        try:

            df = data[ticker][
                ['Open', 'High', 'Low', 'Close']
            ].copy()

        except KeyError:

            logging.warning(
                f"[{ticker}] 1d data not found."
            )

            continue

        df.dropna(inplace=True)

        if df.empty:

            logging.warning(
                f"[{ticker}] 1d dataframe empty."
            )

            continue

        if ticker not in MARKET_DATA:

            MARKET_DATA[ticker] = {}

        MARKET_DATA[ticker]["1d"] = df

        logging.info(
            f"[{ticker}] 1d stored successfully."
        )

    logging.info("1d download complete.")

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
        "1d"  : 1440,
    }

    minutes = interval_minutes.get(interval)

    if minutes:

        now = pd.Timestamp.now(tz='Asia/Kolkata')

        last_candle_time = df.index[-1]

        candle_close_time = last_candle_time + pd.Timedelta(minutes=minutes)

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
    
    Download(get_ticker(1))
    download_daily_all(["SCI.NS"])

    end = time.perf_counter()
    print(f"Execution Time: {end - start:.2f} seconds")


if __name__ == "__main__":
    main()