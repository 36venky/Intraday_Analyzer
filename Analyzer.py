import time
import logging
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from Data_Manager import *
from Dependencies.Utils import *
from Strategy import *


def Analyzer(tickers):

    start = time.perf_counter()
    Download(tickers)
    end = time.perf_counter()
    write("T(N).txt", f"{datetime.now().strftime('%H:%M:%S')},{end - start:.2f}\n")

    for ticker in tickers:
        Regression(ticker)
        FiveEMA(ticker)

    scan_breakouts(tickers)

    wait_until_next_candle("15m")
