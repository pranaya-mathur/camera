import json
import os
import traceback
from datetime import datetime

import cv2
import numpy as np
import redis
import multiprocessing as mp

# Force 'spawn' to avoid CUDA forking issues
try:
    mp.set_start_method('spawn', force=True)
except RuntimeError:
    pass


from detection_settings import (
    box_cls_int,
    box_conf,
    label_matches_fire_keyword,
    load_config,
    calculate_iou,
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

import torch


def _resolve_device() -> str:
    """Pick inference device from DEVICE env or auto (CUDA → MPS → CPU)."""

    def auto():
        if torch.cuda.is_available():
            return "cuda:0"
        if torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    raw = os.getenv("DEVICE", "").strip()
    if not raw:
        return auto()

    low = raw.lower()
    if low == "cpu":
        return "cpu"
    if low == "mps":
        if not torch.backends.mps.is_available():
            print("[!] DEVICE=mps but MPS unavailable; using cpu", flush=True)
            return "cpu"
        return "mps"
    if low in ("cuda", "gpu"):
        if not torch.cuda.is_available():
            print("[!] DEVICE=cuda but CUDA unavailable; using cpu", flush=True)
            return "cpu"
        return "cuda:0"
    if low.startswith("cuda:"):
        if not torch.cuda.is_available():
            print(f"[!] DEVICE={raw} but CUDA unavailable; using cpu", flush=True)
            return "cpu"
        return raw
    if raw.isdigit():
        if not torch.cuda.is_available():
            print(f"[!] DEVICE={raw} but CUDA unavailable; using cpu", flush=True)
            return "cpu"
        idx = int(raw)
        if idx < 0 or idx >= torch.cuda.device_count():
            print(f"[!] DEVICE={raw} out of range; using cuda:0", flush=True)
            return "cuda:0"
        return f"cuda:{idx}"

    print(f"[!] Unrecognized DEVICE={raw!r}; auto-selecting", flush=True)
    return auto()


DEVICE = None

def _get_device():
    global DEVICE
    if DEVICE is not None:
        return DEVICE
    DEVICE = _resolve_device()
    print(f"[*] Targeting device: {DEVICE}", flush=True)
    return DEVICE


models_dict = None


def _load_models():
    global models_dict
    if models_dict is not None:
        return models_dict

    dev = _get_device()
    models_dict = ModelLoader().load()
    for name, m in models_dict.items():
        if hasattr(m, "to"):
            try:
                m.to(dev)
            except Exception as e:
                print(f"[!] Model '{name}' .to({dev!r}) failed: {e}", flush=True)

    if "yolo" in models_dict and hasattr(models_dict["yolo"], "set_classes"):
        models_dict["yolo"].set_classes(CFG["yolo_world_classes"])

    print(f"[*] Loaded models: {list(models_dict.keys())}", flush=True)
    return models_dict


print("[*] Listening on motion_queue (Redis BRPOP)", flush=True)
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
    md = _load_models()
    for name, model in md.items():
        if name == "fire":
            continue
        if not callable(model):
            continue
        try:
            res = model(frame, imgsz=sz, conf=cf, verbose=False, device=_get_device())
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
    md = _load_models()
    if "fire" not in md:
        return
    model = md["fire"]
    if not callable(model):
        return
    try:
        res_h = model(
            frame,
            imgsz=IMGSZ["fire_verify"],
            conf=CONF["fire_verify"],
            verbose=False,
            device=_get_device(),
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
    md = _load_models()
    if "lpd" not in md:
        return
    model = md["lpd"]
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
            device=_get_device(),
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


def _suppress_false_positives(all_detections):
    fp_cfg = CFG.get("fp_suppression")
    if not fp_cfg or not fp_cfg.get("enabled"):
        return

    iou_thresh = fp_cfg.get("iou_threshold", 0.3)
    suppress_labels = {s.lower() for s in fp_cfg.get("suppress_labels", [])}

    # 1. Identify FP sources from the first pass (YOLO-World)
    fp_sources = [
        d for d in all_detections
        if d.get("label", "").lower() in suppress_labels
    ]

    if not fp_sources:
        return

    # 2. Check fire/smoke detections for overlap
    to_suppress = []
    for i, d in enumerate(all_detections):
        if not label_matches_fire_keyword(d.get("label", ""), FIRE_KW):
            continue

        fire_box = d.get("box")
        if not fire_box:
            continue

        for src in fp_sources:
            src_box = src.get("box")
            if not src_box:
                continue

            iou = calculate_iou(fire_box, src_box)
            if iou > iou_thresh:
                print(
                    f"[*] Smart Filtering: Suppressing {d['label']} due to overlap with {src['label']} (IoU={iou:.2f})",
                    flush=True
                )
                to_suppress.append(i)
                break

    # 3. Mark or remove suppressed detections
    # We'll tag them so rules.py can decide, but also for logging
    for idx in to_suppress:
        all_detections[idx]["suppressed"] = True


def pipeline_from_frame(frame, cid_s: str):
    """Full detection stack: YOLO-World + face + LPD first pass, then fire verify, then vehicle LPD."""
    all_detections = []
    _run_first_pass(frame, all_detections)

    if FIRE_VERIFY_EVERY:
        _run_fire_verify(frame, all_detections, cid_s)
    elif _fire_soft_triggered(all_detections):
        all_detections = _strip_soft_fire_labels(all_detections)
        _run_fire_verify(frame, all_detections, cid_s)

    if _has_vehicle(all_detections):
        _run_lpd(frame, all_detections, cid_s)

    # NEW: Smart Filtering / FP Suppression
    _suppress_false_positives(all_detections)

    return all_detections


def process_frame(cid: bytes, img_bytes: bytes):
    frame = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        print("[!] Skipping frame: imdecode failed (corrupt JPEG?)", flush=True)
        return None

    cid_s = cid.decode(errors="replace")
    all_detections = pipeline_from_frame(frame, cid_s)

    if all_detections:
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] {cid_s} → {[d['label'] for d in all_detections]}",
            flush=True,
        )

    h, w = frame.shape[:2]
    r.publish(
        "detections",
        json.dumps(
            {
                "cam": cid_s,
                "frame": {"w": int(w), "h": int(h)},
                "detections": all_detections,
            }
        ),
    )
    return (cid_s, len(all_detections))


