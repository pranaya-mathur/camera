import json
import os
import time
import traceback
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np
import redis
import yaml

# Path to our localized config
_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.environ.get("DETECTION_CONFIG", os.path.join(os.path.dirname(_DIR), "config", "detection_config.opencv.yaml"))

def _load_config():
    if not os.path.isfile(_CONFIG_PATH):
        return {}
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}

CFG = _load_config()
OPENCV_CFG = CFG.get("opencv") or {}
r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379)

# OpenCV Detectors
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
cat_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalcatface.xml')

# HOG for Pedestrians
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# Thread Pool for concurrent execution
executor = ThreadPoolExecutor(max_workers=2)

print(f"[*] OpenCV Detection Engine started (CPU-only). Config: {_CONFIG_PATH}", flush=True)

def _detect_faces(gray):
    f_cfg = OPENCV_CFG.get("face") or {}
    faces = face_cascade.detectMultiScale(
        gray, 
        scaleFactor=float(f_cfg.get("scaleFactor", 1.1)), 
        minNeighbors=int(f_cfg.get("minNeighbors", 5)), 
        minSize=tuple(f_cfg.get("minSize", (30, 30)))
    )
    return [{"label": "face", "cls": 0, "box": [float(x), float(y), float(x+w), float(y+h)], "conf": 0.9} for (x, y, w, h) in faces]

def _detect_cats(gray):
    c_cfg = OPENCV_CFG.get("cat") or {}
    cats = cat_cascade.detectMultiScale(
        gray, 
        scaleFactor=float(c_cfg.get("scaleFactor", 1.1)), 
        minNeighbors=int(c_cfg.get("minNeighbors", 3))
    )
    return [{"label": "cat", "cls": 1, "box": [float(x), float(y), float(x+w), float(y+h)], "conf": 0.8} for (x, y, w, h) in cats]

def _detect_pedestrians(frame):
    p_cfg = OPENCV_CFG.get("person") or {}
    target_w = int(p_cfg.get("resize_width", 640))
    target_h = int(p_cfg.get("resize_height", 360))
    
    # Resize for throughput
    h, w = frame.shape[:2]
    frame_small = cv2.resize(frame, (target_w, target_h))
    
    (rects, weights) = hog.detectMultiScale(
        frame_small, 
        winStride=tuple(p_cfg.get("winStride", (4, 4))), 
        padding=tuple(p_cfg.get("padding", (8, 8))), 
        scale=float(p_cfg.get("scale", 1.05))
    )
    
    # Rescale boxes back
    rw, rh = w / target_w, h / target_h
    detections = []
    for i, (x, y, pw, ph) in enumerate(rects):
        rx, ry = x * rw, y * rh
        rpw, rph = pw * rw, ph * rh
        detections.append({
            "label": "person",
            "cls": 2,
            "box": [float(rx), float(ry), float(rx + rpw), float(ry + rph)],
            "conf": float(weights[i])
        })
    return detections

def _detect_fire_heuristic(frame):
    h_cfg = OPENCV_CFG.get("heuristics", {}).get("fire") or {}
    if not h_cfg.get("enabled", True):
        return []
        
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    lower = np.array(h_cfg.get("hsv_lower", [0, 100, 100]))
    upper = np.array(h_cfg.get("hsv_upper", [25, 255, 255]))
    
    mask = cv2.inRange(hsv, lower, upper)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    detections = []
    min_area = h_cfg.get("min_area", 500)
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > min_area:
            x, y, w, h = cv2.boundingRect(cnt)
            detections.append({
                "label": "fire",
                "cls": 3,
                "box": [float(x), float(y), float(x + w), float(y + h)],
                "conf": 0.7,
                "heuristic": "fire_color_blob"
            })
    return detections

def detect_objects(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    # Improvement 3: Histogram Equalization
    gray = cv2.equalizeHist(gray)
    
    # Improvement 5: Thread Pool for HOG
    # We run HOG in a separate thread while processing cascades on main (or another thread)
    future_ped = executor.submit(_detect_pedestrians, frame)
    future_fire = executor.submit(_detect_fire_heuristic, frame)
    
    # Sub-improvement: Run cascades
    faces = _detect_faces(gray)
    cats = _detect_cats(gray)
    
    pedestrians = future_ped.result()
    fire = future_fire.result()
    
    return faces + cats + pedestrians + fire

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
