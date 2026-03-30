import json
import os
from datetime import datetime

import redis
import yaml

r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379)
sub = r.pubsub()
sub.subscribe("detections")

print(
    "[*] rules: subscribed to Redis 'detections' → will publish 'alerts'",
    flush=True,
)

_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_fire_alert_keywords():
    path = os.environ.get("DETECTION_CONFIG", os.path.join(_DIR, "detection_config.yaml"))
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
    if not os.path.isfile(path):
        return defaults
    with open(path) as f:
        cfg = yaml.safe_load(f) or {}
    kw = cfg.get("fire_alert_keywords")
    return kw if kw else defaults


FIRE_ALERT_KW = tuple(k.lower() for k in _load_fire_alert_keywords())


def _load_vehicle_alert_types():
    """Map detection_config.yaml `vehicles` labels → distinct alert_type (e.g. vehicle_car)."""
    path = os.environ.get("DETECTION_CONFIG", os.path.join(_DIR, "detection_config.yaml"))
    defaults = [
        "car",
        "bus",
        "truck",
        "auto rickshaw",
        "motorcycle",
        "scooter",
    ]
    if not os.path.isfile(path):
        vehicles = defaults
    else:
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}
        vehicles = cfg.get("vehicles") or defaults
    out = {}
    for v in vehicles:
        key = (v or "").strip().lower()
        if not key:
            continue
        slug = key.replace(" ", "_").replace("-", "_")
        out[key] = f"vehicle_{slug}"
    return out


VEHICLE_ALERT_TYPES = _load_vehicle_alert_types()
print(
    f"[*] rules: vehicle alert types: {list(VEHICLE_ALERT_TYPES.values())}",
    flush=True,
)


def _fire_smoke_match(label_lower: str) -> bool:
    return any(k in label_lower for k in FIRE_ALERT_KW)


def _publish_alert(*, alert_type: str, cam: str, label: str, **extra):
    cam = str(cam)
    payload = {
        "type": alert_type,
        "cam": cam,
        "cid": cam,
        "label": label,
        "ts": datetime.utcnow().isoformat() + "Z",
        **extra,
    }
    r.publish("alerts", json.dumps(payload))


for msg in sub.listen():
    if msg["type"] != "message":
        continue
    data = json.loads(msg["data"])
    cam = data.get("cam", "unknown")

    for d in data.get("detections", []):
        raw_label = d.get("label", "") or ""
        label = raw_label.lower()
        cls_id = d.get("cls", -1)

        if label in ["person", "face"]:
            _publish_alert(
                alert_type="intelligence_feed",
                cam=cam,
                label=f"{label.capitalize()} detected",
            )

        elif label in ["dog", "cat", "monkey", "snake", "reptile"] or (
            label == "cow" or cls_id == 3
        ):
            animal = label if label else "unknown_animal"
            _publish_alert(
                alert_type="animal_intrusion",
                cam=cam,
                label=f"Animal: {animal.replace('_', ' ')}",
                animal=animal,
            )

        elif label in VEHICLE_ALERT_TYPES:
            atype = VEHICLE_ALERT_TYPES[label]
            pretty = raw_label.strip() or label
            _publish_alert(
                alert_type=atype,
                cam=cam,
                label=f"{pretty} detected",
                vehicle=label,
            )

        elif _fire_smoke_match(label):
            _publish_alert(
                alert_type="fire_hazard",
                cam=cam,
                label=raw_label.strip() or "Fire / smoke",
            )

        elif label == "license plate":
            plate_text = d.get("text", "Unknown") # If LPR was active
            _publish_alert(
                alert_type="security_alert",
                cam=cam,
                label=f"License Plate: {plate_text}",
                plate=plate_text
            )
