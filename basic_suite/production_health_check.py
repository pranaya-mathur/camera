import os
import sys
import yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASIC = ROOT / "basic_suite"

def check(name, condition, msg):
    if condition:
        print(f"[OK] {name}")
        return True
    else:
        print(f"[FAIL] {name}: {msg}")
        return False

def main():
    print(f"--- SecureVu Basic Suite Production Health Check ---\n")
    success = True

    # 1. Check Configs
    success &= check("Cameras Config", (BASIC / "config" / "cameras.basic.yaml").exists(), "Missing cameras.basic.yaml")
    success &= check("RBAC Config", (BASIC / "config" / "rbac.basic.yaml").exists(), "Missing rbac.basic.yaml")
    success &= check("Plans Config", (BASIC / "config" / "plans.basic.yaml").exists(), "Missing plans.basic.yaml")

    # 2. Check Models
    face_model = ROOT / "models" / "face" / "yolov8n-face.pt"
    success &= check("Face Model", face_model.exists(), f"Missing {face_model}")

    # 3. Check Imports (Modular)
    try:
        from ultralytics import YOLO
        success &= check("Ultralytics", True, "")
    except ImportError:
        success &= check("Ultralytics", False, "ultralytics not installed")

    try:
        import cv2
        success &= check("OpenCV", True, "")
    except ImportError:
        success &= check("OpenCV", False, "opencv-python not installed")

    # 4. Check ONVIF (Critical for PTZ)
    try:
        import onvif
        success &= check("ONVIF Library", True, "")
    except ImportError:
        success &= check("ONVIF Library", False, "onvif-zeep not installed (needed for PTZ)")

    # 5. Check Privacy Filter
    sys.path.append(str(ROOT))
    try:
        from basic_suite.pipeline.privacy_filter import PrivacyFilter
        pf = PrivacyFilter(model_path=str(face_model))
        success &= check("Privacy Filter Logic", True, "")
    except Exception as e:
        success &= check("Privacy Filter Logic", False, str(e))

    print(f"\n--- Result: {'READY' if success else 'NOT READY'} ---")
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
