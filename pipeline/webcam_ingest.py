import os
import sys
import time

import cv2
import redis
import yaml

_HEARTBEAT = float(os.getenv("PIPELINE_HEARTBEAT_SEC", "5"))

r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379)

cfg_path = os.path.join(os.path.dirname(__file__), "cameras.yaml")
with open(cfg_path) as f:
    CAMS = yaml.safe_load(f)["cameras"]


def open_capture(source):
    """Open a camera: int index (local) or str (RTSP, file path, URL)."""
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
        key = (type(src).__name__, str(src))
        if key in seen_sources:
            print(
                f"[!] Skipping duplicate source {src!r} for '{cid}' "
                "(use one name per physical stream)."
            )
            continue
        seen_sources.add(key)

        cap = open_capture(src)
        if not cap.isOpened():
            print(f"[!] Skipping '{cid}': cannot open source {src!r}")
            if sys.platform == "darwin":
                print(
                    "    macOS: System Settings → Privacy & Security → Camera — "
                    "enable the app that runs this script (Terminal, Cursor, …)."
                )
            continue
        caps[cid] = cap

    if not caps:
        print("[!] No working camera sources. Edit pipeline/cameras.yaml and check permissions.")
        sys.exit(1)

    print(
        f"[*] Ingestion active for {len(caps)} source(s): {list(caps.keys())}",
        flush=True,
    )

    loops = 0
    publishes = 0
    t0 = time.monotonic()
    while True:
        for cid, cap in caps.items():
            ret, frame = cap.read()
            if not ret:
                continue
            frame = cv2.resize(frame, (640, 360))
            _, buf = cv2.imencode(".jpg", frame)
            r.publish("frames", cid.encode() + b"|" + buf.tobytes())
            publishes += 1
        loops += 1
        now = time.monotonic()
        if now - t0 >= _HEARTBEAT:
            print(
                f"[*] ingest: published ~{publishes} JPEG frames in last {_HEARTBEAT:.0f}s "
                f"({len(caps)} camera(s))",
                flush=True,
            )
            publishes = 0
            t0 = now
        time.sleep(0.01)


if __name__ == "__main__":
    main()
