import json
import os
import time
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import redis
import yaml

r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379)

# Paths
_DIR = os.path.dirname(os.path.abspath(__file__))
# Ensure basic_suite is in path for zone_logic imports
_REPO_ROOT = Path(_DIR).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from basic_suite.pipeline.zone_logic import (
    ZoneRuntimeState,
    bbox_center_norm,
    count_persons_in_zone,
    schedule_allows,
)

_DETECTION_CONFIG_PATH = os.environ.get(
    "DETECTION_CONFIG", os.path.join(os.path.dirname(_DIR), "config", "detection_config.opencv.yaml")
)
_ZONES_PATH = os.environ.get("ZONES_CONFIG", os.path.join(os.path.dirname(_DIR), "config", "zones.basic.yaml"))

def _load_yaml(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}

CFG = _load_yaml(_DETECTION_CONFIG_PATH)
RULES_ENGINE = CFG.get("rules_engine") or {}
ENGINE_COOLDOWN = float(RULES_ENGINE.get("alert_cooldown_seconds", 15))
ENABLE_PERSON_FEED = bool(RULES_ENGINE.get("enable_generic_person_feed", True))

ZONES_CFG = _load_yaml(_ZONES_PATH).get("cameras") or {}
zone_state = ZoneRuntimeState()
_last_emit: Dict[str, float] = {}

print(f"[*] OpenCV Rules Engine started. Cooldown: {ENGINE_COOLDOWN}s", flush=True)

def _cooldown_ok(key: str, seconds: float) -> bool:
    now = time.time()
    if now - _last_emit.get(key, 0.0) < seconds:
        return False
    _last_emit[key] = now
    return True

def _publish_alert(
    *,
    alert_type: str,
    cam: str,
    label: str,
    severity: str = "info",
    dedupe_key: Optional[str] = None,
    **extra: Any,
) -> bool:
    dk = dedupe_key or f"{alert_type}:{cam}:{label}"
    if not _cooldown_ok(dk, ENGINE_COOLDOWN):
        return False

    payload = {
        "type": alert_type,
        "cam": cam,
        "label": label,
        "severity": severity,
        "ts": datetime.utcnow().isoformat() + "Z",
        **extra,
    }
    r.publish("alerts", json.dumps(payload))
    return True

def _process_zones(cam: str, detections: List[Dict[str, Any]], w: int, h: int) -> None:
    cam_cfg = ZONES_CFG.get(cam) or ZONES_CFG.get(str(cam))
    if not cam_cfg:
        return
    zones = cam_cfg.get("zones") or []
    for z in zones:
        zid = str(z.get("id") or "zone")
        name = z.get("name") or zid
        poly = z.get("polygon") or []
        if len(poly) < 3:
            continue

        sched = z.get("schedule")
        if not schedule_allows(sched if isinstance(sched, dict) else None):
            continue

        count = count_persons_in_zone(detections, w, h, poly)
        restricted = bool(z.get("restricted", False))
        loiter_sec = float(z.get("loitering_seconds") or 0)

        if restricted and count > 0:
            _publish_alert(
                alert_type="zone_intrusion",
                cam=cam,
                label=f"OpenCV Restricted Zone: {name}",
                severity="critical",
                dedupe_key=f"intrusion:{cam}:{zid}",
                zone_id=zid,
                zone_name=name,
                persons_in_zone=count,
            )

        if loiter_sec > 0:
            if zone_state.loitering_should_fire(cam, zid, count, loiter_sec):
                if _publish_alert(
                    alert_type="zone_loitering",
                    cam=cam,
                    label=f"OpenCV Loitering ({int(loiter_sec)}s+) — {name}",
                    severity="warning",
                    dedupe_key=f"loiter:{cam}:{zid}",
                    zone_id=zid,
                    zone_name=name,
                    persons_in_zone=count,
                ):
                    zone_state.clear_loiter(cam, zid)

def classify_heuristically(detections):
    """Refine labels based on heuristic rules (Small low objects -> animals)."""
    h_cfg = (CFG.get("opencv", {}).get("heuristics") or {})
    max_h = h_cfg.get("animal_max_height", 100)
    min_ar = h_cfg.get("animal_min_aspect_ratio", 1.5)
    
    for d in detections:
        if d["label"] == "person":
            box = d.get("box", [0, 0, 0, 0])
            w = box[2] - box[0]
            h = box[3] - box[1]
            if w > (h * min_ar) and h < max_h:
                d["label"] = "animal"
    return detections

def process_detections(msg_data):
    try:
        data = json.loads(msg_data)
    except: return
    
    cam = data.get("cam", "unknown")
    detections = data.get("detections") or []
    frame = data.get("frame") or {}
    w, h = frame.get("w", 640), frame.get("h", 360)
    
    # 1. Zone Logic (Intrusion / Loitering)
    _process_zones(cam, detections, w, h)
    
    # 2. Heuristic checks
    detections = classify_heuristically(detections)
    
    # 3. Specific Alerts
    for d in detections:
        label = d.get("label", "").lower()
        if label == "fire":
            _publish_alert(
                alert_type="fire_hazard",
                cam=cam,
                label="OpenCV: Fire/Smoke Detected (Heuristic)",
                severity="critical",
                dedupe_key=f"fire:{cam}"
            )
        elif label == "animal":
            _publish_alert(
                alert_type="animal_intrusion",
                cam=cam,
                label="OpenCV: Animal Detected (Heuristic)",
                severity="warning",
                dedupe_key=f"animal:{cam}"
            )
        elif label in ["person", "face"] and ENABLE_PERSON_FEED:
             _publish_alert(
                alert_type="intelligence_feed",
                cam=cam,
                label=f"OpenCV: {label.capitalize()} detected",
                severity="info",
                dedupe_key=f"personfeed:{cam}:{label}"
            )

def main():
    sub = r.pubsub()
    sub.subscribe("detections")
    print("[*] OpenCV Rules Engine running...", flush=True)
    
    for msg in sub.listen():
        if msg["type"] == "message":
            process_detections(msg["data"])

if __name__ == "__main__":
    main()
