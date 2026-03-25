# SecureVU

End-to-end reference stack for **AI video analytics**: ingest camera frames, motion-gate them, run multi-model detection (YOLO-World, face, fire/smoke, license plates), apply rules, and push alerts to a **FastAPI** backend with a **React** dashboard (JWT + WebSocket).

---

## Architecture

```
Cameras (webcam / RTSP) ──► webcam_ingest.py ──► Redis pub/sub "frames"
                                                      │
motion.py ◄───────────────────────────────────────────┘
   │
   └──► Redis list "motion_queue"
            │
detect.py ◄─┘  (models from models/registry.yaml + pipeline/detection_config.yaml)
   │
   └──► Redis pub/sub "detections"
            │
rules.py ◄───┘
   │
   └──► Redis pub/sub "alerts"
            │
backend (FastAPI) ◄── async subscriber in-process: updates /alerts + WebSocket broadcast
            │
       ui/ (Vite + React) ──► REST login, WS live feed
```

**Important:** Alerts are consumed **inside the uvicorn process** (no separate `alerts_to_backend` worker). The legacy script `pipeline/alerts_to_backend.py` is obsolete.

---

## Prerequisites

| Component | Notes |
|-----------|--------|
| **Redis** | Default `localhost:6379` locally; service name `redis` in Docker Compose. |
| **Python 3.10+** | Virtualenv recommended at repo root (`venv/`). |
| **Node.js** | For the UI (`ui/`). |
| **GPU** | Optional but strongly recommended for `detect.py` (Ultralytics / PyTorch). |

---

## Quick start (local, no Docker)

1. **Clone and enter the repo.**

2. **Install Python dependencies** (from repo root):

   ```bash
   python3 -m venv venv
   source venv/bin/activate   # Windows: venv\Scripts\activate
   pip install -r models/requirements.txt
   pip install -r backend/requirements.txt
   ```

3. **Download model weights** (requires network):

   ```bash
   bash models/setup_models.sh
   ```

4. **Start Redis** (example macOS Homebrew):

   ```bash
   brew services start redis
   # or: redis-server
   ```

5. **Configure cameras** — edit `pipeline/cameras.yaml`:

   - `main: 0` — built-in or first USB webcam  
   - Or RTSP: `gate: "rtsp://user:pass@192.168.1.50:554/stream1"`  
   - One entry per physical stream; do not duplicate the same device index.

6. **Run the stack** — `test_system.py` expects `venv/bin/python3` at the repo root:

   ```bash
   export PYTHONPATH="$(pwd)"   # usually set inside test_system.py via env
   python3 test_system.py
   ```

   This starts: **uvicorn** (`backend.app:app` on port **8000**), **motion**, **detect**, **rules**, **webcam_ingest**.

7. **Create a user and open the UI:**

   ```bash
   curl -X POST "http://127.0.0.1:8000/auth/register?email=you@example.com&password=yourpass&role=admin"
   ```

   ```bash
   cd ui && npm install && npm run dev
   ```

   Open the URL Vite prints (e.g. `http://localhost:5173`). The UI uses `window.location.hostname` for API/WebSocket (port **8000**) so LAN access works if the browser can reach the host.

---

## Docker Compose

```bash
docker compose up --build
```

- **UI:** `http://localhost:5173`  
- **API:** `http://localhost:8000`  
- **Redis:** `localhost:6379`

Set real RTSP URLs in `pipeline/ingest.py` (`CAMS` dict) for the `ingest` service, or mount config and switch the service command to `webcam_ingest.py` with a volume-mounted `cameras.yaml` if you prefer YAML-driven ingest in containers.

Backend environment includes `REDIS_HOST=redis` and `PYTHONPATH=/app`.

---

## Configuration

