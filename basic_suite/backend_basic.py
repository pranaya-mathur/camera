from contextlib import asynccontextmanager
from datetime import timedelta
import asyncio
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
import redis.asyncio as redis_async
import yaml
from sqlalchemy.orm import Session

# NEW: ONVIF support
try:
    from onvif import ONVIFCamera
except ImportError:
    ONVIFCamera = None

from backend.db import SessionLocal, User, get_db, init_db
from backend.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    authenticate_user,
    create_access_token,
    get_current_user,
    get_password_hash,
    user_from_access_token,
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
# (WebSocket, user | None) — user from ?token= for per-role alert payload (strip clips for viewers).
alerts_ws_clients: List[Tuple[WebSocket, Optional[User]]] = []
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


# Customer-facing policy: live MJPEG / website embed (see BASIC_SUITE_LIVE_FEED_MODE).
LIVE_FEED_MODE = os.getenv("BASIC_SUITE_LIVE_FEED_MODE", "internal").strip().lower()
_INTERNAL_LIVE_ROLES = frozenset(
    x.strip().lower()
    for x in os.getenv("BASIC_SUITE_INTERNAL_LIVE_ROLES", "admin,manager,operator").split(",")
    if x.strip()
)


def _user_may_view_authenticated_live(user: User) -> bool:
    """Logged-in MJPEG /video/{cam} — off for viewers when mode is internal (default)."""
    if not _has_perm(user, "view_streams"):
        return False
    if LIVE_FEED_MODE == "full":
        return True
    if LIVE_FEED_MODE == "off":
        return False
    if LIVE_FEED_MODE == "internal":
        return _role_norm(user.role) in _INTERNAL_LIVE_ROLES
    return False


def _public_embed_streaming_allowed() -> bool:
    """Token-based embed for websites — only when explicitly full (customers could see)."""
    return LIVE_FEED_MODE == "full"


_CLIP_VIEW_ROLES = frozenset(
    x.strip().lower()
    for x in os.getenv("BASIC_SUITE_CLIP_VIEW_ROLES", "admin,manager,operator").split(",")
    if x.strip()
)


def _user_may_see_alert_clip(user: Optional[User]) -> bool:
    """End users (e.g. viewer) never get clip URLs; operators can review MP4 evidence."""
    if user is None:
        return False
    return _role_norm(user.role) in _CLIP_VIEW_ROLES


def _ensure_seed_admin() -> None:
    """
    Ensure an admin user exists (RBAC role `admin` → permissions *).
    Disable with BASIC_SUITE_SEED_ADMIN=0. Override email/password via env.
    """
    flag = os.getenv("BASIC_SUITE_SEED_ADMIN", "1").strip().lower()
    if flag in ("0", "false", "no", "off"):
        return
    email = (os.getenv("BASIC_SUITE_SEED_ADMIN_EMAIL") or "admin@local.test").strip()
    password = os.getenv("BASIC_SUITE_SEED_ADMIN_PASSWORD") or "admin123"
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            db.add(
                User(
                    email=email,
                    hashed_password=get_password_hash(password),
                    role="admin",
                )
            )
            db.commit()
            print(f"[*] basic_suite: seeded admin user {email!r}", flush=True)
            return
        if user.role != "admin":
            user.role = "admin"
            db.commit()
            print(f"[*] basic_suite: promoted existing user {email!r} to admin", flush=True)
    finally:
        db.close()


def _operator_clip_pipeline_enabled() -> bool:
    if os.getenv("BASIC_SUITE_ALERTS_IMAGES_ONLY", "") == "1":
        return False
    return os.getenv("BASIC_SUITE_OPERATOR_CLIPS", "1") == "1"


def _alert_snapshots_enabled() -> bool:
    return os.getenv("BASIC_SUITE_ALERT_SNAPSHOTS", "1") == "1"


def _sanitize_alert_for_user(alert: dict, user: User) -> dict:
    a = dict(alert)
    if not _user_may_see_alert_clip(user):
        a.pop("clip", None)
        a.pop("clip_file", None)
    return a


def _alert_payload_for_ws(alert: dict, user: Optional[User]) -> dict:
    a = dict(alert)
    if not _user_may_see_alert_clip(user):
        a.pop("clip", None)
        a.pop("clip_file", None)
    return a


def _require_perm(perm: str):
    async def dep(current_user: User = Depends(get_current_user)):
        if not _has_perm(current_user, perm):
            raise HTTPException(status_code=403, detail=f"Missing permission: {perm}")
        return current_user

    return dep


_bearer_optional = HTTPBearer(auto_error=False)


