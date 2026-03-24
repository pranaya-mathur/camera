
#!/bin/bash
set -e
mkdir -p models/yolo models/face models/fire models/animal
curl -L -o models/yolo/yolov8s-worldv2.pt "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8s-worldv2.pt" || true
curl -L -o models/face/yolov8n-face.pt "https://huggingface.co/arnabdhar/YOLOv8-Face-Detection/resolve/main/model.pt?download=true" || true
curl -L -o models/fire/fire_smoke.pt "https://huggingface.co/SHOU-ISD/fire-and-smoke/resolve/main/yolov8n_1.pt?download=true" || true
mkdir -p models/lpd
curl -L -o models/lpd/model.pt "https://huggingface.co/wuriyanto/yolo8-indonesian-license-plate-detection/resolve/main/model.pt" || true
echo "Done"
