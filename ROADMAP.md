# SecureVu — Roadmap, remaining work & enhancements

This document tracks what is **not** in the prototype today and **optional improvements** (UI, operations, product). The live feature set is described in [`README.md`](README.md).

---

## Explicitly not implemented (or placeholder only)

| Area | Notes |
|------|--------|
| **Face recognition** | Face **detection** exists; no embedding gallery, enrollment, or identity matching. |
| **License plate OCR / ANPR** | Plate **detection** (LPD) exists; no robust text read pipeline or India-specific tuning in-repo. |
| **Subscriptions / personas** | No billing, plans, or tenant-scoped feature flags. |
| **Multi-camera re-identification** | No cross-camera track IDs or vehicle re-ID. |
| **External vehicle / owner metadata** | No integration with registration or fleet databases. |

---

## Product / roadmap gaps (vs a full commercial VMS)

- Violence, fall, or child-specific **behaviour models** (beyond geometry + open-vocab heuristics).
- **Policy engine** (schedules, roles, per-user camera access beyond simple JWT role string).
- **Mobile apps** and **white-label** packaging.
- **Audit exports** (legal hold, long-term archive policies).

---

## UI polish (incremental)

- **Zone editor** on the dashboard (draw polygons on a frame grab) instead of hand-editing YAML.
- **Settings screen** for cooldowns, webhook URLs, and clip-on alert types (today: config files + env).
- Merge **alert + clip** into one card when a clip is saved for the same event (today: separate `clip_ready` event).
- **Responsive / mobile** layout pass on the dashboard.
- Richer **alert detail** (thumbnail, bounding boxes) if the pipeline publishes crops or annotated frames.

---

## Operations & production hardening

- **WebSocket authentication** (today `/ws` accepts connections without tying to JWT).
- **HTTPS** termination, secret rotation, and environment separation (dev/staging/prod).
- **Health checks** for pipeline processes (detect, rules, ingest) and Redis connectivity.
- **Metrics** (Prometheus-style): FPS, queue depth, alert rate, GPU utilization.
- **Log aggregation** and rotation; structured logging for rules and detect workers.
- **Backups** for `alerts.db` and clip storage; documented restore procedure.
- **Rate limiting** on webhooks and outbound notifications to avoid storms.

---

## Technical enhancements (engineering)

- **Hot reload** of `zones.yaml` / `detection_config.yaml` without restarting `rules.py` (watch files or SIGHUP).
- **Tests**: unit tests for zone geometry, rules dedupe, and vehicle policy parsing.
- **CI** pipeline (lint, tests, optional model smoke test on CPU).
- **Tracker** (e.g. ByteTrack) for stabler person counts and loitering per individual.
- **Frame / detection batching** tuning guides per GPU tier; optional FP16 path in live `detect.py`.
- **Docker Compose** profile that wires `CLIP_DIR`, `WEBHOOK_*`, and UI env in one file.

---

## Documentation

- **Runbook**: “first day in production” checklist (Redis persistence, disk space for clips, camera auth).
- **Tuning guide**: fire/smoke and motion thresholds per scene type (warehouse vs office).

---

## How to use this list

Treat items as a **backlog**: prioritize by your persona (public space vs business vs retail) and pick vertical slices (e.g. “WebSocket auth + HTTPS” before “zone editor”).
