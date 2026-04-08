import os
import sys
import time

# Set before `import cv2` so OpenCV's FFmpeg backend picks up RTSP options (TCP avoids many UDP timeouts).
_default_rtsp = os.getenv("BASIC_RTSP_FFMPEG_OPTIONS", "rtsp_transport;tcp")
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", _default_rtsp)

import cv2
import redis
import yaml

_HEARTBEAT = float(os.getenv("PIPELINE_HEARTBEAT_SEC", "5"))
FRAME_CHANNEL = os.getenv("FRAME_CHANNEL", "frames")

r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379)


def _cfg_path() -> str:
    return os.getenv(
        "BASIC_CAMERAS_CONFIG",
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "cameras.basic.yaml"),
    )


def load_cameras_dict() -> tuple[dict, str]:
    """
    Build camera map at runtime (not at import) so subprocess env vars are always visible.
    """
    cfg_path = _cfg_path()
    with open(cfg_path) as f:
        cams = (yaml.safe_load(f) or {}).get("cameras", {}) or {}

    _env_main = os.getenv("BASIC_MAIN_CAMERA")
    if _env_main:
        if _env_main.isdigit():
            cams["main"] = {"stream_url": int(_env_main)}
        else:
            cams["main"] = {"stream_url": _env_main}
    elif os.getenv("BASIC_SUITE_USE_WEBCAM") == "1":
        cams["main"] = {"stream_url": 0}

    return cams, cfg_path


def open_capture(source):
    if isinstance(source, bool):
        source = int(source)
    if isinstance(source, int):
        if sys.platform == "darwin" and hasattr(cv2, "CAP_AVFOUNDATION"):
            return cv2.VideoCapture(source, cv2.CAP_AVFOUNDATION)
        return cv2.VideoCapture(source)
    s = str(source)
    if s.lower().startswith("rtsp://") and hasattr(cv2, "CAP_FFMPEG"):
        return cv2.VideoCapture(s, cv2.CAP_FFMPEG)
    return cv2.VideoCapture(s)


def main():
    CAMS, _CFG = load_cameras_dict()
    print(
        "[*] basic_suite ingest env: "
        f"BASIC_MAIN_CAMERA={os.getenv('BASIC_MAIN_CAMERA')!r} "
        f"BASIC_SUITE_USE_WEBCAM={os.getenv('BASIC_SUITE_USE_WEBCAM')!r} "
        f"OPENCV_FFMPEG_CAPTURE_OPTIONS={os.getenv('OPENCV_FFMPEG_CAPTURE_OPTIONS')!r}",
        flush=True,
    )

    caps = {}
    seen_sources = set()

    for cid, src in CAMS.items():
        if src is None:
            continue
        if isinstance(src, dict):
            src_val = src.get("stream_url", "")
        else:
            src_val = src

        if not src_val and src_val != 0:
            continue

        key = (type(src_val).__name__, str(src_val))
        if key in seen_sources:
            print(f"[!] Skipping duplicate source {src_val!r} for '{cid}'")
            continue
        seen_sources.add(key)

        cap = open_capture(src_val)
        if not cap.isOpened():
            print(f"[!] Skipping '{cid}': cannot open source {src_val!r}")
            if isinstance(src_val, str) and src_val.lower().startswith("rtsp://"):
                print(
                    "[!] RTSP hints: ensure this machine can reach the NVR (same LAN/VPN), "
                    "credentials are correct, and try BASIC_RTSP_FFMPEG_OPTIONS "
                    '(e.g. "rtsp_transport;tcp|stimeout;60000000").',
                    flush=True,
                )
            continue
        caps[cid] = cap

    # macOS: index 0 sometimes fails; try 1 if webcam mode and nothing opened
    if not caps and os.getenv("BASIC_SUITE_USE_WEBCAM") == "1":
        for idx in (1, 2):
            cap = open_capture(idx)
            if cap.isOpened():
                caps["main"] = cap
                print(f"[*] basic_suite ingest: using camera index {idx} as main", flush=True)
                break

    if not caps:
        print(f"[!] No working sources in {_CFG}", flush=True)
        print(
            "[!] Ingest idle: set BASIC_MAIN_CAMERA, use --use-webcam, or fix stream_url in cameras.basic.yaml.",
            flush=True,
        )
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\n[*] basic_suite ingest: stopped (idle)", flush=True)
        return

    print(f"[*] basic_suite ingest active: {list(caps.keys())}", flush=True)

    publishes = 0
    t0 = time.monotonic()
    try:
        while True:
            for cid, cap in caps.items():
                ret, frame = cap.read()
                if not ret:
                    continue
                frame = cv2.resize(frame, (640, 360))
                ok, buf = cv2.imencode(".jpg", frame)
                if not ok:
                    continue
                blob = buf.tobytes()
                r.publish(FRAME_CHANNEL, cid.encode() + b"|" + blob)
                # Last JPEG per camera for alert snapshots (rules_basic).
                try:
                    r.set(f"bscam:{cid}:last_jpg", blob, ex=300)
                except Exception:
                    pass
                publishes += 1

            now = time.monotonic()
            if now - t0 >= _HEARTBEAT:
                print(f"[*] basic_suite ingest: ~{publishes} JPEG / {_HEARTBEAT:.0f}s", flush=True)
                publishes = 0
                t0 = now
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\n[*] basic_suite ingest: stopped", flush=True)
    finally:
        for cap in caps.values():
            try:
                cap.release()
            except Exception:
                pass


if __name__ == "__main__":
    main()
