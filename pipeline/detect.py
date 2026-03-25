import json
import os
import traceback
from datetime import datetime

import cv2
import numpy as np
import redis

from detection_settings import (
    box_cls_int,
    box_conf,
    label_matches_fire_keyword,
    load_config,
)
from models.loader import ModelLoader
from backend.notify import notifier

r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"), port=6379)

CFG = load_config()
FIRE_KW = CFG["fire_trigger_keywords"]
VEHICLES = {v.strip().lower() for v in CFG["vehicles"]}
CONF = CFG["confidence"]
IMGSZ = CFG["imgsize"]


def _fire_verify_every_frame_enabled():
    v = CFG.get("fire_verify_every_frame")
    if isinstance(v, str):
        if v.strip().lower() in ("1", "true", "yes", "on"):
            return True
        if v.strip().lower() in ("0", "false", "no", "off"):
            return False
    if v is True:
        return True
    env = os.getenv("FIRE_VERIFY_EVERY_FRAME", "").strip().lower()
    return env in ("1", "true", "yes", "on")


FIRE_VERIFY_EVERY = _fire_verify_every_frame_enabled()

models_dict = ModelLoader().load()

if "yolo" in models_dict and hasattr(models_dict["yolo"], "set_classes"):
    models_dict["yolo"].set_classes(CFG["yolo_world_classes"])

print("[*] Listening on motion_queue (Redis BRPOP)", flush=True)
print(f"[*] Loaded models: {list(models_dict.keys())}", flush=True)
print(
    f"[*] Detection config: {os.environ.get('DETECTION_CONFIG', 'pipeline/detection_config.yaml')}",
    flush=True,
)
if FIRE_VERIFY_EVERY:
    print(
        "[*] FIRE_VERIFY_EVERY_FRAME=on → dedicated fire model on every motion frame (high load)",
        flush=True,
    )
else:
    print(
        "[*] Fire model runs only when YOLO-World hits a fire keyword "
        "(set fire_verify_every_frame: true or FIRE_VERIFY_EVERY_FRAME=1 to always run)",
        flush=True,
    )


def _run_first_pass(frame, all_detections):
    sz = IMGSZ["first_pass"]
    cf = CONF["first_pass"]
    for name, model in models_dict.items():
        if name == "fire":
            continue
        if not callable(model):
            continue
        try:
            res = model(frame, imgsz=sz, conf=cf, verbose=False)
        except Exception as e:
            print(f"[!] Model '{name}' inference error: {e}")
            continue
        for rlt in res:
            if rlt.boxes is None:
                continue
            for b in rlt.boxes:
                cls_id = box_cls_int(b)
                m = model
                label = m.names[cls_id] if hasattr(m, "names") and m.names else name
                all_detections.append(
                    {
                        "cls": cls_id,
                        "label": label,
                        "conf": box_conf(b),
                        "model": name,
                        "box": b.xyxy[0].tolist(),
                    }
                )


def _fire_soft_triggered(all_detections):
    soft = CONF["fire_soft"]
    for d in all_detections:
        if d["conf"] <= soft:
            continue
        if label_matches_fire_keyword(d["label"], FIRE_KW):
            return True
    return False


def _strip_soft_fire_labels(all_detections):
    return [
        d
        for d in all_detections
        if not label_matches_fire_keyword(d["label"], FIRE_KW)
    ]


def _run_fire_verify(frame, all_detections, cid: str):
    if "fire" not in models_dict:
        return
    model = models_dict["fire"]
    if not callable(model):
        return
    try:
        res_h = model(
            frame,
            imgsz=IMGSZ["fire_verify"],
            conf=CONF["fire_verify"],
            verbose=False,
        )
    except Exception as e:
        print(f"[!] Fire model error: {e}")
        return
    for rlt in res_h:
        if rlt.boxes is None:
            continue
        for b in rlt.boxes:
            cls_id = box_cls_int(b)
            label = model.names[cls_id] if hasattr(model, "names") else "fire"
            cf = box_conf(b)
            all_detections.append(
                {
                    "cls": cls_id,
                    "label": f"CRITICAL {label}",
                    "conf": cf,
                    "model": "fire_heavy",
                    "box": b.xyxy[0].tolist(),
                }
            )
            notifier.notify("FIRE", cid, f"Verified {label} at {cf:.2f}")


