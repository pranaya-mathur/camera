import json
import os
import shutil
import subprocess
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

_PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_PIPELINE_DIR)
CLIP_DIR = os.getenv(
    "CLIP_DIR", os.path.join(_REPO_ROOT, "storage", "clips")
)
os.makedirs(CLIP_DIR, exist_ok=True)


def _ensure_browser_playable_mp4(path: str) -> None:
    """
    OpenCV mp4v (MPEG-4 Part 2) often won't play in Safari / some browsers.
    Re-encode to H.264 + yuv420p + faststart when ffmpeg is available.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print(
            "[*] Clip saved as mp4v. For reliable browser playback install ffmpeg "
            "(brew install ffmpeg) — clips will then be re-encoded to H.264.",
            flush=True,
        )
        return
    tmp = path + ".web.mp4"
    try:
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-i",
                path,
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-preset",
                "ultrafast",
                "-crf",
                "23",
                "-movflags",
                "+faststart",
                "-an",
                tmp,
            ],
            check=True,
            timeout=120,
        )
        os.replace(tmp, path)
        print(f"[+] Clip re-encoded for web (H.264): {path}", flush=True)
    except Exception as e:
        print(f"[!] ffmpeg transcode failed, original file kept: {e}", flush=True)
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


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
            if not os.path.isfile(filename) or os.path.getsize(filename) < 32:
                print(f"[!] Clip file missing or empty: {filename}", flush=True)
                continue
            _ensure_browser_playable_mp4(filename)
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


def main() -> None:
    print("[*] buffering frames...")
    try:
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
                        buffer[cid] = deque(maxlen=100)  # ~10 seconds of history
                    buffer[cid].append(frame)
            except Exception as e:
                print(f"[!] Buffering error: {e}")
    except KeyboardInterrupt:
        print("\n[*] clip_buffer: stopped", flush=True)


if __name__ == "__main__":
    main()
