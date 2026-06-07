import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import Analyze_Sleep as AS
from Data_Manager import *
import logging

logging.info("🚀 Analyzer [5] started...")

while True:
    AS.analyze_real_time(get_ticker(5))
    AS.wait_until_next_15_min()
