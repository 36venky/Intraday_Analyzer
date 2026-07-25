import time
import logging
from datetime import datetime, time as dtime

from dotenv import load_dotenv
load_dotenv()

from Data_Manager import *
from Dependencies.Utils import *
from Strategy import *

# ── Set to True to bypass the market-hours check during testing ──────────
TESTING = False

_MARKET_START = dtime(9, 30)
_MARKET_END   = dtime(14, 45)


def _in_market_hours() -> bool:
    """Returns True if current time is between 09:30 and 14:45."""
    return _MARKET_START <= datetime.now().time() <= _MARKET_END


def Analyzer(tickers):

    if not TESTING and not _in_market_hours():
        logging.info(
            f"[Analyzer] Skipped — outside market hours "
            f"({_MARKET_START.strftime('%H:%M')}–{_MARKET_END.strftime('%H:%M')}). "
            f"Set TESTING=True to bypass."
        )
        wait_until_next_candle("15m")
        return

    start = time.perf_counter()
    Download(tickers)
    end = time.perf_counter()
    write("T(N).txt", f"{datetime.now().strftime('%H:%M:%S')},{end - start:.2f}\n")

    for ticker in tickers:
        Regression(ticker)
        FiveEMA(ticker)
        Ranges(ticker)

    scan_breakouts(tickers)

    wait_until_next_candle("15m")
