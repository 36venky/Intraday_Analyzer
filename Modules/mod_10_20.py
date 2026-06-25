'''
    Each file in this folder runs as an independent thread/process that calls
    `analyze_real_time()` every 15 minutes for a specific set of tickers.
    This enables parallel analysis of multiple tickers simultaneously,
    improving scalability and preventing the main thread from blocking.
'''
import Dependencies.Utils.Loggings  # noqa: F401

from Controller import *
import logging
from Data_Manager import *
from Dependencies.Features import Daily_Data

logging.info("🚀 Analyzer [1] started...")

Daily_Data(get_ticker(1))   # downloads 1d data once for this process

while True:
    Analyzer(get_ticker(1))
