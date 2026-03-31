#!/usr/bin/env python3
"""
Run isolated basic suite from basic_suite/ without editing core pipeline files.

It uses:
- basic_suite/pipeline/webcam_ingest_basic.py
- basic_suite/pipeline/motion_basic.py
- core detect.py / clip_buffer.py / backend.app
- basic_suite/pipeline/rules_basic.py

The goal is separation of configs + entrypoints, while reusing proven core modules.
"""

from __future__ import annotations

import argparse
import copy
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BASIC = ROOT / "basic_suite"


def run(cmd: str, env: dict, name: str, procs: list[subprocess.Popen]) -> None:
    print(f"[*] Starting {name}...")
    p = subprocess.Popen(cmd, env=env, shell=True)
    procs.append(p)


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _apply_profile_overrides(basic_dir: Path, profile: dict, env: dict) -> Path:
    """
    Materialize profile-overridden detection config to a generated file.
    This fully wires use_cases.yaml `rules_overrides` support.
    """
    src = basic_dir / "config" / "detection_config.basic.yaml"
    cfg = yaml.safe_load(src.read_text()) or {}
    overrides = profile.get("rules_overrides") or {}
    merged = _deep_merge(cfg, overrides)
    gen_dir = basic_dir / "generated"
    gen_dir.mkdir(parents=True, exist_ok=True)
    out = gen_dir / "detection_config.runtime.yaml"
    out.write_text(yaml.safe_dump(merged, sort_keys=False))
    env["DETECTION_CONFIG"] = str(out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="home_monitoring")
    parser.add_argument("--api-port", default="8100")
    args = parser.parse_args()

    use_cases = yaml.safe_load((BASIC / "config" / "use_cases.yaml").read_text()) or {}
    profiles = (use_cases.get("profiles") or {})
    if args.profile not in profiles:
        print(f"[!] Unknown profile: {args.profile}. Available: {', '.join(profiles.keys())}")
        return 2
    profile = profiles[args.profile]

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONUNBUFFERED"] = "1"
    env.setdefault("REDIS_HOST", "localhost")
    env["DETECTION_CONFIG"] = str(BASIC / "config" / "detection_config.basic.yaml")
    env["ZONES_CONFIG"] = str(BASIC / "config" / "zones.basic.yaml")
    env["BASIC_CAMERAS_CONFIG"] = str(BASIC / "config" / "cameras.basic.yaml")
    env["MOTION_DIFF_MEAN_THRESHOLD"] = str(profile.get("motion_diff_threshold", 3.0))
    runtime_cfg = _apply_profile_overrides(BASIC, profile, env)

    # Keep data separated from main suite.
    env.setdefault("DB_PATH", str(ROOT / "alerts_basic.db"))
    env.setdefault("CLIP_DIR", str(ROOT / "storage" / "clips_basic"))

    # Lightweight defaults
    env.setdefault("NUM_WORKERS", "1")
    env.setdefault("BATCH_SIZE", "1")
    env.setdefault("FIRE_VERIFY_EVERY_FRAME", "0")

    print("[*] basic_suite profile:", args.profile)
    print("[*] API:", f"http://127.0.0.1:{args.api_port}")
    print("[*] DETECTION_CONFIG:", env["DETECTION_CONFIG"])
    print("[*] ZONES_CONFIG:", env["ZONES_CONFIG"])
    print("[*] BASIC_CAMERAS_CONFIG:", env["BASIC_CAMERAS_CONFIG"])
    print("[*] RUNTIME_CONFIG:", runtime_cfg)

    procs: list[subprocess.Popen] = []
    py = "venv/bin/python3" if (ROOT / "venv" / "bin" / "python3").exists() else "python3"

    try:
        run(
            f"{py} -m uvicorn basic_suite.backend_basic:app --host 127.0.0.1 --port {args.api_port}",
            env,
            "Basic Backend (RBAC+Plans)",
            procs,
        )
        run(f"{py} basic_suite/pipeline/motion_basic.py", env, "Basic Motion", procs)
        run(f"{py} pipeline/detect.py", env, "Detection", procs)
        run(f"{py} basic_suite/pipeline/rules_basic.py", env, "Basic Rules", procs)
        run(f"{py} pipeline/clip_buffer.py", env, "Clip Buffer", procs)
        run(f"{py} basic_suite/pipeline/webcam_ingest_basic.py", env, "Basic Ingest", procs)

        print("\n[!] basic_suite running. Ctrl+C to stop all.\n")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[!] Stopping basic_suite...")
        for p in procs:
            try:
                p.send_signal(signal.SIGTERM)
            except Exception:
                pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
