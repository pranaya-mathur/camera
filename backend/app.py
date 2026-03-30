from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
import os
from datetime import timedelta
from sqlalchemy.orm import Session
import redis.asyncio as redis_async

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_redis_alert_listener())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
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
    email: str,
    password: str,
    role: str = "home",
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
                # get_message() is faster than listen() for low-latency web apps
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    await asyncio.sleep(0.01)
                    continue

                if msg["type"] == "message":
                    data = msg["data"]
                    if b"|" in data:
                        cid_bytes, frame_bytes = data.split(b"|", 1)
                        if cid_bytes.decode() == cam_id:
                            yield (
                                b"--frame\r\n"
                                b"Content-Type: image/jpeg\r\n\r\n"
                                + frame_bytes
                                + b"\r\n"
                            )
                # Keep loop tight but not spinning 100% CPU
                await asyncio.sleep(0.005)
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
    )


@app.get("/health")
def health():
    return {"status": "ok"}


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
