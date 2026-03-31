import os
import sys
import time

import cv2
import redis
import yaml

_HEARTBEAT = float(os.getenv("PIPELINE_HEARTBEAT_SEC", "5"))
FRAME_CHANNEL = os.getenv("FRAME_CHANNEL", "frames")

r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379)

_CFG = os.getenv(
    "BASIC_CAMERAS_CONFIG",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "cameras.basic.yaml"),
)
with open(_CFG) as f:
    CAMS = (yaml.safe_load(f) or {}).get("cameras", {})

# Optional runtime override for quick camera switching without editing YAML.
# Example:
#   export BASIC_MAIN_CAMERA="rtsp://user:pass@192.168.1.55:554/cam/realmonitor?channel=1&subtype=0"
_env_main = os.getenv("BASIC_MAIN_CAMERA")
if _env_main:
    CAMS["main"] = _env_main


def open_capture(source):
    if isinstance(source, bool):
        source = int(source)
    if isinstance(source, int):
        if sys.platform == "darwin" and hasattr(cv2, "CAP_AVFOUNDATION"):
            return cv2.VideoCapture(source, cv2.CAP_AVFOUNDATION)
        return cv2.VideoCapture(source)
    return cv2.VideoCapture(str(source))


def main():
    caps = {}
    seen_sources = set()

    for cid, src in CAMS.items():
        if src is None:
            continue
        # Support both old string and new dict format
        if isinstance(src, dict):
            src_val = src.get("stream_url", "")
        else:
            src_val = src
        
        if not src_val:
            continue

        key = (type(src_val).__name__, str(src_val))
        if key in seen_sources:
            print(f"[!] Skipping duplicate source {src_val!r} for '{cid}'")
            continue
        seen_sources.add(key)

        cap = open_capture(src_val)
        if not cap.isOpened():
            print(f"[!] Skipping '{cid}': cannot open source {src_val!r}")
            continue
        caps[cid] = cap


    if not caps:
        print(f"[!] No working sources in {_CFG}")
        sys.exit(1)

    print(f"[*] basic_suite ingest active: {list(caps.keys())}", flush=True)

    publishes = 0
    t0 = time.monotonic()
    while True:
        for cid, cap in caps.items():
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.resize(frame, (640, 360))
            ok, buf = cv2.imencode(".jpg", frame)
            if not ok:
                continue
            r.publish(FRAME_CHANNEL, cid.encode() + b"|" + buf.tobytes())
            publishes += 1

        now = time.monotonic()
        if now - t0 >= _HEARTBEAT:
            print(f"[*] basic_suite ingest: ~{publishes} JPEG / {_HEARTBEAT:.0f}s", flush=True)
            publishes = 0
            t0 = now
        time.sleep(0.01)


if __name__ == "__main__":
    main()
