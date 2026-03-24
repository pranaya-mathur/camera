
import subprocess, time, sys, os

# This script runs all SecureVu components locally.
# Requirements: redis-server must be installed and running on default port.

ENV = os.environ.copy()
ENV["REDIS_HOST"] = "localhost"
ENV["PYTHONPATH"] = os.getcwd() # So modules can find each other

processes = []

def run(cmd, name):
    print(f"[*] Starting {name}...")
    p = subprocess.Popen(cmd, env=ENV, shell=True)
    processes.append(p)

try:
    # 1. Start Backend (API)
    run("venv/bin/python3 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000", "Backend")

    # 2. Start Motion Detection
    run("venv/bin/python3 pipeline/motion.py", "Motion")

    # 3. Start Object Detection
    run("venv/bin/python3 pipeline/detect.py", "Detection")

    # 4. Start Rule Engine
    run("venv/bin/python3 pipeline/rules.py", "Rules")

    # 5. Start Alert Broadcaster
    run("venv/bin/python3 pipeline/alerts_to_backend.py", "Alerts")

    # 6. Start Webcam Ingestion
    run("venv/bin/python3 pipeline/webcam_ingest.py", "Webcam Ingest")

    print("\n[!] All backend components ARE RUNNING. Press Ctrl+C to stop.\n")
    
    # Wait for completion or interrupt
    while True:
        time.sleep(1)

except KeyboardInterrupt:
    print("\n[!] Stopping all components...")
    for p in processes:
        p.terminate()
    print("[!] Done.")
