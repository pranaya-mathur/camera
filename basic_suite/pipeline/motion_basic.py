import os
import time

import cv2
import numpy as np
import redis

# NEW: Privacy Filter integration
from basic_suite.pipeline.privacy_filter import PrivacyFilter

THRESH = float(os.getenv("MOTION_DIFF_MEAN_THRESHOLD", "5"))
HEARTBEAT_SEC = float(os.getenv("PIPELINE_HEARTBEAT_SEC", "5"))
FRAME_CHANNEL = os.getenv("FRAME_CHANNEL", "frames")
MOTION_QUEUE = os.getenv("MOTION_QUEUE", "motion_queue")
PRIVACY_MODE = os.getenv("PRIVACY_MODE", "0") == "1"

r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379)
sub = r.pubsub()
sub.subscribe(FRAME_CHANNEL)
prev = {}

_pfilter = None
if PRIVACY_MODE:
    _pfilter = PrivacyFilter()
    print("[*] basic_suite motion: Privacy Mode is ENABLED (face blurring active)", flush=True)

_frames_in = 0
_queued = 0
_last_hb = time.monotonic()
_last_mean = 0.0

print(f"[*] basic_suite motion: channel={FRAME_CHANNEL}, queue={MOTION_QUEUE}, thresh={THRESH}", flush=True)

for msg in sub.listen():
    if msg["type"] != "message":
        continue
    cid, img_bytes = msg["data"].split(b"|", 1)
    f = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), 1)
    if f is None:
        continue
    
    # NEW: Privacy Masking
    if PRIVACY_MODE and _pfilter:
        faces = _pfilter.detect_faces(f)
        if faces:
            f = _pfilter.apply_blur(f, faces)
            # Re-encode frame if we modified it
            _, img_encoded = cv2.imencode(".jpg", f)
            img_bytes = img_encoded.tobytes()

    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    if cid not in prev:
        prev[cid] = g
        continue
    mean_diff = float(cv2.absdiff(prev[cid], g).mean())
    _frames_in += 1
    _last_mean = mean_diff
    if mean_diff > THRESH:
        # Pushing processed frame to detection queue
        r.lpush(MOTION_QUEUE, cid + b"|" + img_bytes)
        r.ltrim(MOTION_QUEUE, 0, 50)
        _queued += 1
    now = time.monotonic()
    if now - _last_hb >= HEARTBEAT_SEC:
        print(
            f"[*] basic_suite motion: frames={_frames_in}, queued={_queued}, last_mean={_last_mean:.2f}",
            flush=True,
        )
        _frames_in = 0
        _queued = 0
        _last_hb = now
    prev[cid] = g

