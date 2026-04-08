import json
import os
import cv2
import numpy as np
import redis
from collections import deque
import threading
import time
from datetime import datetime, timezone

r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379)
sub = r.pubsub()
sub.subscribe("frames")

# { cam_id: deque([frames...], maxlen=150) } 
# 150 frames at 15fps = 10 seconds
buffer = {}
buffer_lock = threading.Lock()

# ── Detection overlay ─────────────────────────────────────────────────────────
_det_cache: dict = {}   # cam_id -> {"dets": [...], "ts": float, "fw": int, "fh": int}
_det_lock  = threading.Lock()
_DETS_TTL  = 2.0        # seconds before detections expire

_LABEL_COLOURS = {
    "person": (0, 220, 0),
    "face":   (0, 180, 255),
    "fire":   (0, 60,  255),
    "smoke":  (80, 80, 220),
}
_DEFAULT_COLOUR = (255, 180, 0)


def _detection_subscriber():
    """Background thread: keep _det_cache updated with latest detections."""
    ps = r.pubsub()
    ps.subscribe("detections")
    for msg in ps.listen():
        if msg["type"] != "message":
            continue
        try:
            payload = json.loads(msg["data"])
            cam = payload.get("cam") or ""
            if cam:
                finfo = payload.get("frame") or {}
                with _det_lock:
                    _det_cache[cam] = {
                        "dets": payload.get("detections") or [],
                        "ts":   time.time(),
                        "fw":   finfo.get("w", 640),
                        "fh":   finfo.get("h", 360),
                    }
        except Exception:
            pass


threading.Thread(target=_detection_subscriber, daemon=True).start()


def _draw_dets(frame: np.ndarray, cam_id: str) -> np.ndarray:
    """Draw bounding-box overlays on a cv2 BGR frame in-place."""
    with _det_lock:
        entry = _det_cache.get(cam_id)
    if not entry or (time.time() - entry["ts"]) > _DETS_TTL:
        return frame
    dets = entry["dets"]
    if not dets:
        return frame

    h, w = frame.shape[:2]
    det_w = entry.get("fw", w) or w
    det_h = entry.get("fh", h) or h
    sx = w / det_w
    sy = h / det_h

    for d in dets:
        if d.get("suppressed"):
            continue
        box = d.get("box")
        if not box or len(box) < 4:
            continue
        label = d.get("label", "?")
        conf  = d.get("conf", 0.0)
        if conf < 0.35:
            continue

        x1 = int(box[0] * sx)
        y1 = int(box[1] * sy)
        x2 = int(box[2] * sx)
        y2 = int(box[3] * sy)

        lbl_key = label.lower()
        colour  = next((v for k, v in _LABEL_COLOURS.items() if k in lbl_key), _DEFAULT_COLOUR)

        cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 2)

        text = f"{label}  {conf:.0%}"
        font  = cv2.FONT_HERSHEY_SIMPLEX
        fs    = 0.52
        (tw, th), bl = cv2.getTextSize(text, font, fs, 1)
        ty = max(y1 - 4, th + 4)
        cv2.rectangle(frame, (x1, ty - th - bl - 2), (x1 + tw + 4, ty + 2), colour, cv2.FILLED)
        cv2.putText(frame, text, (x1 + 2, ty - bl), font, fs, (10, 10, 10), 1, cv2.LINE_AA)

    return frame

_PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_PIPELINE_DIR)
CLIP_DIR = os.getenv(
    "CLIP_DIR", os.path.join(_REPO_ROOT, "storage", "clips")
)
os.makedirs(CLIP_DIR, exist_ok=True)

def save_clip_worker():
    ps = r.pubsub()
    ps.subscribe("save_clip")
    print("[*] Clip Saver Worker started")
    for msg in ps.listen():
        if msg["type"] != "message":
            continue
        # data format: cam_id|alert_type
        try:
            cam_id, alert_type = msg["data"].decode().split("|")
            timestamp = int(time.time())
            filename = f"{CLIP_DIR}/{cam_id}_{alert_type}_{timestamp}.mp4"
            
            with buffer_lock:
                if cam_id not in buffer or not buffer[cam_id]:
                    print(f"[!] No buffered frames for {cam_id}")
                    continue
                frames = list(buffer[cam_id])
            
            if not frames:
                continue
                
            h, w = frames[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(filename, fourcc, 10.0, (w, h))
            
            for f in frames:
                out.write(f)
            out.release()
            print(f"[+] Saved alert clip: {filename}")
            basename = os.path.basename(filename)
            try:
                r.publish(
                    "alerts",
                    json.dumps(
                        {
                            "type": "clip_ready",
                            "cam": cam_id,
                            "cid": cam_id,
                            "label": f"Recording saved: {basename}",
                            "severity": "info",
                            "clip": f"/clips/{basename}",
                            "clip_file": basename,
                            "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                        }
                    ),
                )
            except Exception as ex:
                print(f"[!] clip_ready publish: {ex}")

        except Exception as e:
            print(f"[!] Clip saving error: {e}")

threading.Thread(target=save_clip_worker, daemon=True).start()

print("[*] buffering frames...")
for msg in sub.listen():
    if msg["type"] != "message":
        continue
    try:
        cid_b, img_b = msg["data"].split(b"|", 1)
        cid = cid_b.decode()
        frame = cv2.imdecode(np.frombuffer(img_b, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            continue
            
        with buffer_lock:
            if cid not in buffer:
                buffer[cid] = deque(maxlen=100) # ~10 seconds of history
            buffer[cid].append(_draw_dets(frame, cid))   # annotate before storing
    except Exception as e:
        print(f"[!] Buffering error: {e}")
