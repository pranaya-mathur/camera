from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, WebSocket, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import os
import time
from datetime import timedelta
from sqlalchemy.orm import Session
import redis.asyncio as redis_async
import cv2
import numpy as np

from .db import init_db, get_db, User
from .auth import (
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)

MAX_STORED_ALERTS = 5000
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

alerts: list = []
clients: set = set()

# Latest detections per camera: {cam_id: {"dets": [...], "ts": float}}
_latest_dets: dict = {}
_DETS_TTL = 2.0  # seconds before detections are considered stale


# ── label → colour (BGR) ────────────────────────────────────────────────────
LABEL_COLOURS = {
    "person": (0, 220, 0),
    "face":   (0, 180, 255),
    "fire":   (0, 60, 255),
    "smoke":  (80, 80, 220),
}
_DEFAULT_COLOUR = (255, 180, 0)


def _colour_for(label: str):
    l = label.lower()
    for key, col in LABEL_COLOURS.items():
        if key in l:
            return col
    return _DEFAULT_COLOUR


def _annotate_frame(jpeg_bytes: bytes, cam_id: str) -> bytes:
    """Draw bounding boxes + labels on a JPEG frame using the latest detections."""
    entry = _latest_dets.get(cam_id)
    if not entry or (time.time() - entry["ts"]) > _DETS_TTL:
        return jpeg_bytes
    dets = entry["dets"]
    if not dets:
        return jpeg_bytes

    frame = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return jpeg_bytes

    h, w = frame.shape[:2]
    # scale: detections were run on 640×360 (ingest resizes), frame here is also 640×360
    det_w = entry.get("fw", w) or w
    det_h = entry.get("fh", h) or h
    sx = w / det_w
    sy = h / det_h

    for d in dets:
        if d.get("suppressed"):
            continue
        box = d.get("box")
        if not box or len(box) < 4:
            continue
        label = d.get("label", "?")
        conf = d.get("conf", 0.0)

        x1 = int(box[0] * sx)
        y1 = int(box[1] * sy)
        x2 = int(box[2] * sx)
        y2 = int(box[3] * sy)

        colour = _colour_for(label)
        thickness = 2

        # Box
        cv2.rectangle(frame, (x1, y1), (x2, y2), colour, thickness)

        # Label background + text
        text = f"{label}  {conf:.0%}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.52
        text_thickness = 1
        (tw, th), baseline = cv2.getTextSize(text, font, font_scale, text_thickness)
        ty = max(y1 - 4, th + 4)
        cv2.rectangle(frame, (x1, ty - th - baseline - 2), (x1 + tw + 4, ty + 2), colour, cv2.FILLED)
        cv2.putText(frame, text, (x1 + 2, ty - baseline), font, font_scale, (10, 10, 10), text_thickness, cv2.LINE_AA)

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return buf.tobytes()


async def broadcast(event: dict) -> None:
    dead = []
    for c in clients:
        try:
            await c.send_text(json.dumps(event))
        except Exception:
            dead.append(c)
    for d in dead:
        clients.discard(d)