def _has_vehicle(all_detections):
    for d in all_detections:
        lab = (d.get("label") or "").strip().lower()
        if lab in VEHICLES:
            return True
    return False


def _run_lpd(frame, all_detections, cid: str):
    if "lpd" not in models_dict:
        return
    model = models_dict["lpd"]
    if not callable(model):
        return
    all_detections[:] = [
        d for d in all_detections if (d.get("label") or "").lower() != "license plate"
    ]
    try:
        res_l = model(
            frame,
            imgsz=IMGSZ["lpd"],
            conf=CONF["lpd"],
            verbose=False,
        )
    except Exception as e:
        print(f"[!] LPD error: {e}")
        return
    for rlt in res_l:
        if rlt.boxes is None:
            continue
        for b in rlt.boxes:
            all_detections.append(
                {
                    "cls": box_cls_int(b),
                    "label": "License Plate",
                    "conf": box_conf(b),
                    "model": "lpd",
                    "box": b.xyxy[0].tolist(),
                }
            )
    notifier.notify("VEHICLE", cid, "Vehicle and Plate detected")


def process_frame(cid: bytes, img_bytes: bytes):
    frame = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        print("[!] Skipping frame: imdecode failed (corrupt JPEG?)", flush=True)
        return None

    cid_s = cid.decode(errors="replace")
    all_detections = []

    _run_first_pass(frame, all_detections)

    if FIRE_VERIFY_EVERY:
        _run_fire_verify(frame, all_detections, cid_s)
    elif _fire_soft_triggered(all_detections):
        all_detections = _strip_soft_fire_labels(all_detections)
        _run_fire_verify(frame, all_detections, cid_s)

    if _has_vehicle(all_detections):
        _run_lpd(frame, all_detections, cid_s)

    if all_detections:
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] {cid_s} → {[d['label'] for d in all_detections]}",
            flush=True,
        )

    r.publish(
        "detections",
        json.dumps({"cam": cid_s, "detections": all_detections}),
    )
    return (cid_s, len(all_detections))


from concurrent.futures import ProcessPoolExecutor
import time

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "4"))
NUM_WORKERS = int(os.getenv("NUM_WORKERS", "3"))

def worker_loop():
    print(f"[*] Worker process {os.getpid()} started", flush=True)
    _err_streak = 0
    _frames_done = 0
    _LOG_EVERY = int(os.getenv("DETECT_LOG_EVERY_N_FRAMES", "20"))
    
    while True:
        # Collect a batch
        batch_data = []
        for _ in range(BATCH_SIZE):
            res_queue = r.brpop("motion_queue", timeout=1)
            if not res_queue:
                break
            batch_data.append(res_queue[1])
        
        if not batch_data:
            continue
            
        for data in batch_data:
            try:
                cid, img = data.split(b"|", 1)
                out = process_frame(cid, img)
                if out:
                    _frames_done += 1
                    if _frames_done % _LOG_EVERY == 0:
                        print(f"[*] worker {os.getpid()}: processed {_frames_done} frames", flush=True)
                _err_streak = 0
            except Exception:
                _err_streak += 1
                if _err_streak <= 3 or _err_streak % 50 == 0:
                    print(f"[!] Worker error (x{_err_streak}):\n{traceback.format_exc()}")

if __name__ == "__main__":
    print(f"[*] Starting {NUM_WORKERS} parallel workers with batch_size={BATCH_SIZE}", flush=True)
    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        futures = [executor.submit(worker_loop) for _ in range(NUM_WORKERS)]
        for future in futures:
            future.result() # Keep main process alive