async def get_current_user_bearer_or_query(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_optional),
    token_q: Optional[str] = Query(None, alias="token"),
    db: Session = Depends(get_db),
):
    """Browser <img> cannot send Authorization; allow same JWT as ?token= for MJPEG only."""
    raw = (credentials.credentials if credentials else None) or token_q
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = user_from_access_token(raw, db)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def _require_perm_stream(perm: str):
    async def dep(current_user: User = Depends(get_current_user_bearer_or_query)):
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


# PTZ Manager Logic
class PTZManager:
    _connections = {}

    @classmethod
    async def get_camera(cls, cam_id: str, config: dict):
        if not ONVIFCamera:
            return None
        if cam_id in cls._connections:
            return cls._connections[cam_id]
        
        onvif_cfg = config.get("onvif")
        if not onvif_cfg:
            return None
        
        try:
            # Note: synchronous call, wrapping if possible
            cam = ONVIFCamera(
                onvif_cfg["url"].split("//")[-1].split(":")[0], # host
                int(onvif_cfg["url"].split(":")[-1].split("/")[0]), # port
                onvif_cfg["username"],
                onvif_cfg["password"],
                # Directory to hold WSDLs if needed, or None
            )
            cls._connections[cam_id] = cam
            return cam
        except Exception as e:
            print(f"[!] PTZ connection failed for {cam_id}: {e}")
            return None

    @classmethod
    async def move(cls, cam: Any, x: float, y: float, zoom: float = 0):
        try:
            ptz = cam.create_ptz_service()
            media = cam.create_media_service()
            profile = media.GetProfiles()[0]
            
            request = ptz.create_type("ContinuousMove")
            request.ProfileToken = profile.token
            status = ptz.GetStatus({"ProfileToken": profile.token})
            
            # Simple continuous move logic
            request.Velocity = status.Position
            request.Velocity.PanTilt.x = x
            request.Velocity.PanTilt.y = y
            if hasattr(request.Velocity, "Zoom") and zoom != 0:
                request.Velocity.Zoom.x = zoom
            
            ptz.ContinuousMove(request)
            await asyncio.sleep(0.5) # Move for half second
            ptz.Stop({"ProfileToken": profile.token, "PanTilt": True, "Zoom": True})
        except Exception as e:
            print(f"[!] PTZ move error: {e}")


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
    dead: List[Tuple[WebSocket, Optional[User]]] = []
    for pair in list(alerts_ws_clients):
        ws, user = pair
        try:
            await ws.send_text(json.dumps(_alert_payload_for_ws(event, user)))
        except Exception:
            dead.append(pair)
    for pair in dead:
        try:
            alerts_ws_clients.remove(pair)
        except ValueError:
            pass


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
_ensure_seed_admin()
CLIP_DIR = os.getenv("CLIP_DIR", str(ROOT / "storage" / "clips_basic"))
os.makedirs(CLIP_DIR, exist_ok=True)

ALERT_SNAPSHOT_DIR = Path(os.getenv("ALERT_SNAPSHOT_DIR", str(ROOT / "storage" / "alert_snapshots")))
ALERT_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


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
        "live_feed_for_user": _user_may_view_authenticated_live(current_user),
        "live_feed_mode": LIVE_FEED_MODE,
        "public_embed_streaming": _public_embed_streaming_allowed(),
        "alert_snapshots_enabled": _alert_snapshots_enabled(),
        "operator_clip_pipeline": _operator_clip_pipeline_enabled(),
        "clip_media_for_user": _user_may_see_alert_clip(current_user),
        "legacy_alerts_images_only": os.getenv("BASIC_SUITE_ALERTS_IMAGES_ONLY", "") == "1",
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
        "privacy_mode": os.getenv("PRIVACY_MODE", "0") == "1",
    }


@app.get("/control-plane/cameras")
def control_plane_cameras(current_user: User = Depends(_require_perm("view_streams"))):
    cams = _load_cameras()
    allowed = set(_allowed_cameras(current_user))
    out = []
    for cid in cams.keys():
        if cid in allowed:
            name = cid.capitalize()
            has_ptz = isinstance(cams[cid], dict) and "onvif" in cams[cid]
            out.append({"id": cid, "name": name, "has_ptz": has_ptz})
    return {"cameras": out}


