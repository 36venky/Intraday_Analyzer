'''
    Executions starts form here,
    This script will run all the analyzer scripts concurrently, allowing them to operate simultaneously without blocking each other.
'''

# Must be first — configures the root logger (file-only, no console output)
# before any other module can call logging.basicConfig or add a StreamHandler.
import Dependencies.Utils.Loggings  # noqa: F401

import subprocess
import glob
import os, time, sys

from Controller import *
from Data_Manager import *
from Dependencies.Utils import *
from Dependencies.Features import *

def run_all_analyzers():

    # ── One-time market open init (runs in master process only) ──
    start = time.perf_counter()
    reset_session()
    end = time.perf_counter()
    print(f"Execution Time: {end - start:.2f} seconds")

    # Path to the 'Modules' folder (at project root)
    mod_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Modules")

    # Find all scripts inside the mod folder that start with 'mod_'
    scripts = glob.glob(os.path.join(mod_folder, "mod_*.py"))

    if not scripts:
        print("⚠️ No mod_*.py files found inside the 'mod' folder!")
        return

    processes = []
    for script in scripts:
        #print(f"🚀 Starting {os.path.basename(script)} ...")
        p = subprocess.Popen([sys.executable, script], cwd=mod_folder)
        processes.append(p)

    print("✅ All analyzer scripts are now running concurrently!\n")

    # Keep the master script alive until all analyzers finish
    for p in processes:
        p.wait()

if __name__ == "__main__":
    run_all_analyzers()