import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import redis
import yaml

r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379)

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)

from zone_logic import (  # noqa: E402
    ZoneRuntimeState,
    bbox_center_norm,
    count_persons_in_zone,
    count_vehicles_in_zone,
    infer_frame_size,
    point_in_polygon,
    schedule_allows,
)

_DETECTION_CONFIG_PATH = os.environ.get(
    "DETECTION_CONFIG", os.path.join(os.path.dirname(_DIR), "config", "detection_config.basic.yaml")
)
_ZONES_PATH = os.environ.get("ZONES_CONFIG", os.path.join(os.path.dirname(_DIR), "config", "zones.basic.yaml"))


def _load_yaml(path: str) -> Dict[str, Any]:
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


CFG = _load_yaml(_DETECTION_CONFIG_PATH)
RULES_ENGINE = CFG.get("rules_engine") or {}
ENGINE_COOLDOWN = float(RULES_ENGINE.get("alert_cooldown_seconds", 25))
ENABLE_PERSON_FEED = bool(RULES_ENGINE.get("enable_generic_person_feed", False))
CLIP_ON_TYPES: Set[str] = set(
    str(x) for x in (RULES_ENGINE.get("clip_on_alert_types") or [])
)

VEHICLE_POLICY = CFG.get("vehicle_policy") or {"mode": "all", "deny": [], "allow": []}
OPEN_VOCAB_CUSTOM: List[Dict[str, Any]] = list(CFG.get("open_vocab_custom") or [])


def _load_fire_alert_keywords():
    defaults = [
        "fire",
        "smoke",
        "flame",
        "burning",
        "blaze",
        "haze",
        "lighter",
        "spark",
        "candle",
    ]
    kw = CFG.get("fire_alert_keywords")
    return tuple(k.lower() for k in (kw if kw else defaults))


FIRE_ALERT_KW = _load_fire_alert_keywords()


def _load_vehicle_alert_types():
    defaults = [
        "car",
        "bus",
        "truck",
        "auto rickshaw",
        "motorcycle",
        "scooter",
    ]
    vehicles = CFG.get("vehicles") or defaults
    out = {}
    for v in vehicles:
        key = (v or "").strip().lower()
        if not key:
            continue
        slug = key.replace(" ", "_").replace("-", "_")
        out[key] = f"vehicle_{slug}"
    return out


VEHICLE_ALERT_TYPES = _load_vehicle_alert_types()
VEHICLE_LABEL_SET: Set[str] = set(VEHICLE_ALERT_TYPES.keys())
print(
    f"[*] basic_suite rules: vehicle alert types: {list(VEHICLE_ALERT_TYPES.values())}",
    flush=True,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ALERT_SNAPSHOT_DIR = Path(
    os.getenv("ALERT_SNAPSHOT_DIR", str(_REPO_ROOT / "storage" / "alert_snapshots"))
)
LEGACY_ALERTS_IMAGES_ONLY = os.getenv("BASIC_SUITE_ALERTS_IMAGES_ONLY", "") == "1"
ALERT_SNAPSHOTS = os.getenv("BASIC_SUITE_ALERT_SNAPSHOTS", "1") == "1"
OPERATOR_CLIPS = os.getenv("BASIC_SUITE_OPERATOR_CLIPS", "1") == "1"
if LEGACY_ALERTS_IMAGES_ONLY:
    OPERATOR_CLIPS = False
    print(
        "[*] basic_suite rules: legacy BASIC_SUITE_ALERTS_IMAGES_ONLY=1 → operator MP4 clips disabled",
        flush=True,
    )
if ALERT_SNAPSHOTS:
    print("[*] basic_suite rules: alert JPEG snapshots ON (all roles see evidence images)", flush=True)
if OPERATOR_CLIPS:
    print("[*] basic_suite rules: operator clip pipeline ON (save_clip → MP4 for internal roles)", flush=True)

ZONES_CFG = _load_yaml(_ZONES_PATH).get("cameras") or {}
zone_state = ZoneRuntimeState()
_last_emit: Dict[str, float] = {}

WEBHOOK_URLS = [
    u.strip()
    for u in os.getenv("WEBHOOK_URLS", os.getenv("WEBHOOK_URL", "")).split(",")
    if u.strip()
]
if WEBHOOK_URLS:
    print(f"[*] rules: webhooks enabled ({len(WEBHOOK_URLS)} URL(s))", flush=True)


def _vehicle_allowed(label: str) -> bool:
    lab = (label or "").strip().lower()
    mode = (VEHICLE_POLICY.get("mode") or "all").lower()
    if mode == "all":
        return True
    deny = {str(x).strip().lower() for x in (VEHICLE_POLICY.get("deny") or [])}
    allow = {str(x).strip().lower() for x in (VEHICLE_POLICY.get("allow") or [])}
    if mode == "deny_list":
        return lab not in deny
    if mode == "allow_list":
        return lab in allow
    return True


def _cooldown_ok(key: str, seconds: float) -> bool:
    now = time.time()
    if now - _last_emit.get(key, 0.0) < seconds:
        return False
    _last_emit[key] = now
    return True


def _safe_alert_slug(s: str) -> str:
    return (re.sub(r"[^a-zA-Z0-9_-]+", "_", (s or ""))[:64]).strip("_") or "x"


def _attach_alert_snapshot(cam: str, alert_type: str, payload: Dict[str, Any]) -> None:
    if not ALERT_SNAPSHOTS:
        return
    try:
        raw = r.get(f"bscam:{cam}:last_jpg")
    except Exception as e:
        print(f"[!] snapshot redis read failed: {e}", flush=True)
        return
    if not raw:
        return
    ALERT_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    fn = f"{int(time.time() * 1000)}_{_safe_alert_slug(cam)}_{_safe_alert_slug(alert_type)}.jpg"
    path = ALERT_SNAPSHOT_DIR / fn
    try:
        path.write_bytes(raw)
        payload["image"] = f"/alert-images/{fn}"
    except OSError as e:
        print(f"[!] alert snapshot write failed: {e}", flush=True)


def _maybe_save_clip(cam: str, alert_type: str) -> None:
    if not OPERATOR_CLIPS:
        return
    if alert_type not in CLIP_ON_TYPES:
        return
    try:
        r.publish("save_clip", f"{cam}|{alert_type}")
    except Exception as e:
        print(f"[!] save_clip publish failed: {e}", flush=True)


def _webhook_post(payload: Dict[str, Any]) -> None:
    if not WEBHOOK_URLS:
        return
    body = json.dumps(payload).encode("utf-8")
    for url in WEBHOOK_URLS:
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=6)
        except urllib.error.URLError as e:
            print(f"[!] webhook failed {url}: {e}", flush=True)
        except Exception as e:
            print(f"[!] webhook error {url}: {e}", flush=True)


