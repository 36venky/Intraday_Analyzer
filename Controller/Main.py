'''
    Executions starts form here,
    This script will run all the analyzer scripts concurrently, allowing them to operate simultaneously without blocking each other.
'''

import subprocess
import glob
import os

def run_all_analyzers():
    # Path to the 'mod' folder
    mod_folder = os.path.join(os.path.dirname(__file__), "Modules")

    # Find all scripts inside the mod folder that start with 'mod_'
    scripts = glob.glob(os.path.join(mod_folder, "mod_*.py"))

    if not scripts:
        print("⚠️ No mod_*.py files found inside the 'mod' folder!")
        return

    processes = []
    for script in scripts:
        #print(f"🚀 Starting {os.path.basename(script)} ...")
        p = subprocess.Popen(["python", script], cwd=mod_folder)
        processes.append(p)

    print("✅ All analyzer scripts are now running concurrently!\n")

    # Keep the master script alive until all analyzers finish
    for p in processes:
        p.wait()

if __name__ == "__main__":
    run_all_analyzers()