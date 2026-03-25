---
description: How to deploy and run the SecureVu AI surveillance pipeline
---

Follow these steps to set up and run the enhanced SecureVu AI pipeline with multi-model detection, TensorRT optimization, and persistent storage.

### 1. Environment Setup
Install the necessary dependencies for the backend and models.

```bash
# Install Python dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r models/requirements.txt
pip install -r backend/requirements.txt
```

### 2. Model Preparation
Download the pre-trained weights and optionally export them to TensorRT for high performance.

// turbo
```bash
# Download weights (YOLO-World, Face, Fire, LPD)
bash models/setup_models.sh

# (Optional) Export to TensorRT (.engine) if an NVIDIA GPU is available
python3 models/export_trt.py
```

### 3. Start Infrastructure
Ensure Redis is running, as it acts as the primary message bus.

```bash
# Start Redis (macOS example)
brew services start redis
```

### 4. Run the Pipeline
Use the integrated system runner to start all processing components.

// turbo
```bash
# Start Backend, Motion, Detection (Parallel), Rules, and Clip Buffer
python3 test_system.py
```

### 5. Verify Operation
Check that alerts and clips are being stored correctly.

```bash
# Check alert database
sqlite3 alerts.db "SELECT * FROM alerts ORDER BY timestamp DESC LIMIT 10;"

# List saved alert clips
ls -lh storage/clips/
```

### 6. Frontend Dashboard
Start the React dashboard to view live alerts.

```bash
cd ui
npm install
npm run dev
```
