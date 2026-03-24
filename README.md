
SecureVU E2E Package

Includes:
- End-to-end pipeline (ingest → motion → detect → rules → alerts)
- Model registry + loader
- Real-time alerts via WebSocket
- UI (React/Vite) synced with backend
- Redis (dev) + Kafka (scale) hooks
- S3 upload helper
- Kubernetes (Helm) + Docker compose

Quick Start:
1) pip install -r models/requirements.txt
2) bash models/setup_models.sh
3) docker-compose up --build
4) open UI: http://localhost:5173