def _publish_alert(
    *,
    alert_type: str,
    cam: str,
    label: str,
    severity: str = "info",
    dedupe_key: Optional[str] = None,
    **extra: Any,
) -> bool:
    cam = str(cam)
    dk = dedupe_key or f"{alert_type}:{cam}:{label}"
    if not _cooldown_ok(dk, ENGINE_COOLDOWN):
        return False

    payload = {
        "type": alert_type,
        "cam": cam,
        "cid": cam,
        "label": label,
        "severity": severity,
        "ts": datetime.utcnow().isoformat() + "Z",
        **extra,
    }
    _attach_alert_snapshot(cam, alert_type, payload)
    r.publish("alerts", json.dumps(payload))
    _maybe_save_clip(cam, alert_type)
    _webhook_post(payload)
    return True


def _fire_smoke_match(label_lower: str) -> bool:
    return any(k in label_lower for k in FIRE_ALERT_KW)


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
        crowd_max = z.get("crowd_max")
        loiter_sec = float(z.get("loitering_seconds") or 0)
        loiter_min_p = int(z.get("loitering_min_persons") or 1)
        loiter_effective = count if count >= max(1, loiter_min_p) else 0

        hoa_labels = z.get("hoa_vehicle_labels")
        if isinstance(hoa_labels, list) and hoa_labels:
            hoa_set = {str(x).strip().lower() for x in hoa_labels if str(x).strip()}
        else:
            hoa_set = set(VEHICLE_LABEL_SET)
        if bool(z.get("hoa_vehicle_violation") or z.get("no_vehicles_in_zone")):
            vcount = count_vehicles_in_zone(detections, w, h, poly, hoa_set)
            if vcount > 0:
                hk = f"hoa:{cam}:{zid}"
                _publish_alert(
                    alert_type="hoa_vehicle_violation",
                    cam=cam,
                    label=f"Vehicle in restricted area ({vcount}) — {name}",
                    severity="warning",
                    dedupe_key=hk,
                    zone_id=zid,
                    zone_name=name,
                    vehicles_in_zone=vcount,
                    rule="hoa_vehicle",
                )

        if restricted and count > 0:
            ik = f"intrusion:{cam}:{zid}"
            _publish_alert(
                alert_type="zone_intrusion",
                cam=cam,
                label=f"Restricted zone: {name}",
                severity="critical",
                dedupe_key=ik,
                zone_id=zid,
                zone_name=name,
                persons_in_zone=count,
            )

        if crowd_max is not None:
            try:
                cm = int(crowd_max)
            except (TypeError, ValueError):
                cm = 0
            if cm > 0 and count > cm:
                ck = f"crowd:{cam}:{zid}"
                _publish_alert(
                    alert_type="zone_crowd",
                    cam=cam,
                    label=f"Crowd threshold ({count}>{cm}) — {name}",
                    severity="warning",
                    dedupe_key=ck,
                    zone_id=zid,
                    zone_name=name,
                    persons_in_zone=count,
                    crowd_max=cm,
                )

        if loiter_sec > 0:
            if zone_state.loitering_should_fire(cam, zid, loiter_effective, loiter_sec):
                lk = f"loiter:{cam}:{zid}"
                if _publish_alert(
                    alert_type="zone_loitering",
                    cam=cam,
                    label=f"Loitering ({int(loiter_sec)}s+) — {name}",
                    severity="warning",
                    dedupe_key=lk,
                    zone_id=zid,
                    zone_name=name,
                    persons_in_zone=count,
                ):
                    zone_state.clear_loiter(cam, zid)


