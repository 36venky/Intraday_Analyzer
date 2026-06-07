import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from Data_Manager import *
import logging
import Analyze_Sleep as AS

logging.info("🚀 Analyzer [3] started...")

while True:
    AS.analyze_real_time(get_ticker(3))
    AS.wait_until_next_15_min()
