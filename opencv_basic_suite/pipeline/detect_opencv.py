import json
import os
import time
import traceback
from datetime import datetime

import cv2
import numpy as np
import redis

# Reuse some settings if possible, or define local ones
# We'll use a local minimal config to keep it isolated
r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379)

# OpenCV Detectors
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
cat_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalcatface.xml')

# HOG for Pedestrians
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

print("[*] OpenCV Detection Engine started (CPU-only)", flush=True)

def detect_objects(frame):
    all_detections = []
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = frame.shape[:2]

    # 1. Face Detection
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
    for (x, y, fw, fh) in faces:
        all_detections.append({
            "cls": 0,
            "label": "face",
            "conf": 0.9, # OpenCV cascades don't provide reliable confidence scores easily
            "model": "opencv_haar",
            "box": [float(x), float(y), float(x + fw), float(y + fh)]
        })

    # 2. Cat Face Detection
    cats = cat_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3)
    for (x, y, cw, ch) in cats:
        all_detections.append({
            "cls": 1,
            "label": "cat",
            "conf": 0.8,
            "model": "opencv_haar_cat",
            "box": [float(x), float(y), float(x + cw), float(y + ch)]
        })

    # 3. Pedestrian Detection (HOG)
    # Note: HOG is relatively slow on CPU
    (rects, weights) = hog.detectMultiScale(frame, winStride=(4, 4), padding=(8, 8), scale=1.05)
    for i, (x, y, pw, ph) in enumerate(rects):
        all_detections.append({
            "cls": 2,
            "label": "person",
            "conf": float(weights[i]),
            "model": "opencv_hog",
            "box": [float(x), float(y), float(x + pw), float(y + ph)]
        })

    return all_detections

def main_loop():
    queue_name = os.getenv("MOTION_QUEUE", "motion_queue")
    print(f"[*] Listening on {queue_name}...", flush=True)
    
    while True:
        res = r.brpop(queue_name, timeout=1)
        if not res:
            continue
            
        try:
            cid_bytes, img_bytes = res[1].split(b"|", 1)
            cid_s = cid_bytes.decode(errors="replace")
            
            frame = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue
                
            detections = detect_objects(frame)
            
            if detections:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] {cid_s} → {[d['label'] for d in detections]}", flush=True)
            
            h, w = frame.shape[:2]
            r.publish("detections", json.dumps({
                "cam": cid_s,
                "frame": {"w": int(w), "h": int(h)},
                "detections": detections,
                "engine": "opencv"
            }))
            
        except Exception:
            print(f"[!] OpenCV Detect Error: {traceback.format_exc()}")
            time.sleep(1)

if __name__ == "__main__":
    main_loop()
