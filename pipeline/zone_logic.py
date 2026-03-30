"""Zone geometry and state for rules.py (crowd, loitering, restricted areas)."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Tuple


def point_in_polygon(nx: float, ny: float, poly: List[List[float]]) -> bool:
    """nx, ny normalized 0–1; poly is list of [x, y] normalized."""
    if not poly or len(poly) < 3:
        return False
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        intersect = (yi > ny) != (yj > ny) and nx < (xj - xi) * (ny - yi) / (yj - yi + 1e-12) + xi
        if intersect:
            inside = not inside
        j = i
    return inside


def bbox_center_norm(box: List[float], w: int, h: int) -> Tuple[float, float]:
    x1, y1, x2, y2 = box
    cx = ((x1 + x2) / 2) / max(w, 1)
    cy = ((y1 + y2) / 2) / max(h, 1)
    return cx, cy


def infer_frame_size(
    detections: List[Dict[str, Any]], default_w: int = 640, default_h: int = 360
) -> Tuple[int, int]:
    mw, mh = 0.0, 0.0
    for d in detections:
        b = d.get("box")
        if not b or len(b) < 4:
            continue
        mw = max(mw, float(b[2]), float(b[0]))
        mh = max(mh, float(b[3]), float(b[1]))
    if mw > 1.0 and mh > 1.0:
        return int(mw), int(mh)
    return default_w, default_h


def person_labels() -> frozenset:
    return frozenset({"person", "face"})


def is_person_label(label: str) -> bool:
    return (label or "").strip().lower() in person_labels()


class ZoneRuntimeState:
    """Loitering dwell timers per (camera, zone_id)."""

    def __init__(self) -> None:
        self._occupied_since: Dict[Tuple[str, str], float] = {}

    def loitering_should_fire(
        self,
        cam: str,
        zone_id: str,
        person_count: int,
        loitering_seconds: float,
    ) -> bool:
        """True while dwell time >= threshold (caller clears after successful alert)."""
        key = (cam, zone_id)
        now = time.time()
        if person_count <= 0:
            self._occupied_since.pop(key, None)
            return False
        if key not in self._occupied_since:
            self._occupied_since[key] = now
            return False
        return (now - self._occupied_since[key]) >= loitering_seconds

    def clear_loiter(self, cam: str, zone_id: str) -> None:
        self._occupied_since.pop((cam, zone_id), None)


def count_persons_in_zone(
    detections: List[Dict[str, Any]],
    w: int,
    h: int,
    poly: List[List[float]],
) -> int:
    n = 0
    for d in detections:
        lab = (d.get("label") or "").strip().lower()
        if not is_person_label(lab):
            continue
        box = d.get("box")
        if not box or len(box) < 4:
            continue
        cx, cy = bbox_center_norm(box, w, h)
        if point_in_polygon(cx, cy, poly):
            n += 1
    return n

