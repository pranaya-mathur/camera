"""Zone geometry and state for rules.py (crowd, loitering, restricted areas)."""

from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo


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


def _parse_hhmm(s: str) -> int:
    """Return minutes since midnight for 'HH:MM' or 'H:MM'."""
    parts = (s or "").strip().split(":")
    if len(parts) < 2:
        return 0
    h, m = int(parts[0]), int(parts[1])
    return max(0, min(h * 60 + m, 24 * 60 - 1))


def _minutes_in_window(now_min: int, start_min: int, end_min: int) -> bool:
    """end is exclusive for same-day; overnight if start_min > end_min."""
    if start_min < end_min:
        return start_min <= now_min < end_min
    if start_min > end_min:
        return now_min >= start_min or now_min < end_min
    return False


def schedule_allows(schedule: Optional[Dict[str, Any]]) -> bool:
    """
    If schedule is None or empty, rules always apply.
    If windows is missing or empty, treat as 24/7 (backward compatible).
    Otherwise local time must fall in ANY window (OR), and optional days filter.
    """
    if not schedule:
        return True
    windows = schedule.get("windows")
    if windows is None:
        return True
    if len(windows) == 0:
        return True

    tz_name = str(schedule.get("timezone") or os.environ.get("RULES_TIMEZONE") or "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
    now = datetime.now(tz)
    weekday = now.weekday()
    day_names = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

    days_filter = schedule.get("days")
    if days_filter:
        ok_day = False
        for d in days_filter:
            if isinstance(d, int) and d == weekday:
                ok_day = True
                break
            ds = str(d).strip().lower()[:3]
            if ds and ds == day_names[weekday][:3]:
                ok_day = True
                break
        if not ok_day:
            return False

    now_min = now.hour * 60 + now.minute
    for w in windows:
        if not isinstance(w, dict):
            continue
        st = _parse_hhmm(str(w.get("start", "00:00")))
        en = _parse_hhmm(str(w.get("end", "23:59")))
        if _minutes_in_window(now_min, st, en):
            return True
    return False


def count_vehicles_in_zone(
    detections: List[Dict[str, Any]],
    w: int,
    h: int,
    poly: List[List[float]],
    vehicle_labels: Set[str],
) -> int:
    n = 0
    for d in detections:
        lab = (d.get("label") or "").strip().lower()
        if lab not in vehicle_labels:
            continue
        box = d.get("box")
        if not box or len(box) < 4:
            continue
        cx, cy = bbox_center_norm(box, w, h)
        if point_in_polygon(cx, cy, poly):
            n += 1
    return n


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

