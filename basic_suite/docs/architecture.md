# Architecture & Access Control

This document explains the internal logic, RBAC (Role Based Access Control), and API surface of the Basic Suite.

## 1. Interaction Model: Users vs Operators

The Basic Suite follows a "customer-safe" visibility policy by default.

### Viewers (End Users / Customers)
- **Live Feed**: Restricted (MJPEG disabled by default).
- **Video Clips**: Denied (MP4 review is restricted).
- **Alerts**: Allowed (Alert images/snapshots are visible).
- **Embed**: Disabled (Video tokens are not issued).

### Operators (Admins / Managers)
- **Live Feed**: Allowed (Full MJPEG streaming).
- **Video Clips**: Allowed (Full MP4 clip review).
- **Embed**: Allowed (If `LIVE_FEED_MODE=full` is enabled).
- **Control Plane**: Full access to status and discovery.

## 2. API Reference (`backend_basic.py`)

The suite exposes a standalone control-plane API on port `8000`.

### Authentication
- `POST /auth/login`: Issue JWT.
- `POST /auth/register`: Create new user.

### System Control
- `GET /control-plane/status`: Redis health, uptime, and camera list.
- `GET /control-plane/cameras`: Detailed camera capability list.
- `POST /cameras/{cam_id}/ptz`: ONVIF-based PTZ control.

### Surveillance
- `GET /alerts`: List recent alerts (sanitized based on role).
- `GET /alert-images/{name}`: Serve alert snapshots.
- `GET /clips/{name}`: Serve MP4 clips (Operators only).
- `GET /video/{cam_id}`: Authenticated MJPEG stream (Operators only).

### Integrations
- `POST /integrations/iot/command`: IoT Bridge stub.
- `POST /integrations/scada/tag`: SCADA tag writer stub.
- `POST /integrations/gamepad/map`: Gamepad mapper stub.

## 3. Product Entitlements
Plan definitions (`plans.basic.yaml`) control feature access:
- `plan_a`: Standard surveillance.
- `plan_b`: Advanced storage/retention.
- `enterprise`: Unlimited users, full device management.
