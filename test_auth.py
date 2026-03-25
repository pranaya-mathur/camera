import requests
import time

BASE_URL = "http://localhost:8000"

def test_auth_flow():
    # 1. Register
    print("[*] Registering user...")
    resp = requests.post(f"{BASE_URL}/auth/register?email=admin@securevu.com&password=admin123&role=admin")
    if resp.status_code != 200:
        print(f"    Error: {resp.status_code} - {resp.text}")
    else:
        print(f"    Result: {resp.status_code} - {resp.json()}")

    # 2. Login
    print("[*] Logging in...")
    resp = requests.post(f"{BASE_URL}/auth/login", data={"username": "admin@securevu.com", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    print(f"    Token received: {token[:20]}...")

    # 3. Access Protected Route with Token
    print("[*] Accessing /alerts with token...")
    resp = requests.get(f"{BASE_URL}/alerts", headers={"Authorization": f"Bearer {token}"})
    print(f"    Result: {resp.status_code} - {resp.json()}")
    assert resp.status_code == 200

    # 4. Access Protected Route WITHOUT Token
    print("[*] Accessing /alerts without token...")
    resp = requests.get(f"{BASE_URL}/alerts")
    print(f"    Result: {resp.status_code} (Expected 401)")
    assert resp.status_code == 401

if __name__ == "__main__":
    try:
        test_auth_flow()
        print("\n[+] Auth & RBAC Verification PASSED!")
    except Exception as e:
        print(f"\n[-] Verification FAILED: {e}")
