import json
import os
import time
import re
from datetime import datetime
import redis
import cv2
import numpy as np

r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379)

_last_emit = {}
COOLDOWN = 15

def _cooldown_ok(key: str) -> bool:
    now = time.time()
    if now - _last_emit.get(key, 0.0) < COOLDOWN:
        return False
    _last_emit[key] = now
    return True

def classify_heuristically(cam, detections, frame_info):
    """
    Apply rules to detections or frame properties to 'classify' 
    unidentified events (Fire, Animals, Vehicles).
    """
    alerts = []
    
    # Example Heuristic: Large detection with no label -> Vehicle?
    # (In OpenCV suite, most detections will have labels, but we can add logic)
    
    # 1. Fire Heuristic (Simulated - in a real app, we'd check pixels)
    # We look for any 'orange/red' blobs if we had them. 
    # For now, let's look for specific labels if we added them to detect_opencv.
    
    # 2. Animal Heuristic
    # If a 'person' detection is actually very small and low to ground
    for d in detections:
        box = d.get("box", [0, 0, 0, 0])
        w = box[2] - box[0]
        h = box[3] - box[1]
        
        # If it's labeled 'person' but aspect ratio is more like a dog (w > h)
        if d["label"] == "person" and w > (h * 1.5) and h < 100:
            d["label"] = "animal (heuristic)"
            d["type"] = "animal_intrusion"

    return detections

def process_detections(msg_data):
    data = json.loads(msg_data)
    cam = data.get("cam", "unknown")
    detections = data.get("detections", [])
    
    # Apply Classification Rules
    detections = classify_heuristically(cam, detections, data.get("frame", {}))
    
    for d in detections:
        label = d.get("label", "unknown")
        alert_type = d.get("type", "intelligence_feed")
        
        # Map labels to alert types if not already set
        if label == "face":
            alert_type = "face_detected"
        elif label == "person":
            alert_type = "zone_intrusion"
        elif "animal" in label:
            alert_type = "animal_intrusion"
            
        dk = f"{alert_type}:{cam}"
        if _cooldown_ok(dk):
            payload = {
                "type": alert_type,
                "cam": cam,
                "label": f"OpenCV: {label.capitalize()}",
                "severity": "info" if "face" in label else "warning",
                "ts": datetime.utcnow().isoformat() + "Z",
                "box": d.get("box")
            }
            r.publish("alerts", json.dumps(payload))
            print(f"[*] Alert Published: {alert_type} on {cam}", flush=True)

def main():
    sub = r.pubsub()
    sub.subscribe("detections")
    print("[*] OpenCV Rules Engine listening to 'detections' channel...", flush=True)
    
    for msg in sub.listen():
        if msg["type"] == "message":
            process_detections(msg["data"])

if __name__ == "__main__":
    main()