async def _redis_alert_listener() -> None:
    """Subscribe to pipeline alerts in-process so WebSocket and GET /alerts stay consistent."""
    client = redis_async.Redis(
        host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
    )
    pubsub = client.pubsub()
    await pubsub.subscribe("alerts")
    try:
        while True:
            try:
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=0.5
                )
            except asyncio.CancelledError:
                raise
            if msg is None:
                continue
            if msg.get("type") != "message":
                continue
            try:
                evt = json.loads(msg["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            alerts.append(evt)
            if len(alerts) > MAX_STORED_ALERTS:
                del alerts[: len(alerts) - MAX_STORED_ALERTS]
            await broadcast(evt)
    finally:
        try:
            await pubsub.unsubscribe("alerts")
            await pubsub.aclose()
        except Exception:
            pass
        try:
            await client.aclose()
        except Exception:
            pass


async def _redis_detection_listener() -> None:
    """Cache latest detections per camera for frame annotation."""
    client = redis_async.Redis(
        host=REDIS_HOST, port=REDIS_PORT, decode_responses=True
    )
    pubsub = client.pubsub()
    await pubsub.subscribe("detections")
    try:
        while True:
            try:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            except asyncio.CancelledError:
                raise
            if msg is None:
                continue
            if msg.get("type") != "message":
                continue
            try:
                payload = json.loads(msg["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            cam = payload.get("cam") or ""
            if cam:
                fw = (payload.get("frame") or {}).get("w", 640)
                fh = (payload.get("frame") or {}).get("h", 360)
                _latest_dets[cam] = {
                    "dets": payload.get("detections") or [],
                    "ts": time.time(),
                    "fw": fw,
                    "fh": fh,
                }
    finally:
        try:
            await pubsub.unsubscribe("detections")
            await pubsub.aclose()
        except Exception:
            pass
        try:
            await client.aclose()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    task_alerts = asyncio.create_task(_redis_alert_listener())
    task_dets = asyncio.create_task(_redis_detection_listener())
    try:
        yield
    finally:
        for t in (task_alerts, task_dets):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIP_DIR = os.getenv("CLIP_DIR", os.path.join(_REPO_ROOT, "storage", "clips"))
os.makedirs(CLIP_DIR, exist_ok=True)
app.mount("/clips", StaticFiles(directory=CLIP_DIR), name="clips")


@app.post("/auth/register")
def register(
    email: str = Query(..., description="User email"),
    password: str = Query(..., description="Password"),
    role: str = Query("home"),
    db: Session = Depends(get_db),
):
    db_user = db.query(User).filter(User.email == email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    new_user = User(
        email=email, hashed_password=get_password_hash(password), role=role
    )
    db.add(new_user)
    db.commit()
    return {"message": "User created successfully"}


@app.post("/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": user.role,
    }


@app.get("/video/{cam_id}")
async def video_feed(cam_id: str):
    """MJPEG stream from Redis 'frames' channel."""

    async def frame_generator():
        client = redis_async.Redis(host=REDIS_HOST, port=REDIS_PORT)
        pubsub = client.pubsub()
        await pubsub.subscribe("frames")
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    await asyncio.sleep(0)
                    continue
                if msg["type"] == "message":
                    data = msg["data"]
                    if b"|" in data:
                        cid_bytes, frame_bytes = data.split(b"|", 1)
                        if cid_bytes.decode() == cam_id:
                            annotated = _annotate_frame(frame_bytes, cam_id)
                            yield (
                                b"--frame\r\n"
                                b"Content-Type: image/jpeg\r\n\r\n"
                                + annotated
                                + b"\r\n"
                            )
                await asyncio.sleep(0)
        finally:
            try:
                await pubsub.unsubscribe("frames")
                await pubsub.aclose()
                await client.aclose()
            except Exception:
                pass

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/control-plane/status")
def control_plane_status(current_user: User = Depends(get_current_user)):
    """Compatibility endpoint used by the Dashboard."""
    import yaml
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pipeline", "cameras.yaml")
    try:
        with open(cfg_path) as f:
            cams_cfg = yaml.safe_load(f).get("cameras", {})
        cam_ids = [cid for cid, v in cams_cfg.items() if v is not None]
    except Exception:
        cam_ids = []
    import time as _time
    return {
        "uptime_sec": 0,
        "redis_host": REDIS_HOST,
        "configured_cameras": cam_ids,
        "alerts_buffered": len(alerts),
        "privacy_mode": False,
    }


@app.get("/cameras")
def get_cameras():
    """Read camera list from pipeline/cameras.yaml."""
    import yaml
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "pipeline", "cameras.yaml")
    try:
        with open(cfg_path) as f:
            cams_cfg = yaml.safe_load(f).get("cameras", {})
        # Convert to Dashboard-friendly format
        return {
            "cameras": [
                {"id": cid, "name": cid.capitalize()} 
                for cid in cams_cfg.keys() if cams_cfg[cid] is not None
            ]
        }
    except Exception as e:
        print(f"[!] Error loading cameras: {e}")
        return {"cameras": [{"id": "main", "name": "Main Camera"}]}


@app.get("/alerts")
def get_alerts(current_user: User = Depends(get_current_user)):
    return {"alerts": alerts[-100:]}


@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except Exception:
        clients.discard(ws)
