import os
import sys
import logging
from datetime import datetime, timedelta, time as dtime
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Environmental Variables
from dotenv import load_dotenv
load_dotenv()

# Dependencies
from Data_Manager import *
from Dependencies.Utils import *
from Strategy import *

def Analyzer(tickers):

    start = time.perf_counter()
    Download(tickers)
    end = time.perf_counter()
    write("T(N).txt",f"{datetime.now().strftime("%H:%M:%S")},{end - start:.2f}\n")

    for ticker in tickers:
        Regression(ticker)

    scan_breakouts(tickers)

    wait_until_next_candle("15m")
