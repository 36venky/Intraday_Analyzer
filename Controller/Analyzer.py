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

def Analyzer(tickers):
    
    now = datetime.now().time()
    start_time = dtime(9,27)
    end_time   = dtime(15, 35)

    T = 1

    if T == 0:
        if not (start_time <= now <= end_time and 0 <= datetime.now().weekday() <= 4):
            return  # Market closed
    
    Download(tickers)

    INTERVAL = "15m"

    for ticker in tickers:
        df = get_data(ticker,INTERVAL)
        if df is None:
            continue
        print(df.tail(1))
