import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from Controller import *
from Data_Manager import *
import logging

logging.info("🚀 Analyzer [4] started...")

while True:
    Analyzer(get_ticker(4))
