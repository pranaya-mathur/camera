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

Reference: [Banalytics use cases & platform](https://banalytics.live/page.main.tiles#use-cases).

**Defaults in this repo:** **End users** (`viewer`): **no live**, **no clip sharing** — only **JPEG** alert snapshots. **Operators** (`admin` / `manager` / `operator`): **internal MJPEG** + **MP4 clips** (Banalytics-style ops). For **public** live + embed for everyone, set `BASIC_SUITE_LIVE_FEED_MODE=full`.

- Ad-hoc / home / business / perimeter / pet style flows (motion, zones, rules, webhooks)
- **Alert evidence:** JPEG on every alert for all roles; **MP4** additionally for operators when `BASIC_SUITE_OPERATOR_CLIPS=1`
- **Live view:** operator-only MJPEG by default; **full** live + embed like Banalytics only if `BASIC_SUITE_LIVE_FEED_MODE=full`
- ONVIF/RTSP **discovery** helper (not full provisioning stack)
- Granular RBAC, plans / entitlements, control-plane APIs
- Embed token API **when** `LIVE_FEED_MODE=full` (disabled in customer-safe default)
- IoT / SCADA / gamepad **API stubs** (not hardware agents)

## Roadmap: “same as Banalytics” (parity work)

Banalytics is a **full commercial edge + browser console + billing + installers** product. `basic_suite` is an **in-repo MVP**. To move toward parity, work is grouped below (order matters).

| Phase | Goal | Main work in *this* repo |
|-------|------|---------------------------|
| **A — Surveillance core** | Match “motion + zones + alerts + storage” story | Tune profiles, retention/TTL for snapshots, webhook/mobile push adapters, stronger zone/schedule UX in UI |
| **B — Devices & cameras** | Closer to “ONVIF/RTSP/USB + discovery” | Persist discovered cameras into DB/YAML API, health checks, reconnect/backoff, optional USB path in ingest |
| **C — Access & multi-tenant** | Like “sharing / RBAC / remote console” | Tenant/org model, audit log, invite users, stricter API keys for integrations |
| **D — Platform packaging** | Like Banalytics **downloads** (Win/Linux/ARM agents) | Separate **edge agent** repo or PyInstaller/binary + updater; `run_basic_suite.py` stays dev orchestrator |
| **E — Billing & ops** | Pay-per-component / prepaid style | Metering hooks (cameras, AI minutes, storage), Stripe or ledger; not in `basic_suite` today |

**Not realistically “same” without new products:** distributed SCADA depth, drone/joystick stacks, STEM bundles, Telegram/SQL components as shipped by Banalytics — those need **dedicated modules** or integrations, not only `basic_suite` edits.

**If your north star stays “no end-user live + no end-user clips, images only”:** keep current env defaults; operators still get **live + clips** internally — closer to full Banalytics-style operations while customers stay snapshot-only.

## End users vs operators (alerts + clips)

- **`BASIC_SUITE_ALERT_SNAPSHOTS=1`** (default): every alert gets a **JPEG** from `bscam:{cam}:last_jpg`, saved under `storage/alert_snapshots/`, served at **`GET /alert-images/{file}.jpg`** (JWT). **All roles** with `view_alerts` can open snapshots.
- **`BASIC_SUITE_OPERATOR_CLIPS=1`** (default): **`clip_buffer.py` runs**; operators get **`clip_ready`** with **`/clips/{file}.mp4`** — but **`GET /alerts`**, **WebSocket**, and **`GET /clips/...`** **strip or deny** clip access for non-operator roles (`BASIC_SUITE_CLIP_VIEW_ROLES`, default `admin,manager,operator`). End users never see a clip link.
- **Legacy:** `BASIC_SUITE_ALERTS_IMAGES_ONLY=1` still **disables the clip pipeline entirely** (snapshots only, no MP4 on disk).

## Customer-safe live video (default)

- `BASIC_SUITE_LIVE_FEED_MODE` (set by `run_basic_suite.py` to **`internal`** by default):
  - **`internal`**: MJPEG `/video/{cam}` only for roles **`admin`**, **`manager`**, **`operator`** (after RBAC `role_alias` normalization). **Viewer / customer-style roles do not get live feed.** Website **`/embed/video/{token}`** and **`POST /embed/token`** are **disabled** so streams are not exposed to customers via embed.
  - **`off`**: No one gets authenticated live or embed.
  - **`full`**: Previous behaviour — any role with `view_streams` + public embed allowed.
- UI reads **`GET /entitlements`** → `live_feed_for_user` to hide the camera preview for customers.

## Important scope note

This isolated suite reuses core modules for detection/clip-buffer (`pipeline/detect.py`, `pipeline/clip_buffer.py`) but uses a separate backend module: `basic_suite/backend_basic.py`.

It still does **not** provide full enterprise parity from the external platform page (e.g., full ONVIF provisioning stack, production billing engine, distributed control-plane).
What is added here is a practical MVP implementation of those capabilities within this repo.

## Run

The API defaults to **port 8000** (same as the main Vite proxy default).

```bash
source venv/bin/activate
python3 basic_suite/run_basic_suite.py --profile home_monitoring
```

On first start, `backend_basic` seeds an **admin** user (RBAC `admin` → all permissions) unless disabled:

- `admin@local.test` / `admin123` (override with `BASIC_SUITE_SEED_ADMIN_EMAIL` and `BASIC_SUITE_SEED_ADMIN_PASSWORD`; set `BASIC_SUITE_SEED_ADMIN=0` to skip).

Then open the UI (proxy targets `8000` by default):

```bash
cd ui
npm run dev
# or: npm run dev:basic  (loads ui/.env.basic, also port 8000)
```

Register a user manually if you prefer:

```bash
curl -X POST "http://127.0.0.1:8000/auth/register?email=you@example.com&password=yourpass&role=admin"
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
