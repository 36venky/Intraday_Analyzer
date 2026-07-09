from Analyzer import *
from Data_Manager import *
from Dependencies.Features import Daily_Data
import logging

logging.info("🚀 Analyzer [11] started...")

Daily_Data(get_ticker(11))   # downloads 1d data once for this process

while True:
    Analyzer(get_ticker(11))
