# Surveillance AI & Rules

This document describes the active detection rules, alert types, and how to tune the surveillance behavior of the Basic Suite.

## 1. Active Alerts

The suite generates alerts based on real-time video analysis.

| Alert Type | Trigger | Severity |
|------------|---------|----------|
| **fire_hazard** | Fire, smoke, or flame detection | Critical |
| **zone_intrusion** | Person detected in a restricted zone | Critical |
| **zone_loitering** | Person stays in a zone for > 20 seconds | Warning |
| **zone_crowd** | > 3 persons detected in a single zone | Warning |
| **intelligence_feed** | General person detection | Info |
| **animal_intrusion** | Dogs, cats, monkeys, snakes, etc. | Warning |
| **security_alert** | License plate detection (LPR) | Info |

> [!TIP]
> **Active Testing Mode**: Loitering (20s) and Crowd (3+) thresholds are currently lowered for easy pilot verification.

## 2. Tuning & Profiles

Profiles allow you to quickly switch between different sensitivity levels. These are defined in `config/use_cases.yaml`.

### Available Profiles
- `ad_hoc_surveillance`: Fast movement detection, low cooldown.
- `home_monitoring`: (Default) Balanced for indoor/outdoor home use.
- `business_facility_security`: Strict crowd checks and longer cooldowns.
- `perimeter_unauthorized_access`: Focus on intrusion alerts.
- `pet_monitoring`: High sensitivity for animal classes.
- `website_streaming`: Minimal alerts, optimized for live display.

### Rule Overrides
Overrides in `use_cases.yaml` are merged into the runtime config at startup:
```yaml
profiles:
  home_monitoring:
    rules_overrides:
      rules_engine:
        alert_cooldown_seconds: 30
```

## 3. Configuration Files
- **`config/detection_config.basic.yaml`**: Main engine settings (thresholds, labels).
- **`config/zones.basic.yaml`**: Geometry definitions for intrusion and loitering.
