'''
    Each file in this folder runs as an independent thread/process that calls
    `analyze_real_time()` every 15 minutes for a specific set of tickers.
    This enables parallel analysis of multiple tickers simultaneously,
    improving scalability and preventing the main thread from blocking.
'''
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Controller import *
import logging
from Data_Manager import *

logging.info("🚀 Analyzer [1] started...")

while True:
    download_daily_all()
    Analyzer(get_ticker(1))
