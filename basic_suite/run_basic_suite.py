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


def run_argv(argv: list[str], env: dict, name: str, procs: list[subprocess.Popen]) -> None:
    """Avoid shell=True so env vars (e.g. BASIC_MAIN_CAMERA) reliably reach child processes."""
    print(f"[*] Starting {name}...")
    p = subprocess.Popen(argv, env=env)
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
    parser.add_argument("--api-port", default="8000")
    parser.add_argument(
        "--use-webcam",
        action="store_true",
        help="Use built-in webcam (camera index 0). Same as BASIC_MAIN_CAMERA=0.",
    )
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
    # Default: no live MJPEG/embed to customer-style roles (viewer); operators keep /video.
    env.setdefault("BASIC_SUITE_LIVE_FEED_MODE", "internal")
    # JPEG on every alert (end-user evidence); MP4 clips still recorded for operators unless legacy flag set.
    env.setdefault("BASIC_SUITE_ALERT_SNAPSHOTS", "1")
    env.setdefault("BASIC_SUITE_OPERATOR_CLIPS", "1")
    env.setdefault("ALERT_SNAPSHOT_DIR", str(ROOT / "storage" / "alert_snapshots"))
    if args.use_webcam:
        env["BASIC_MAIN_CAMERA"] = "0"
        # Backup flag: some environments drop arbitrary env keys; ingest honors this too.
        env["BASIC_SUITE_USE_WEBCAM"] = "1"
    env["DETECTION_CONFIG"] = str(BASIC / "config" / "detection_config.basic.yaml")
    env["ZONES_CONFIG"] = str(BASIC / "config" / "zones.basic.yaml")
    env["BASIC_CAMERAS_CONFIG"] = str(BASIC / "config" / "cameras.basic.yaml")
    env["MOTION_DIFF_MEAN_THRESHOLD"] = str(profile.get("motion_diff_threshold", 3.0))
    runtime_cfg = _apply_profile_overrides(BASIC, profile, env)

    # Keep data separated from main suite.
    env.setdefault("DB_PATH", str(ROOT / "alerts_basic.db"))
    env.setdefault("CLIP_DIR", str(ROOT / "storage" / "clips_basic"))

    # Lightweight defaults: single YOLO-World only (see models/registry.basic.yaml).
    # Full face + fire-verify + LPD: export MODEL_REGISTRY=models/registry.yaml
    env.setdefault("MODEL_REGISTRY", str(ROOT / "models" / "registry.basic.yaml"))
    env.setdefault("NUM_WORKERS", "1")
    env.setdefault("BATCH_SIZE", "1")
    env.setdefault("FIRE_VERIFY_EVERY_FRAME", "0")

    print("[*] basic_suite profile:", args.profile)
    print("[*] BASIC_SUITE_LIVE_FEED_MODE:", env.get("BASIC_SUITE_LIVE_FEED_MODE", "internal"))
    print("[*] BASIC_SUITE_ALERT_SNAPSHOTS:", env.get("BASIC_SUITE_ALERT_SNAPSHOTS", "1"))
    print("[*] BASIC_SUITE_OPERATOR_CLIPS:", env.get("BASIC_SUITE_OPERATOR_CLIPS", "1"))
    print("[*] BASIC_MAIN_CAMERA:", env.get("BASIC_MAIN_CAMERA", "(not set)"))
    print("[*] API:", f"http://127.0.0.1:{args.api_port}")
    print("[*] DETECTION_CONFIG:", env["DETECTION_CONFIG"])
    print("[*] ZONES_CONFIG:", env["ZONES_CONFIG"])
    print("[*] BASIC_CAMERAS_CONFIG:", env["BASIC_CAMERAS_CONFIG"])
    print("[*] RUNTIME_CONFIG:", runtime_cfg)
    print("[*] MODEL_REGISTRY:", env.get("MODEL_REGISTRY", "(default)"))

    procs: list[subprocess.Popen] = []
    py = str(ROOT / "venv" / "bin" / "python3") if (ROOT / "venv" / "bin" / "python3").exists() else "python3"

    try:
        run_argv(
            [
                py,
                "-m",
                "uvicorn",
                "basic_suite.backend_basic:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(args.api_port),
            ],
            env,
            "Basic Backend (RBAC+Plans)",
            procs,
        )
        run_argv([py, str(BASIC / "pipeline" / "motion_basic.py")], env, "Basic Motion", procs)
        run_argv([py, str(ROOT / "pipeline" / "detect.py")], env, "Detection", procs)
        run_argv([py, str(BASIC / "pipeline" / "rules_basic.py")], env, "Basic Rules", procs)
        _legacy_img = env.get("BASIC_SUITE_ALERTS_IMAGES_ONLY", "") == "1"
        _op_clip = env.get("BASIC_SUITE_OPERATOR_CLIPS", "1") == "1" and not _legacy_img
        if _op_clip:
            run_argv([py, str(ROOT / "pipeline" / "clip_buffer.py")], env, "Clip Buffer", procs)
        else:
            print(
                "[*] Clip Buffer skipped (set BASIC_SUITE_OPERATOR_CLIPS=1; "
                "legacy BASIC_SUITE_ALERTS_IMAGES_ONLY forces off)",
            )
        run_argv([py, str(BASIC / "pipeline" / "webcam_ingest_basic.py")], env, "Basic Ingest", procs)

        print("\n[!] basic_suite running. Monitoring process health...\n")
        
        while True:
            time.sleep(2)
            for p in procs:
                if p.poll() is not None:
                    print(f"\n[!] CRITICAL: A process has exited with code {p.returncode}. Shutting down suite.")
                    raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("\n[!] Stopping basic_suite...")
        for p in procs:
            try:
                # Use SIGINT first for graceful shutdown, then SIGTERM
                p.send_signal(signal.SIGINT)
                time.sleep(0.5)
                if p.poll() is None:
                    p.terminate()
            except Exception:
                pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
