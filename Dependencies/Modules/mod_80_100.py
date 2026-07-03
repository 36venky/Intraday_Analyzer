from Controller import *
from Data_Manager import *
from Dependencies.Features import Daily_Data
import logging

logging.info("🚀 Analyzer [7] started...")

Daily_Data(get_ticker(7))   # downloads 1d data once for this process

while True:
    Analyzer(get_ticker(7))
