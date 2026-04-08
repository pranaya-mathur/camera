#!/usr/bin/env python3
"""
Incident Logger
===============
Subscribes to the 'detections' and 'alerts' Redis channels and writes
structured JSON-Lines (.jsonl) log files to  storage/logs/.

File layout
-----------
  storage/logs/
    detections_YYYY-MM-DD.jsonl   ← one line per detection event
    alerts_YYYY-MM-DD.jsonl       ← one line per alert / clip-ready event

Each line is valid JSON so the files are easy to query with  jq, pandas, etc.

Usage
-----
  REDIS_HOST=localhost python3 pipeline/incident_logger.py

Environment variables
---------------------
  REDIS_HOST            default: localhost
  REDIS_PORT            default: 6379
  LOG_DIR               default: storage/logs  (relative to repo root)
  LOG_CONF_THRESHOLD    minimum confidence to log a detection (default: 0.30)
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import redis

# ── config ─────────────────────────────────────────────────────────────────────
REDIS_HOST      = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT      = int(os.getenv("REDIS_PORT", "6379"))
CONF_THRESHOLD  = float(os.getenv("LOG_CONF_THRESHOLD", "0.30"))

_REPO = Path(__file__).resolve().parent.parent
LOG_DIR = Path(os.getenv("LOG_DIR", str(_REPO / "storage" / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)


# ── helpers ────────────────────────────────────────────────────────────────────
def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _write(subdir: str, record: dict) -> None:
    """Append one JSON-Lines record to today's log file."""
    path = LOG_DIR / f"{subdir}_{_today()}.jsonl"
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _ts() -> tuple[str, float]:
    """Return (ISO-8601 string, unix epoch float) for right now."""
    now = datetime.now(timezone.utc)
    return now.isoformat().replace("+00:00", "Z"), now.timestamp()


# ── main loop ──────────────────────────────────────────────────────────────────
def main() -> None:
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    ps  = r.pubsub()
    ps.subscribe("detections", "alerts")

    print(f"[*] Incident Logger — writing logs to {LOG_DIR}", flush=True)
    print(f"    confidence threshold : {CONF_THRESHOLD}", flush=True)

    for msg in ps.listen():
        if msg["type"] != "message":
            continue

        channel = msg["channel"]
        try:
            payload = json.loads(msg["data"])
        except (json.JSONDecodeError, TypeError):
            continue

        ts_iso, ts_epoch = _ts()

        # ── detections channel ────────────────────────────────────────────────
        if channel == "detections":
            cam       = payload.get("cam", "unknown")
            finfo     = payload.get("frame") or {}
            dets      = payload.get("detections") or []

            for d in dets:
                if d.get("suppressed"):
                    continue
                conf = float(d.get("conf", 0.0))
                if conf < CONF_THRESHOLD:
                    continue

                record = {
                    "event":    "detection",
                    "ts":       ts_iso,
                    "epoch":    round(ts_epoch, 3),
                    "cam":      cam,
                    "label":    d.get("label", "unknown"),
                    "conf":     round(conf, 4),
                    "conf_pct": f"{conf:.1%}",
                    "box":      d.get("box"),          # [x1, y1, x2, y2] absolute px
                    "model":    d.get("model", "unknown"),
                    "frame_w":  finfo.get("w"),
                    "frame_h":  finfo.get("h"),
                }
                _write("detections", record)

        # ── alerts channel ────────────────────────────────────────────────────
        elif channel == "alerts":
            alert_type = payload.get("type", "unknown")
            cam        = payload.get("cam") or payload.get("cid", "unknown")

            record: dict = {
                "event":      "alert",
                "ts":         ts_iso,
                "epoch":      round(ts_epoch, 3),
                "cam":        cam,
                "alert_type": alert_type,
                "label":      payload.get("label", ""),
                "severity":   payload.get("severity", ""),
            }

            # clip_ready events get extra recording metadata
            if alert_type == "clip_ready":
                record["clip_file"]  = payload.get("clip_file", "")
                record["clip_url"]   = payload.get("clip", "")
                record["saved_at"]   = payload.get("ts", ts_iso)

            _write("alerts", record)
            print(
                f"[ALERT] {ts_iso}  cam={cam}  type={alert_type}"
                + (f"  file={record.get('clip_file')}" if alert_type == "clip_ready" else f"  {record['label']}"),
                flush=True,
            )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[*] Incident Logger stopped.", flush=True)
        sys.exit(0)