def _open_vocab_custom_match(label_lower: str) -> Optional[Dict[str, Any]]:
    for rule in OPEN_VOCAB_CUSTOM:
        m = (rule.get("match") or "").strip().lower()
        if m and m in label_lower:
            return rule
    return None


def _person_in_any_zone(cam: str, d: Dict[str, Any], w: int, h: int) -> bool:
    cam_cfg = ZONES_CFG.get(cam) or ZONES_CFG.get(str(cam)) or {}
    box = d.get("box")
    if not box or len(box) < 4:
        return False
    cx, cy = bbox_center_norm(box, w, h)
    for z in cam_cfg.get("zones") or []:
        poly = z.get("polygon") or []
        if len(poly) >= 3 and point_in_polygon(cx, cy, poly):
            return True
    return False


def _rules_main_loop() -> None:
    sub = r.pubsub()
    sub.subscribe("detections")
    print(
        "[*] basic_suite rules: subscribed to Redis 'detections' → will publish 'alerts'",
        flush=True,
    )
    try:
        for msg in sub.listen():
            if msg["type"] != "message":
                continue
            data = json.loads(msg["data"])
            cam = data.get("cam", "unknown")
            detections: List[Dict[str, Any]] = data.get("detections") or []
            frame = data.get("frame") or {}
            w = int(frame.get("w") or 0)
            h = int(frame.get("h") or 0)
            if w <= 0 or h <= 0:
                w, h = infer_frame_size(detections)

            _process_zones(cam, detections, w, h)

            for d in detections:
                raw_label = d.get("label", "") or ""
                label = raw_label.lower()
                cls_id = d.get("cls", -1)

                if d.get("suppressed"):
                    # Skip alerts for detections suppressed by Smart Filtering
                    continue

                if _fire_smoke_match(label):
                    _publish_alert(
                        alert_type="fire_hazard",
                        cam=cam,
                        label=raw_label.strip() or "Fire / smoke",
                        severity="critical",
                        dedupe_key=f"fire:{cam}",
                    )
                    continue

                custom = _open_vocab_custom_match(label)
                if custom:
                    at = custom.get("alert_type") or "open_vocab"
                    lab = custom.get("label") or raw_label.strip()
                    dk = f"ov:{cam}:{at}:{custom.get('match')}"
                    _publish_alert(
                        alert_type=at,
                        cam=cam,
                        label=str(lab),
                        severity="info",
                        dedupe_key=dk,
                        match=custom.get("match"),
                    )
                    continue

                if label in ["person", "face"]:
                    if ENABLE_PERSON_FEED or _person_in_any_zone(cam, d, w, h):
                        _publish_alert(
                            alert_type="intelligence_feed",
                            cam=cam,
                            label=f"{label.capitalize()} detected",
                            severity="info",
                            dedupe_key=f"personfeed:{cam}:{label}",
                        )
                    continue

                if label in ["dog", "cat", "monkey", "snake", "reptile"] or (
                    label == "cow" or cls_id == 3
                ):
                    animal = label if label else "unknown_animal"
                    _publish_alert(
                        alert_type="animal_intrusion",
                        cam=cam,
                        label=f"Animal: {animal.replace('_', ' ')}",
                        severity="warning",
                        dedupe_key=f"animal:{cam}:{animal}",
                        animal=animal,
                    )
                    continue

                if label in VEHICLE_ALERT_TYPES:
                    if not _vehicle_allowed(label):
                        continue
                    atype = VEHICLE_ALERT_TYPES[label]
                    pretty = raw_label.strip() or label
                    _publish_alert(
                        alert_type=atype,
                        cam=cam,
                        label=f"{pretty} detected",
                        severity="info",
                        dedupe_key=f"veh:{cam}:{atype}",
                        vehicle=label,
                    )
                    continue

                if label == "license plate":
                    plate_text = d.get("text", "Unknown")
                    _publish_alert(
                        alert_type="security_alert",
                        cam=cam,
                        label=f"License Plate: {plate_text}",
                        severity="info",
                        dedupe_key=f"plate:{cam}",
                        plate=plate_text,
                    )
    except KeyboardInterrupt:
        print("\n[*] basic_suite rules: stopped", flush=True)


if __name__ == "__main__":
    _rules_main_loop()