@app.post("/cameras/{cam_id}/ptz")
async def ptz_control(
    cam_id: str,
    action: str = Query(..., pattern="^(UP|DOWN|LEFT|RIGHT|ZOOM_IN|ZOOM_OUT|STOP)$"),
    current_user: User = Depends(_require_perm("view_streams")),
):
    if cam_id not in _allowed_cameras(current_user):
        raise HTTPException(status_code=403, detail="Camera not allowed")
    
    cams = _load_cameras()
    cam_cfg = cams.get(cam_id)
    if not isinstance(cam_cfg, dict) or "onvif" not in cam_cfg:
        raise HTTPException(status_code=400, detail="PTZ not configured for this camera")
    
    cam_obj = await PTZManager.get_camera(cam_id, cam_cfg)
    if not cam_obj:
        raise HTTPException(status_code=500, detail="Could not connect to ONVIF camera")
    
    # Map actions to vectors
    x, y, z = 0, 0, 0
    if action == "UP": y = 1
    elif action == "DOWN": y = -1
    elif action == "LEFT": x = -1
    elif action == "RIGHT": x = 1
    elif action == "ZOOM_IN": z = 1
    elif action == "ZOOM_OUT": z = -1
    
    if action == "STOP":
        # Handled in move call sleep logic usually, but here we can force stop
        pass
    else:
        await PTZManager.move(cam_obj, x, y, z)
    
    return {"status": "ok", "action": action}


@app.post("/embed/token")
def create_embed_token(
    cam_id: str = Query(...),
    ttl_sec: int = Query(3600, ge=60, le=7 * 24 * 3600),
    current_user: User = Depends(_require_feature("embed_stream")),
):
    if not _public_embed_streaming_allowed():
        raise HTTPException(
            status_code=403,
            detail="Website embed streaming is disabled (customer-safe mode). Set BASIC_SUITE_LIVE_FEED_MODE=full to enable.",
        )
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
    if not _public_embed_streaming_allowed():
        raise HTTPException(status_code=403, detail="Embed streaming is disabled (customer-safe mode).")
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
            {"id": cid, "name": cid.capitalize(), "has_ptz": isinstance(cams[cid], dict) and "onvif" in cams[cid]} 
            for cid in cams.keys() if cid in allowed
        ]
    }


@app.get("/video/{cam_id}")
async def video_feed(cam_id: str, current_user: User = Depends(_require_perm_stream("view_streams"))):
    if not _user_may_view_authenticated_live(current_user):
        raise HTTPException(
            status_code=403,
            detail="Live video is not available for your account. Alerts and images are still available.",
        )
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


@app.get("/clips/{name}")
async def download_clip(
    name: str,
    current_user: User = Depends(get_current_user_bearer_or_query),
):
    if not _user_may_see_alert_clip(current_user):
        raise HTTPException(status_code=403, detail="Clip review is limited to operator roles.")
    if not re.match(r"^[a-zA-Z0-9_.-]+\.mp4$", name):
        raise HTTPException(status_code=400, detail="Invalid clip name")
    path = (Path(CLIP_DIR) / name).resolve()
    try:
        root = Path(CLIP_DIR).resolve()
    except OSError:
        raise HTTPException(status_code=404, detail="Not found")
    if not str(path).startswith(str(root)) or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="video/mp4", filename=name)


@app.get("/alert-images/{name}")
async def alert_snapshot_image(
    name: str,
    current_user: User = Depends(get_current_user_bearer_or_query),
):
    if not _has_perm(current_user, "view_alerts"):
        raise HTTPException(status_code=403, detail="Missing permission: view_alerts")
    if not re.match(r"^[a-zA-Z0-9_.-]+\.jpg$", name):
        raise HTTPException(status_code=400, detail="Invalid snapshot name")
    path = (ALERT_SNAPSHOT_DIR / name).resolve()
    try:
        snap_root = ALERT_SNAPSHOT_DIR.resolve()
    except OSError:
        raise HTTPException(status_code=404, detail="Not found")
    if not str(path).startswith(str(snap_root)) or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/alerts")
def get_alerts(current_user: User = Depends(_require_perm("view_alerts"))):
    return {
        "alerts": [
            _sanitize_alert_for_user(a, current_user) for a in alerts[-100:]
        ],
    }


@app.websocket("/ws")
async def ws(ws: WebSocket, token: Optional[str] = Query(None)):
    await ws.accept()
    user: Optional[User] = None
    if token:
        db = SessionLocal()
        try:
            user = user_from_access_token(token, db)
        finally:
            db.close()
    pair = (ws, user)
    alerts_ws_clients.append(pair)
    try:
        while True:
            await ws.receive_text()
    except Exception:
        pass
    finally:
        try:
            alerts_ws_clients.remove(pair)
        except ValueError:
            pass


@app.get("/health")
def health():
    return {"status": "ok", "service": "basic_suite_backend"}

