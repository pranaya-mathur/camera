#!/bin/bash
# SecureVu GCP Pilot Setup Helper
# Use this script to provision a GCE instance for the Basic Suite Pilot.

set -e

PROJECT_ID=$(gcloud config get-value project)
ZONE=${ZONE:-us-central1-a}
INSTANCE_NAME=${INSTANCE_NAME:-securevu-pilot-vm}
MACHINE_TYPE=${MACHINE_TYPE:-e2-standard-4} # Sufficient for multi-cam CPU pilot + Cost Effective

echo "[*] Preparing GCP Pilot for Project: $PROJECT_ID"

# 1. Enable APIs
echo "[+] Enabling required APIs..."
gcloud services enable compute.googleapis.com
gcloud services enable containerregistry.googleapis.com

# 2. Setup Firewall Rules
echo "[+] Creating firewall rule for port 8000..."
gcloud compute firewall-rules create securevu-basic-suite-allow-8000 \
    --direction=INGRESS \
    --priority=1000 \
    --network=default \
    --action=ALLOW \
    --rules=tcp:8000 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=securevu-pilot || echo "[!] Rule might already exist, skipping."

# 3. Provision GCE Instance (Container-Optimized OS)
echo "[+] Provisioning VM: $INSTANCE_NAME in $ZONE..."
gcloud compute instances create-with-container "$INSTANCE_NAME" \
    --project="$PROJECT_ID" \
    --zone="$ZONE" \
    --machine-type="$MACHINE_TYPE" \
    --tags=securevu-pilot \
    --container-image="gcr.io/$PROJECT_ID/securevu-basic-suite:latest" \
    --container-restart-policy=always \
    --boot-disk-size=50GB \
    --boot-disk-type=pd-ssd \
    --metadata=google-logging-enabled=true

echo ""
echo "--- PROVISIONING COMPLETE ---"
echo "VM Name: $INSTANCE_NAME"
echo "Zone:    $ZONE"
echo ""
echo "Next Steps:"
echo "1. Wait a few minutes for the container to pull."
echo "2. Find your External IP:"
echo "   gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE --format='get(networkInterfaces[0].accessConfigs[0].natIP)'"
echo "3. Access the dashboard at http://[EXTERNAL_IP]:8000"
echo "4. Use SSH to configure cameras if needed:"
echo "   gcloud compute ssh $INSTANCE_NAME --zone=$ZONE"
