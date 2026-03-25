
import cv2
import os
import argparse
from models.loader import ModelLoader
from pipeline.detection_settings import load_config
import numpy as np

def test_video(video_path, output_path=None):
    if not os.path.exists(video_path):
        print(f"[!] Error: Video file not found at {video_path}")
        return

    print("[*] Initializing models...")
    loader = ModelLoader()
    models_dict = loader.load()
    
    if "fire" not in models_dict:
        print("[!] ERROR: Fire model (fire_smoke.pt) not found in registry or missing on disk.")
        return

    fire_model = models_dict["fire"]
    print(f"[*] Loaded Model: {fire_model.ckpt_path if hasattr(fire_model, 'ckpt_path') else 'fire_smoke.pt'}")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[!] Error: Could not open video {video_path}")
        return

    # Video properties for output
    width = int(cap.get(cv2.COMMAND_CAP_PROP_FRAME_WIDTH) if hasattr(cv2, 'COMMAND_CAP_PROP_FRAME_WIDTH') else cap.get(3))
    height = int(cap.get(cv2.COMMAND_CAP_PROP_FRAME_HEIGHT) if hasattr(cv2, 'COMMAND_CAP_PROP_FRAME_HEIGHT') else cap.get(4))
    fps = cap.get(cv2.CAP_PROP_FPS)
    
    out = None
    if output_path:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
        print(f"[*] Saving results to {output_path}")

    cv2.namedWindow("SecureVu - Advanced Detection Test", cv2.WINDOW_NORMAL)
    
    # More descriptive prompts for open-vocabulary (added socket to filter specific FP)
    if "yolo" in models_dict and hasattr(models_dict["yolo"], "set_classes"):
        custom_classes = ["person", "fire", "smoke", "bright light source", "lit lamp", "glowing bulb", "ceiling light", "cigarette", "socket", "electrical outlet", "power point"]
        models_dict["yolo"].set_classes(custom_classes)
        print(f"[*] YOLO-World Prompts updated (Filtering SOCKETS): {custom_classes}")

    print("[!] Running. Press 'q' to stop.")
    frame_count = 0

    while True:
        ret, frame = cap.read()
        if not ret: break
        frame_count += 1
        display_frame = frame.copy()
        
        yolo_detections = []
        fire_detections = []

        # 1. Run YOLO-World (Validation)
        if "yolo" in models_dict:
            # Setting to 0.20 to only see clear objects
            res = models_dict["yolo"](frame, imgsz=640, conf=0.20, verbose=False)
            for r in res:
                for b in r.boxes:
                    cls_id = int(b.cls[0])
                    label = models_dict["yolo"].names[cls_id]
                    yolo_detections.append({'box': b.xyxy[0].tolist(), 'lbl': label, 'conf': float(b.conf[0])})

        # 2. Run Fire Model (Strict Mode)
        if "fire" in models_dict:
            # Setting to 0.45 threshold to filter out all reflections/noise
            res = models_dict["fire"](frame, imgsz=800, conf=0.45, verbose=False)
            for r in res:
                for b in r.boxes:
                    cls_id = int(b.cls[0])
                    label = models_dict["fire"].names[cls_id]
                    fire_detections.append({'box': b.xyxy[0].tolist(), 'lbl': label, 'conf': float(b.conf[0])})

        # 3. Filter False Positives (Overlap Logic)
        def get_iou(b1, b2):
            x1, y1, x2, y2 = max(b1[0], b2[0]), max(b1[1], b2[1]), min(b1[2], b2[2]), min(b1[3], b2[3])
            if x1>=x2 or y1>=y2: return 0
            inter = (x2-x1)*(y2-y1)
            area1, area2 = (b1[2]-b1[0])*(b1[3]-b1[1]), (b2[2]-b2[0])*(b2[3]-b2[1])
            return inter / (area1 + area2 - inter)

        # Draw YOLO first (Green/Gray)
        for d in yolo_detections:
            x1, y1, x2, y2 = d['box']
            color = (0, 255, 0) if d['lbl'] == 'person' else (128, 128, 128)
            cv2.rectangle(display_frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 1)
            cv2.putText(display_frame, f"YOLO:{d['lbl']}", (int(x1), int(y1)-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Draw Fire ONLY if not a known false positive source
        for f in fire_detections:
            is_false_positive = False
            found_fp_label = ""
            for y in yolo_detections:
                # Filter if it overlaps with Lamps OR Sockets
                if any(x in y['lbl'].lower() for x in ['lamp', 'bulb', 'light', 'socket', 'outlet', 'power']):
                    if get_iou(f['box'], y['box']) > 0.2: # Lower threshold to be safer
                        is_false_positive = True
                        found_fp_label = y['lbl'].upper()
                        break
            
            x1, y1, x2, y2 = f['box']
            if is_false_positive:
                cv2.rectangle(display_frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 255, 0), 1)
                cv2.putText(display_frame, f"FP ({found_fp_label})", (int(x1), int(y1)-5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 0), 1)
            else:
                cv2.rectangle(display_frame, (int(x1), int(y1)), (int(x2), int(y2)), (0, 0, 255), 2)
                cv2.putText(display_frame, f"FIRE:{f['lbl']} {f['conf']:.2f}", (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
                print(f"[*] Frame {frame_count}: REAL FIRE DETECTED! {f['conf']:.2f}")

        if out: out.write(display_frame)
        cv2.imshow("SecureVu - Smart Test", display_frame)
        if cv2.waitKey(1) & 0xFF == ord('q'): break

    cap.release()
    if out:
        out.release()
    cv2.destroyAllWindows()
    print("[*] Test complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test SecureVu Fire Model on Kaggle Dataset Videos")
    parser.add_argument("video", help="Path to the video file from Kaggle dataset")
    parser.add_argument("--out", help="Path to save output video", default=None)
    
    args = parser.parse_args()
    test_video(args.video, args.out)
