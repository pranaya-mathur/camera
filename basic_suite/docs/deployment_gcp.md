# GCP & Docker Deployment

Instructions for deploying the SecureVu Basic Suite on Google Cloud Platform or any Docker-compatible environment.

## 1. Automated GCP Pilot (Recommended)

We have provided automation scripts to provision a Compute Engine instance and configure networking.

### Build & Push (Cloud Build)
Automate your container builds using Google Cloud Build. This tags and pushes the `basic-suite` image to YOUR project's Container Registry.

```bash
gcloud builds submit --config cloudbuild.yaml .
```

### Automated Provisioning (GCE)
On a local machine with `gcloud` configured, run the setup script:

```bash
bash basic_suite/gcp_pilot_setup.sh
```

**What this script does:**
- Enables Compute Engine and Container Registry APIs.
- Creates a VPC firewall rule for **TCP 8000** (dashboard).
- Provisions a VM pre-configured with the **Container-Optimized OS**.

## 2. Manual Docker Deployment

If you prefer to manage your own VM or use a non-GCP provider.

### From Root Directory
1. Ensure `BASIC_MAIN_CAMERA` is set if using environment overrides.
2. Run Docker Compose:
   ```bash
   docker compose -f basic_suite/docker-compose.yml up --build
   ```

### Ports
- The API binds to **0.0.0.0:8000**.
- Ensure port **8000** is open in your cloud VPC firewall.

## 3. Storage & Secrets

### Persistence
- SQLite Database, snapshots, and clips are stored in the `basic_suite_data` volume.
- Default path inside container: `/data/basic_suite`.

### Secrets Management
The backend supports loading secrets from:
1. Environment variables (e.g., `SECRET_KEY`, `SMTP_PASS`).
2. Mounted files at `/etc/secrets/` (e.g., `/etc/secrets/SECRET_KEY`).
   - This matches GCP Secret Manager's mounted volume pattern.
