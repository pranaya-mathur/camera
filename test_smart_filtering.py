import sys
import os

# Add pipeline to path
sys.path.insert(0, os.path.join(os.getcwd(), "pipeline"))

from detection_settings import calculate_iou, load_config
from detect import _suppress_false_positives

# 1. Test IoU directly
def test_iou():
    box1 = [0, 0, 100, 100]
    box2 = [50, 50, 150, 150]
    iou = calculate_iou(box1, box2)
    # Intersection: [50, 50, 100, 100] -> Area = 50 * 50 = 2500
    # Box1: 100 * 100 = 10000
    # Box2: 100 * 100 = 10000
    # Union: 10000 + 10000 - 2500 = 17500
    # IoU: 2500 / 17500 = 1/7 ~= 0.1428
    print(f"Test IoU: Expected ~0.14, Got {iou:.4f}")
    assert abs(iou - 0.1428) < 0.01

# 2. Test Suppression Logic
def test_suppression():
    # Mock some detections
    # D1: Fire
    # D2: Lamp (Overlapping with D1)
    # D3: Smoke (Not overlapping)
    
    detections = [
        {
            "label": "fire",
            "conf": 0.9,
            "box": [100, 100, 200, 200], # Fire
        },
        {
            "label": "lamp",
            "conf": 0.8,
            "box": [120, 120, 220, 220], # Lamp (IoU with fire ~0.39)
        },
        {
            "label": "smoke",
            "conf": 0.7,
            "box": [500, 500, 600, 600], # Smoke far away
        }
    ]
    
    # Run suppression
    _suppress_false_positives(detections)
    
    # Results
    print(f"Fire suppressed? {detections[0].get('suppressed', False)}")
    print(f"Smoke suppressed? {detections[2].get('suppressed', False)}")
    
    assert detections[0].get("suppressed") == True
    assert detections[2].get("suppressed", False) == False
    print("Test Suppression: Passed!")

if __name__ == "__main__":
    try:
        test_iou()
        test_suppression()
        print("\n[SUCCESS] Smart Filtering verification passed.")
    except Exception as e:
        print(f"\n[FAIL] Verification failed: {e}")
        sys.exit(1)
