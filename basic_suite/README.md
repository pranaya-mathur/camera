# SecureVu Basic Suite

This folder provides a **standalone, lightweight surveillance pipeline** designed for pilot deployments and localized testing. It reuses core SecureVu AI modules while maintaining a separate, isolated control plane.

---

## 📚 Documentation Index

- [**GCP & Docker Deployment**](docs/deployment_gcp.md) — How to deploy on the cloud (GCE/Docker).
- [**Surveillance AI & Rules**](docs/surveillance_ai.md) — Understanding alerts, loitering, and tuning.
- [**Camera Setup & Discovery**](docs/camera_setup.md) — Connecting ONVIF/RTSP hardware.
- [**Architecture & Access Control**](docs/architecture.md) — RBAC logic, API reference, and design.

---

## ⚡ Quick Start

### 1. Requirements
- Python 3.10+
- Redis (running locally)
- FFmpeg installed

### 2. Run Orbit (Orchestrator)
The orchestrator starts the backend and all processing components in one command.

```bash
source venv/bin/activate
# Start with a specific use-case profile
python3 basic_suite/run_basic_suite.py --profile home_monitoring
```

### 3. Open UI
The UI proxy targets port `8000` by default.

```bash
cd ui
npm install
npm run dev
```

### 4. Seed Admin
By default, the backend seeds an admin user at startup:
- **Email**: `admin@local.test`
- **Password**: `admin123`

---

## 🛠 Project Structure

- `backend_basic.py` — Isolated FastAPI backend.
- `run_basic_suite.py` — Multi-process runner.
- `config/` — YAML configurations (Cameras, Zones, RBAC, Plans).
- `pipeline/` — Stream processing modules (Motion, Rules).
- `adapters/` — IoT/SCADA/Gamepad integration stubs.

---

## 🎯 North Star Feature Parity
Banalytics is a full commercial product. The `basic_suite` provides a localized MVP for:
- [x] Motion + Zones + Alerts + Storage
- [x] ONVIF/RTSP Hardware Discovery
- [x] Granular RBAC & Plans
- [ ] Production Billing Engine (In Roadmap)
- [ ] Distributed Agent Fleet (In Roadmap)
