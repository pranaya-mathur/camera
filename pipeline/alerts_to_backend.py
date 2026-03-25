"""
Deprecated: the API subscribes to Redis channel "alerts" inside FastAPI (see backend.app).

Do not run this script in production or docker-compose.
"""

def main() -> None:
    print(
        "[!] alerts_to_backend.py is obsolete.\n"
        "    Run uvicorn only — backend.app subscribes to Redis 'alerts' on startup."
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
