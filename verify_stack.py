#!/usr/bin/env python3
"""
Non-GPU verification: configs, imports, API contract, zone math.
Run from repo root with the project venv:

  source venv/bin/activate
  python3 verify_stack.py

Exit code 0 means these checks passed. Live camera + models are NOT exercised here;
run test_system.py with Redis for full pipeline smoke.
"""

from __future__ import annotations

import ast
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))


def _fail(msg: str) -> None:
    print(f"[verify_stack] FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    os.chdir(REPO)
    sys.path.insert(0, REPO)
    sys.path.insert(0, os.path.join(REPO, "pipeline"))

    print("[verify_stack] 1/7 syntax check (ast.parse) …")
    for root, _, files in os.walk(os.path.join(REPO, "pipeline")):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8", errors="replace") as f:
                ast.parse(f.read(), filename=path)
    for root, _, files in os.walk(os.path.join(REPO, "backend")):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            with open(path, encoding="utf-8", errors="replace") as f:
                ast.parse(f.read(), filename=path)

    print("[verify_stack] 2/7 YAML configs …")
    import yaml

    for rel in (
        "pipeline/detection_config.yaml",
        "pipeline/zones.yaml",
        "pipeline/cameras.yaml",
    ):
        with open(os.path.join(REPO, rel)) as f:
            yaml.safe_load(f)

    print("[verify_stack] 3/7 zone_logic …")
    from zone_logic import (
        point_in_polygon,
        schedule_allows,
        count_persons_in_zone,
        count_vehicles_in_zone,
    )

    assert point_in_polygon(0.5, 0.5, [[0, 0], [1, 0], [1, 1], [0, 1]])
    assert schedule_allows(None) is True
    dets = [
        {
            "label": "person",
            "box": [100.0, 100.0, 200.0, 200.0],
        }
    ]
    assert (
        count_persons_in_zone(dets, 400, 400, [[0, 0], [1, 0], [1, 1], [0, 1]]) == 1
    )
    assert (
        count_vehicles_in_zone(
            [{"label": "car", "box": [100.0, 100.0, 200.0, 200.0]}],
            400,
            400,
            [[0, 0], [1, 0], [1, 1], [0, 1]],
            {"car"},
        )
        == 1
    )

    print("[verify_stack] 4/7 detection_settings …")
    from detection_settings import load_config

    load_config()

    print("[verify_stack] 5/7 import rules module (no Redis listen loop) …")
    import rules as rules_mod

    assert callable(rules_mod._process_zones)
    assert callable(rules_mod._rules_main_loop)

    print("[verify_stack] 6/7 FastAPI backend + auth (TestClient) …")
    from fastapi.testclient import TestClient
    import uuid

    from backend.app import app

    client = TestClient(app)
    email = f"verify_{uuid.uuid4().hex[:10]}@example.com"
    r = client.post(
        "/auth/register",
        params={"email": email, "password": "verify123", "role": "admin"},
    )
    if r.status_code != 200:
        _fail(f"register: {r.status_code} {r.text}")
    r = client.post(
        "/auth/login",
        data={"username": email, "password": "verify123"},
    )
    if r.status_code != 200:
        _fail(f"login: {r.status_code} {r.text}")
    token = r.json()["access_token"]
    r = client.get("/alerts", headers={"Authorization": f"Bearer {token}"})
    if r.status_code != 200:
        _fail(f"alerts: {r.status_code} {r.text}")
    r = client.get("/alerts")
    if r.status_code != 401:
        _fail(f"alerts without token expected 401, got {r.status_code}")
    r = client.get("/health")
    if r.status_code != 200:
        _fail(f"health: {r.status_code}")

    print("[verify_stack] 7/7 optional Redis ping …")
    try:
        import redis

        rh = os.getenv("REDIS_HOST", "localhost")
        r = redis.Redis(host=rh, port=6379, socket_connect_timeout=1)
        r.ping()
        print(f"  Redis OK at {rh}:6379")
    except Exception as e:
        print(f"  Redis skip (start redis for full live stack): {e}")

    print("[verify_stack] All automated checks passed.")
    print(
        "  Note: GPU inference + camera + long-running workers are not run here."
    )


if __name__ == "__main__":
    main()
