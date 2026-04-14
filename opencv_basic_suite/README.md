# 🛡️ OpenCV Basic Suite (Isolated)

The **OpenCV Basic Suite** is a high-performance, **CPU-only** variant of SecureVu designed for legacy hardware and edge devices (like Raspberry Pi or low-end VMs). It completely eliminates the dependency on modern deep learning models (YOLO/TensorRT) in favor of traditional computer vision algorithms.

---

## ✨ Key Features

### 1. Traditional Vision Detectors
*   **👤 Human Face Detection**: Uses **Haar Cascades** for fast, reliable face tracking.
*   **🚶 Pedestrian Detection**: Uses **HOG + Linear SVM** (Histogram of Oriented Gradients) for robust person detection in various poses.
*   **🐱 Cat Detection**: Specialized Haar models for detecting feline faces.

### 2. 🧠 Heuristic-Based Classification
Since OpenCV doesn't have a "vocabulary" like AI, this suite uses custom **Mathematical Rules** to classify events:
*   **🐾 Animal Heuristics**: Automatically re-classifies objects as "Animals" if they match specific aspect ratios (low height, wide body) and movement patterns.
*   **🔥 Fire Filter**: Employs color-space analysis to detect flickering high-saturation Red/Orange clusters.
*   **🚗 Vehicle Heuristics**: Identifies large, fast-moving rectangular geometries as vehicles.

### 3. ⚡ Ultra-Lightweight Footprint
*   **Model Size**: ~0 MB (Uses built-in OpenCV binaries).
*   **Hardware**: Runs on any CPU with at least 1GB of RAM.
*   **Zero-GPU**: Does not require CUDA or MPS drivers.

---

## 🚀 Getting Started

### 1. Requirements
*   Python 3.10+
*   OpenCV (`opencv-python`)
*   Redis (Running locally)

### 2. Run the Suite
From the root of the repository, execute the isolated runner:
```bash
python3 opencv_basic_suite/run_opencv_suite.py --use-webcam
```

### 3. Open the UI
The suite is fully compatible with the standard SecureVu dashboard.
```bash
cd ui
npm run dev
```

---

## 📁 Project Structure

*   `run_opencv_suite.py`: The main orchestrator (replaces `run_basic_suite.py`).
*   `pipeline/detect_opencv.py`: The detection core using OpenCV primitives.
*   `pipeline/rules_opencv.py`: The rules engine providing heuristic classification.
*   `config/`: Localized configurations for zones and detection sensitivity.

---

## ⚠️ Accuracy Considerations
While this suite is significantly faster, it is **less accurate** than the YOLO-based suite. It is highly sensitive to:
*   **Low Lighting**: Cascades prefer clear color contrasts.
*   **False Positives**: Moving foliage or shadows may occasionally trigger the Pedestrian detector.
*   **Limited Vocabulary**: It can only "see" things that it has a mathematical rule for.
