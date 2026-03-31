# basic_suite (isolated pipeline folder)

This folder keeps a **separate basic feature pipeline** so your existing repo flow is not mixed.

## What is included here

- `config/cameras.basic.yaml` - separate camera list
- `config/detection_config.basic.yaml` - separate detection/rules config
- `config/zones.basic.yaml` - separate zones (intrusion/crowd/loitering/schedule/HOA)
- `config/use_cases.yaml` - profile presets inspired by the shared link use-cases
- `config/rbac.basic.yaml` - granular role permissions + camera access allowlists
- `config/plans.basic.yaml` - plan definitions and feature entitlements
- `pipeline/webcam_ingest_basic.py` - basic ingest entrypoint
- `pipeline/motion_basic.py` - basic motion gate entrypoint
- `pipeline/rules_basic.py` - isolated rules engine copy
- `pipeline/zone_logic.py` - zone helper copy
- `pipeline/discovery_onvif_rtsp.py` - ONVIF/RTSP subnet discovery scanner
- `backend_basic.py` - isolated backend with RBAC, plans, embed tokens, control-plane APIs
- `adapters/*.py` - IoT/SCADA/gamepad integration stubs
- `run_basic_suite.py` - orchestrator for this folder

## Banalytics-like basic features you can run now

- Ad-hoc surveillance (motion + alerts + clips)
- Home monitoring (zones + loitering + mobile/webhook-ready alerts)
- Business facility security (crowd + intrusion + scheduled restrictions)
- Perimeter / unauthorized access (restricted zones + schedules)
- Pet monitoring (animal alerts)
- 24/7 website streaming baseline (MJPEG stream + dashboard)
- ONVIF/RTSP discovery scanner for one-click-ish provisioning bootstrap
- Granular RBAC (role permissions + camera allowlists)
- Plan/feature gating (subscription-like entitlements)
- Embed token API for website streaming (`/embed/video/{token}`)
- Remote management control-plane status APIs
- IoT/SCADA/robotics gamepad integration stubs (API-level)

## Important scope note

This isolated suite reuses core modules for detection/clip-buffer (`pipeline/detect.py`, `pipeline/clip_buffer.py`) but uses a separate backend module: `basic_suite/backend_basic.py`.

It still does **not** provide full enterprise parity from the external platform page (e.g., full ONVIF provisioning stack, production billing engine, distributed control-plane).
What is added here is a practical MVP implementation of those capabilities within this repo.

## Run

```bash
source venv/bin/activate
python3 basic_suite/run_basic_suite.py --profile home_monitoring --api-port 8100
```

Then open UI (`npm run dev`) and point API to port `8100` via env:

```bash
cd ui
VITE_API_PORT=8100 npm run dev
```

Register a user on the same port:

```bash
curl -X POST "http://127.0.0.1:8100/auth/register?email=you@example.com&password=yourpass&role=admin"
```

## CP E25A quick config

You can configure CP E25A in two ways:

1. Edit `config/cameras.basic.yaml` and set `cameras.main` to an RTSP URL.
2. Keep YAML unchanged and use env override:

```bash
export BASIC_MAIN_CAMERA="rtsp://USERNAME:PASSWORD@CAMERA_IP:554/cam/realmonitor?channel=1&subtype=0"
```

Common RTSP paths to try:

- `rtsp://USERNAME:PASSWORD@CAMERA_IP:554/cam/realmonitor?channel=1&subtype=0`
- `rtsp://USERNAME:PASSWORD@CAMERA_IP:554/Streaming/Channels/101`
- `rtsp://USERNAME:PASSWORD@CAMERA_IP:554/live/ch00_0`

Tip: set camera stream codec to **H.264** for best compatibility.

## Profiles

Current profiles in `config/use_cases.yaml`:

- `ad_hoc_surveillance`
- `home_monitoring`
- `business_facility_security`
- `perimeter_unauthorized_access`
- `pet_monitoring`
- `website_streaming`

You can tune each profile's `motion_diff_threshold` and rule overrides.

`rules_overrides` in `config/use_cases.yaml` are now **fully wired**:
`run_basic_suite.py` merges them into `basic_suite/generated/detection_config.runtime.yaml` per profile.

## New API surface (backend_basic)

- `GET /plans`
- `GET /entitlements`
- `GET /control-plane/status`
- `GET /control-plane/cameras`
- `POST /embed/token?cam_id=main&ttl_sec=3600`
- `GET /embed/video/{token}`
- `POST /integrations/iot/command`
- `POST /integrations/scada/tag?tag=x&value=y`
- `POST /integrations/gamepad/map`

## Discovery helper

```bash
python3 basic_suite/pipeline/discovery_onvif_rtsp.py --cidr 10.251.224.0/24
```
