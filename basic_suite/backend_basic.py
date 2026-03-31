from contextlib import asynccontextmanager
from datetime import timedelta
import asyncio
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
import redis.asyncio as redis_async
import yaml
from sqlalchemy.orm import Session

from backend.db import User, get_db, init_db
from backend.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
)
from basic_suite.adapters.iot_stub import IoTBridge
from basic_suite.adapters.scada_stub import ScadaBridge
from basic_suite.adapters.gamepad_stub import GamepadBridge

MAX_STORED_ALERTS = 5000
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
ROOT = Path(__file__).resolve().parent.parent
BASIC = ROOT / "basic_suite"
RBAC_CFG_PATH = Path(os.getenv("BASIC_RBAC_CONFIG", str(BASIC / "config" / "rbac.basic.yaml")))
PLANS_CFG_PATH = Path(os.getenv("BASIC_PLANS_CONFIG", str(BASIC / "config" / "plans.basic.yaml")))
CAMS_CFG_PATH = Path(os.getenv("BASIC_CAMERAS_CONFIG", str(BASIC / "config" / "cameras.basic.yaml")))
TOKENS_PATH = Path(os.getenv("BASIC_EMBED_TOKENS", str(BASIC / "config" / "embed_tokens.basic.json")))

alerts: List[dict] = []
clients: set = set()
process_started_at = time.time()


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


RBAC = _load_yaml(RBAC_CFG_PATH)
PLANS = _load_yaml(PLANS_CFG_PATH)


def _role_norm(role: str) -> str:
    aliases = RBAC.get("role_alias") or {}
    return aliases.get(role, role)


def _role_spec(role: str) -> Dict[str, Any]:
    r = _role_norm(role)
    return (RBAC.get("roles") or {}).get(r, {"permissions": [], "camera_allow": []})


def _plan_for_role(role: str) -> str:
    role = _role_norm(role)
    return (PLANS.get("role_default_plan") or {}).get(role, "free")


def _plan_spec(plan: str) -> Dict[str, Any]:
    return (PLANS.get("plans") or {}).get(plan, {"features": [], "max_cameras": 1})


def _load_cameras() -> Dict[str, Any]:
    cfg = _load_yaml(CAMS_CFG_PATH)
    return cfg.get("cameras") or {}


def _permissions(user: User) -> List[str]:
    return list(_role_spec(user.role).get("permissions") or [])


def _has_perm(user: User, perm: str) -> bool:
    p = _permissions(user)
    return "*" in p or perm in p


def _require_perm(perm: str):
    async def dep(current_user: User = Depends(get_current_user)):
        if not _has_perm(current_user, perm):
            raise HTTPException(status_code=403, detail=f"Missing permission: {perm}")
        return current_user

    return dep


def _require_feature(feature: str):
    async def dep(current_user: User = Depends(get_current_user)):
        plan = _plan_for_role(current_user.role)
        feats = list(_plan_spec(plan).get("features") or [])
        if feature not in feats and "*" not in feats:
            raise HTTPException(status_code=403, detail=f"Feature not in plan: {feature}")
        return current_user

    return dep


def _allowed_cameras(user: User) -> List[str]:
    allow = list(_role_spec(user.role).get("camera_allow") or [])
    cams = list(_load_cameras().keys())
    if "*" in allow:
        return cams
    return [c for c in cams if c in allow]


embed_tokens: Dict[str, Dict[str, Any]] = {}
if TOKENS_PATH.exists():
    try:
        embed_tokens = json.loads(TOKENS_PATH.read_text(encoding="utf-8"))
    except Exception:
        embed_tokens = {}


def _save_tokens() -> None:
    TOKENS_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKENS_PATH.write_text(json.dumps(embed_tokens, indent=2), encoding="utf-8")


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
    client = redis_async.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe("alerts")
    try:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
            if not msg or msg.get("type") != "message":
                continue
            try:
                evt = json.loads(msg["data"])
            except Exception:
                continue
            alerts.append(evt)
            if len(alerts) > MAX_STORED_ALERTS:
                del alerts[: len(alerts) - MAX_STORED_ALERTS]
            await broadcast(evt)
    finally:
        try:
            await pubsub.unsubscribe("alerts")
            await pubsub.aclose()
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


