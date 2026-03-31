import cv2
import numpy as np
from ultralytics import YOLO
import os

class PrivacyFilter:
    def __init__(self, model_path=None):
        if model_path is None:
            # Default to repo structure
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            model_path = os.path.join(root, "models", "face", "yolov8n-face.pt")
        
        self.model = YOLO(model_path)
        print(f"[*] PrivacyFilter: Loaded face model from {model_path}")

    def detect_faces(self, frame):
        results = self.model(frame, verbose=False)
        boxes = []
        if len(results) > 0:
            for r in results:
                for box in r.boxes:
                    # xyxy
                    b = box.xyxy[0].cpu().numpy().astype(int)
                    boxes.append(b)
        return boxes

    def apply_blur(self, frame, boxes):
        for (x1, y1, x2, y2) in boxes:
            # Ensure within frame
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            
            if x2 <= x1 or y2 <= y1:
                continue

            face_roi = frame[y1:y2, x1:x2]
            # Strong Gaussian blur
            k_size = (max(3, (x2 - x1) // 2 | 1), max(3, (y2 - y1) // 2 | 1))
            blurred_face = cv2.GaussianBlur(face_roi, k_size, 30)
            frame[y1:y2, x1:x2] = blurred_face
        return frame
