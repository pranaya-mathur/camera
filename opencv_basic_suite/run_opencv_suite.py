#!/usr/bin/env python3
"""
Isolated runner for the OpenCV Basic Suite.
Uses traditional OpenCV detectors instead of YOLO models.
"""

from __future__ import annotations
import argparse
import os
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OPENCV_SUITE = ROOT / "opencv_basic_suite"

def run_argv(argv: list[str], env: dict, name: str, procs: list[subprocess.Popen]) -> None:
    print(f"[*] Starting {name}...")
    p = subprocess.Popen(argv, env=env)
    procs.append(p)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-port", default="8000")
    parser.add_argument("--use-webcam", action="store_true")
    args = parser.parse_args()

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("REDIS_HOST", "localhost")
    
    # Storage isolation
    env.setdefault("DB_PATH", str(ROOT / "alerts_opencv.db"))
    env.setdefault("CLIP_DIR", str(ROOT / "storage" / "clips_opencv"))
    env.setdefault("ALERT_SNAPSHOT_DIR", str(ROOT / "storage" / "alert_snapshots_opencv"))

    if args.use_webcam:
        env["BASIC_MAIN_CAMERA"] = "0"
        env["BASIC_SUITE_USE_WEBCAM"] = "1"

    # Localization
    env["DETECTION_CONFIG"] = str(OPENCV_SUITE / "config" / "detection_config.opencv.yaml")
    env["ZONES_CONFIG"] = str(OPENCV_SUITE / "config" / "zones.opencv.yaml")

    procs: list[subprocess.Popen] = []
    py = str(ROOT / "venv" / "bin" / "python3") if (ROOT / "venv" / "bin" / "python3").exists() else "python3"

    try:
        # 1. Shared Backend (Basic)
        # We reuse the basic backend for API access
        run_argv(
            [py, "-m", "uvicorn", "basic_suite.backend_basic:app", "--host", "0.0.0.0", "--port", args.api_port],
            env, "Backend (Reuse Basic)", procs
        )
        
        # 2. OpenCV Ingest (Reuse Basic Webcam Ingest or fork)
        run_argv([py, str(ROOT / "basic_suite" / "pipeline" / "webcam_ingest_basic.py")], env, "Ingest", procs)
        
        # 3. OpenCV Detection
        run_argv([py, str(OPENCV_SUITE / "pipeline" / "detect_opencv.py")], env, "OpenCV Detect", procs)
        
        # 4. OpenCV Rules
        run_argv([py, str(OPENCV_SUITE / "pipeline" / "rules_opencv.py")], env, "OpenCV Rules", procs)

        print("\n[!] opencv_basic_suite running. Press Ctrl+C to stop.\n")
        
        while True:
            time.sleep(2)
            for p in procs:
                if p.poll() is not None:
                    print(f"\n[!] Process exited: {p.returncode}")
                    raise KeyboardInterrupt
                    
    except KeyboardInterrupt:
        print("\n[!] Stopping suite...")
        for p in procs:
            try:
                p.terminate()
            except: pass

if __name__ == "__main__":
    main()
