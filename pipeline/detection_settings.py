"""Load pipeline/detection_config.yaml (override path with DETECTION_CONFIG env)."""

import os
import copy
import yaml

_DIR = os.path.dirname(os.path.abspath(__file__))

_DEFAULTS = {
    "fire_trigger_keywords": [
        "fire",
        "smoke",
        "flame",
        "burning",
        "blaze",
        "haze",
        "mist",
        "fog",
        "lighter",
        "spark",
        "candle",
    ],
    "fire_alert_keywords": [
        "fire",
        "smoke",
        "flame",
        "burning",
        "blaze",
        "haze",
        "lighter",
        "spark",
        "candle",
    ],
    "confidence": {
        "first_pass": 0.08,
        "fire_soft": 0.02,
        "fire_verify": 0.05,
        "lpd": 0.2,
    },
    "imgsize": {
        "first_pass": 640,
        "fire_verify": 800,
        "lpd": 640,
    },
    "vehicles": [
        "car",
        "bus",
        "truck",
        "auto rickshaw",
        "motorcycle",
        "scooter",
    ],
    # If True, dedicated fire model runs on every motion frame (YOLO trigger not required).
    "fire_verify_every_frame": False,
    "yolo_world_classes": [
        "person",
        "dog",
        "cat",
        "cow",
        "monkey",
        "snake",
        "reptile",
        "backpack",
        "bag",
        "fire",
        "smoke",
        "flame",
        "burning",
        "haze",
        "lighter",
        "spark",
        "candle",
        "candle flame",
        "auto rickshaw",
        "motorcycle",
        "scooter",
        "car",
        "bus",
        "truck",
        "license plate",
    ],
}


def _deep_merge(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config():
    path = os.environ.get("DETECTION_CONFIG", os.path.join(_DIR, "detection_config.yaml"))
    cfg = copy.deepcopy(_DEFAULTS)
    if os.path.isfile(path):
        with open(path) as f:
            user = yaml.safe_load(f)
        if user:
            cfg = _deep_merge(cfg, user)
    return cfg


def label_matches_fire_keyword(label, keywords):
    if not label or not keywords:
        return False
    lo = str(label).lower()
    return any(k.lower() in lo for k in keywords)


def box_conf(b):
    """Ultralytics box confidence as float."""
    t = b.conf
    return float(t.item()) if hasattr(t, "item") else float(t)


def box_cls_int(b):
    t = b.cls
    return int(t.item()) if hasattr(t, "item") else int(t)


def calculate_iou(box1, box2):
    """
    Calculate the Intersection over Union (IoU) of two bounding boxes.
    Boxes are in [x1, y1, x2, y2] format.
    """
    # Determine the coordinates of the intersection rectangle
    x_left = max(box1[0], box2[0])
    y_top = max(box1[1], box2[1])
    x_right = min(box1[2], box2[2])
    y_bottom = min(box1[3], box2[3])

    if x_right < x_left or y_bottom < y_top:
        return 0.0

    # The area of intersection rectangle
    intersection_area = (x_right - x_left) * (y_bottom - y_top)

    # Compute the area of both bounding boxes
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])

    # Compute the union area by combining the areas of both boxes
    # and subtracting the intersection area
    union_area = float(box1_area + box2_area - intersection_area)

    if union_area <= 0:
        return 0.0

    return intersection_area / union_area
