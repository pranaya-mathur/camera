import os
import time

import cv2
import numpy as np
import redis

# Mean abs pixel change (0–255) on full grayscale frame before a frame is queued
# for detection. A cigarette lighter flame changes very few pixels — default 5
# often never trips. For lab tests use e.g. MOTION_DIFF_MEAN_THRESHOLD=1.5
# or move your hand in frame while testing.
THRESH = float(os.getenv("MOTION_DIFF_MEAN_THRESHOLD", "5"))
HEARTBEAT_SEC = float(os.getenv("PIPELINE_HEARTBEAT_SEC", "5"))

r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379)
sub = r.pubsub()
sub.subscribe("frames")
prev = {}

_frames_in = 0
_queued = 0
_last_hb = time.monotonic()
_last_mean = 0.0

print(
    f"[*] Motion gate: mean absdiff > {THRESH} (set MOTION_DIFF_MEAN_THRESHOLD to tune)",
    flush=True,
)

for msg in sub.listen():
    if msg["type"] != "message":
        continue
    cid, img = msg["data"].split(b"|", 1)
    f = cv2.imdecode(np.frombuffer(img, np.uint8), 1)
    if f is None:
        continue
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    if cid not in prev:
        prev[cid] = g
        continue
    mean_diff = float(cv2.absdiff(prev[cid], g).mean())
    _frames_in += 1
    _last_mean = mean_diff
    if mean_diff > THRESH:
        r.lpush("motion_queue", msg["data"])
        r.ltrim("motion_queue", 0, 50)
        _queued += 1
    now = time.monotonic()
    if now - _last_hb >= HEARTBEAT_SEC:
        print(
            f"[*] motion: last {HEARTBEAT_SEC:.0f}s — frames_rx={_frames_in}, "
            f"queued_to_detect={_queued}, last_mean_absdiff={_last_mean:.2f} (need >{THRESH})",
            flush=True,
        )
        _frames_in = 0
        _queued = 0
        _last_hb = now
    prev[cid] = g
