#!/bin/bash
# SecureVu GCP Cleanup Script
# Use this script to teardown the GCE instance and firewall rules after your demo.

set -e

PROJECT_ID=$(gcloud config get-value project)
ZONE=${ZONE:-us-central1-a}
INSTANCE_NAME=${INSTANCE_NAME:-securevu-pilot-vm}

echo "[*] Starting cleanup for Project: $PROJECT_ID"

# 1. Delete VM Instance
echo "[+] Deleting VM: $INSTANCE_NAME..."
gcloud compute instances delete "$INSTANCE_NAME" --zone="$ZONE" --quiet || echo "[!] VM might not exist or already deleted."

# 2. Delete Firewall Rule
echo "[+] Deleting firewall rule: securevu-basic-suite-allow-8000..."
gcloud compute firewall-rules delete securevu-basic-suite-allow-8000 --quiet || echo "[!] Rule might not exist or already deleted."

echo ""
echo "--- CLEANUP COMPLETE ---"
echo "All demo resources have been removed to save your GCP credits."
