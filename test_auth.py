"""Auth flow using TestClient (no server on :8000 required). Run: pytest test_auth.py -q"""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_auth_flow(client: TestClient):
    email = f"test_{uuid.uuid4().hex[:12]}@securevu.test"
    r = client.post(
        "/auth/register",
        params={"email": email, "password": "testpass123", "role": "admin"},
    )
    assert r.status_code == 200, r.text

    r = client.post(
        "/auth/login",
        data={"username": email, "password": "testpass123"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    assert token

    r = client.get("/alerts", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text

    r = client.get("/alerts")
    assert r.status_code == 401