app = FastAPI(lifespan=lifespan, title="basic_suite control-plane API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()
CLIP_DIR = os.getenv("CLIP_DIR", str(ROOT / "storage" / "clips_basic"))
os.makedirs(CLIP_DIR, exist_ok=True)
app.mount("/clips", StaticFiles(directory=CLIP_DIR), name="clips")


@app.post("/auth/register")
def register(
    email: str = Query(...),
    password: str = Query(...),
    role: str = Query("viewer"),
    db: Session = Depends(get_db),
):
    db_user = db.query(User).filter(User.email == email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    new_user = User(email=email, hashed_password=get_password_hash(password), role=role)
    db.add(new_user)
    db.commit()
    return {"message": "User created", "role": role, "plan": _plan_for_role(role)}


@app.post("/auth/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    role = user.role
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": role,
        "plan": _plan_for_role(role),
        "permissions": _permissions(user),
    }


@app.get("/plans")
def plans(current_user: User = Depends(_require_perm("view_alerts"))):
    return {"plans": PLANS.get("plans", {}), "current_plan": _plan_for_role(current_user.role)}


@app.get("/entitlements")
def entitlements(current_user: User = Depends(_require_perm("view_alerts"))):
    plan = _plan_for_role(current_user.role)
    spec = _plan_spec(plan)
    return {
        "role": current_user.role,
        "role_normalized": _role_norm(current_user.role),
        "permissions": _permissions(current_user),
        "plan": plan,
        "features": spec.get("features", []),
        "max_cameras": spec.get("max_cameras", 1),
        "allowed_cameras": _allowed_cameras(current_user),
    }


@app.get("/control-plane/status")
def control_plane_status(current_user: User = Depends(_require_perm("view_alerts"))):
    cams = _load_cameras()
    return {
        "uptime_sec": int(time.time() - process_started_at),
        "redis_host": REDIS_HOST,
        "configured_cameras": list(cams.keys()),
        "alerts_buffered": len(alerts),
        "rbac_config": str(RBAC_CFG_PATH),
        "plans_config": str(PLANS_CFG_PATH),
    }


@app.get("/control-plane/cameras")
def control_plane_cameras(current_user: User = Depends(_require_perm("view_streams"))):
    cams = _load_cameras()
    allowed = set(_allowed_cameras(current_user))
    out = []
    for cid in cams.keys():
        if cid in allowed:
            out.append({"id": cid, "name": cid.capitalize()})
    return {"cameras": out}


@app.post("/embed/token")
def create_embed_token(
    cam_id: str = Query(...),
    ttl_sec: int = Query(3600, ge=60, le=7 * 24 * 3600),
    current_user: User = Depends(_require_feature("embed_stream")),
):
    if cam_id not in _allowed_cameras(current_user):
        raise HTTPException(status_code=403, detail="Camera not allowed")
    token = secrets.token_urlsafe(24)
    embed_tokens[token] = {
        "cam_id": cam_id,
        "exp": int(time.time()) + ttl_sec,
        "issuer": current_user.email,
    }
    _save_tokens()
    return {"token": token, "cam_id": cam_id, "expires_in": ttl_sec}


@app.get("/embed/video/{token}")
async def embed_video(token: str):
    rec = embed_tokens.get(token)
    if not rec:
        raise HTTPException(status_code=404, detail="Invalid token")
    if int(time.time()) >= int(rec.get("exp", 0)):
        raise HTTPException(status_code=401, detail="Token expired")
    cam_id = str(rec["cam_id"])

    async def frame_generator():
        client = redis_async.Redis(host=REDIS_HOST, port=REDIS_PORT)
        pubsub = client.pubsub()
        await pubsub.subscribe("frames")
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    await asyncio.sleep(0.01)
                    continue
                if msg["type"] == "message":
                    data = msg["data"]
                    if b"|" in data:
                        cid_bytes, frame_bytes = data.split(b"|", 1)
                        if cid_bytes.decode() == cam_id:
                            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                await asyncio.sleep(0.005)
        finally:
            try:
                await pubsub.unsubscribe("frames")
                await pubsub.aclose()
                await client.aclose()
            except Exception:
                pass

    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.post("/integrations/iot/command")
def iot_command(
    payload: Dict[str, Any],
    current_user: User = Depends(_require_feature("iot_bridge")),
):
    bridge = IoTBridge()
    return bridge.send_command(payload)


@app.post("/integrations/scada/tag")
def scada_tag(
    tag: str = Query(...),
    value: str = Query(...),
    current_user: User = Depends(_require_feature("scada_bridge")),
):
    bridge = ScadaBridge()
    return bridge.write_tag(tag=tag, value=value)


@app.post("/integrations/gamepad/map")
def gamepad_map(
    payload: Dict[str, Any],
    current_user: User = Depends(_require_feature("gamepad_bridge")),
):
    axes = payload.get("axes") or {}
    buttons = payload.get("buttons") or {}
    bridge = GamepadBridge()
    return bridge.map_input(axes=axes, buttons=buttons)


@app.get("/cameras")
def get_cameras(current_user: User = Depends(_require_perm("view_streams"))):
    cams = _load_cameras()
    allowed = set(_allowed_cameras(current_user))
    return {
        "cameras": [
            {"id": cid, "name": cid.capitalize()} for cid in cams.keys() if cid in allowed
        ]
    }


@app.get("/video/{cam_id}")
async def video_feed(cam_id: str, current_user: User = Depends(_require_perm("view_streams"))):
    if cam_id not in _allowed_cameras(current_user):
        raise HTTPException(status_code=403, detail="Camera not allowed")

    async def frame_generator():
        client = redis_async.Redis(host=REDIS_HOST, port=REDIS_PORT)
        pubsub = client.pubsub()
        await pubsub.subscribe("frames")
        try:
            while True:
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not msg:
                    await asyncio.sleep(0.01)
                    continue
                if msg["type"] == "message":
                    data = msg["data"]
                    if b"|" in data:
                        cid_bytes, frame_bytes = data.split(b"|", 1)
                        if cid_bytes.decode() == cam_id:
                            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
                await asyncio.sleep(0.005)
        finally:
            try:
                await pubsub.unsubscribe("frames")
                await pubsub.aclose()
                await client.aclose()
            except Exception:
                pass

    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/alerts")
def get_alerts(current_user: User = Depends(_require_perm("view_alerts"))):
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


@app.get("/health")
def health():
    return {"status": "ok", "service": "basic_suite_backend"}