from concurrent.futures import ProcessPoolExecutor
import time

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "1"))
NUM_WORKERS = int(os.getenv("NUM_WORKERS", "1"))


def _env_flag(name: str, default_true: bool = True) -> bool:
    v = os.getenv(name, "1" if default_true else "0").strip().lower()
    if default_true:
        return v not in ("0", "false", "no", "off")
    return v in ("1", "true", "yes", "on")


def worker_loop():
    print(f"[*] Worker process {os.getpid()} started (device={_get_device()})", flush=True)
    _frames_done = 0
    _LOG_EVERY = int(os.getenv("DETECT_LOG_EVERY_N_FRAMES", "20"))
    _log_detections = _env_flag("DETECT_LOG_DETECTIONS", default_true=True)
    
    while True:
        # 1. Pull frames from Redis
        batch_items = []
        for _ in range(BATCH_SIZE):
            res = r.brpop("motion_queue", timeout=0.1)
            if res:
                batch_items.append(res[1])
            if not res: break
            
        if not batch_items:
            time.sleep(0.01)
            continue
            
        # 2. Parallel Decode (CPU)
        batch_frames = []
        batch_cids = []
        for j, item in enumerate(batch_items):
            # PERFORMANCE: Skip items to maintain real-time (e.g., skip 50%)
            if j % 2 != 0: continue 
            
            try:
                cid, img_bytes = item.split(b"|", 1)
                frame = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
                if frame is not None:
                    batch_frames.append(frame)
                    batch_cids.append(cid.decode(errors="replace"))
            except: continue
            
        if not batch_frames:
            continue

        # 3. Full pipeline per frame (YOLO-World + face + LPD, then fire verify, then vehicle LPD)
        try:
            for frame, cid_s in zip(batch_frames, batch_cids):
                all_detections = pipeline_from_frame(frame, cid_s)
                if all_detections and _log_detections:
                    labs = [d["label"] for d in all_detections]
                    print(
                        f"[{datetime.now().strftime('%H:%M:%S')}] "
                        f"detect cam={cid_s} → {labs}",
                        flush=True,
                    )
                h, w = frame.shape[:2]
                r.publish(
                    "detections",
                    json.dumps(
                        {
                            "cam": cid_s,
                            "frame": {"w": int(w), "h": int(h)},
                            "detections": all_detections,
                        }
                    ),
                )
            _frames_done += len(batch_frames)
            if _frames_done % _LOG_EVERY == 0:
                print(f"[*] worker {os.getpid()}: processed {_frames_done} frames", flush=True)
                
        except Exception:
             print(f"[!] Batch Error: {traceback.format_exc()}")
             time.sleep(1)

if __name__ == "__main__":
    print(f"[*] Starting {NUM_WORKERS} parallel workers with batch_size={BATCH_SIZE}", flush=True)
    # Using mp.get_context('spawn') is critical for CUDA stability
    with ProcessPoolExecutor(max_workers=NUM_WORKERS, mp_context=mp.get_context('spawn')) as executor:
        futures = [executor.submit(worker_loop) for _ in range(NUM_WORKERS)]
        for future in futures:
            future.result() # Keep main process alive
