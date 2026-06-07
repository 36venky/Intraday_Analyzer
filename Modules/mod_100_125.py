import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Data_Manager import *
import Analyze_Sleep as AS
import logging

logging.info("🚀 Analyzer [8] started...")


while True:
    AS.analyze_real_time(get_ticker(8))
    AS.wait_until_next_15_min()