| File / env | Purpose |
|------------|---------|
| `pipeline/cameras.yaml` | Camera IDs and sources (integer index or RTSP URL) for `webcam_ingest.py`. |
| `pipeline/detection_config.yaml` | Fire keywords, confidence thresholds, image sizes, vehicle list, YOLO-World class prompts. Restart **detect** and **rules** after changes. |
| `DETECTION_CONFIG` | Optional path to an alternate YAML for the above. |
| `MOTION_DIFF_MEAN_THRESHOLD` | Motion gate sensitivity (default `5`). Lower (e.g. `1.5`) for small-flame experiments; see `motion.py`. |
| `REDIS_HOST` / `REDIS_PORT` | Redis connection (defaults: `localhost` / `6379`; Docker uses `redis`). |
| `SECRET_KEY` | JWT signing (set in production). |
| `.env` | Optional: `TELEGRAM_*`, `SMTP_*` for `backend/notify.py`. |

---

## API overview

| Method | Path | Auth |
|--------|------|------|
| GET | `/health` | No |
| POST | `/auth/register` | No (query params in demo) |
| POST | `/auth/login` | No (OAuth2 form: `username` = email) |
| GET | `/alerts` | Bearer JWT |
| WS | `/ws` | No token in demo (connect after login in UI for same-origin usage) |

---

## Testing

- **Auth script** (backend must be running): `python3 test_auth.py`  
- **Notify smoke test:** `python3 test_notify.py`  
- **Pytest:** `pytest test_auth.py test_notify.py` (where applicable)

---

## Project layout

```
backend/          FastAPI app, auth, SQLite users, in-process Redis alert subscriber
pipeline/         ingest, motion, detect, rules, configs
models/           registry.yaml, weights, setup_models.sh
ui/               React + Vite dashboard
```

---

## Fire detect kyun nahi ho rahi? / Why fire is not detected

Default pipeline mein **dedicated fire model tabhi chalta hai** jab pehle **YOLO-World** kisi detection par fire-related keyword (substring) de aur confidence `fire_soft` se upar ho. **Chhoti flame / lighter** par open-vocab aksar kuch nahi bolta → fire model **skip** ho jata hai → koi fire output nahi.

**Fix (testing):**

1. **`FIRE_VERIFY_EVERY_FRAME=1`** rakh kar `detect.py` dobara chalao — har motion frame par fire model chalega (GPU zyada use).  
   Ya `pipeline/detection_config.yaml` mein `fire_verify_every_frame: true` set karo.
2. **`MOTION_DIFF_MEAN_THRESHOLD`** kam karo taaki frames detect tak pahunchein.
3. **`confidence.fire_verify`** aur thoda kam karo (false positives badh sakte hain).
4. Training data zyada tar **badi aag / smoke** par hai; **lighter** unreliable hai — test ke liye fire wala **video file** `cameras.yaml` mein source bana sakte ho.

---

## Troubleshooting: camera on but “no logs”

- **`test_system.py`** now sets `PYTHONUNBUFFERED=1` so prints show up immediately.  
- Every **~5s** you should see:
  - **`ingest:`** — JPEG frames published to Redis (if this is missing, camera/RTSP is not delivering frames).  
  - **`motion:`** — `frames_rx` and `last_mean_absdiff`. If `queued_to_detect` stays **0** while the scene is static, lower **`MOTION_DIFF_MEAN_THRESHOLD`** (e.g. `1.5`) or add movement in frame.  
  - **`detect:`** — “processed N motion frames” every 20 frames (tune with **`DETECT_LOG_EVERY_N_FRAMES`**). If missing, nothing is reaching `motion_queue` (motion gate too strict or Redis mismatch).  
- **`detect.py`** must use `from detection_settings import …` (not relative imports) when run as `python pipeline/detect.py`.

---

## Limitations (demo / MVP)

- In-memory alert history in the API process (not durable across restarts).  
- Single uvicorn worker recommended so WebSocket and alert state stay consistent.  
- OpenCV RTSP is fine for demos; production often adds reconnect, buffering, and dedicated media pipelines.  
- Fire/smoke tuning is scene-dependent; adjust `detection_config.yaml` and motion threshold for your environment.

---

## License / ownership

Add your license and contact here if you publish the repo.
