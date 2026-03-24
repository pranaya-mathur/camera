
import cv2, redis, os, json, numpy as np
from datetime import datetime
from models.loader import ModelLoader

# Visual demo with YOLO-World (Open Vocabulary for India context)

def main():
    print("[*] Initializing models...")
    loader = ModelLoader()
    models_dict = loader.load()
    
    if not models_dict:
        print("[!] ERROR: No models loaded.")
        return

    # Set classes for YOLO-World
    if "yolo" in models_dict and hasattr(models_dict["yolo"], "set_classes"):
        # Expanded trigger list for better sensitivity + Indian vehicles & plates
        models_dict["yolo"].set_classes([
            "person", "dog", "cat", "cow", "monkey", "snake", "reptile", "backpack", "bag", 
            "fire", "smoke", "flame", "burning", "haze",
            "auto rickshaw", "motorcycle", "scooter", "car", "bus", "truck", "license plate"
        ])

    print(f"[*] Active models: {list(models_dict.keys())}")
    
    print("[*] Connecting to webcam...")
    cap = cv2.VideoCapture(0)
    
    cv2.namedWindow("SecureVu - India Wildlife & Security Demo", cv2.WINDOW_NORMAL)
    
    print("[!] Running. Press 'q' to quit.")
    
    # Colors for different classes or models
    COLORS = {
        "face": (255, 0, 0), "fire": (0, 0, 255), "smoke": (128, 128, 128),
        "license plate": (0, 255, 255) # Yellow for plates
    }
    
    # Generate random colors for YOLO-World classes
    CLASSES = [
        "person", "dog", "cat", "cow", "monkey", "snake", "reptile", "backpack", "bag", 
        "fire", "smoke", "flame", "burning", "haze",
        "auto rickshaw", "motorcycle", "scooter", "car", "bus", "truck", "license plate"
    ]
    class_colors = {cls: (int(c[0]), int(c[1]), int(c[2])) for cls, c in zip(CLASSES, np.random.randint(0, 255, (len(CLASSES), 3)))}
    
    # Handled via COLORS dict

    while True:
        ret, frame = cap.read()
        if not ret: break
        
        display_detections = []
        
        # 1. First Pass: Light Models (Monitor Mode)
        for name, model in models_dict.items():
            if name == "fire": continue
            # Using 640 which was confirmed as 'Perfect'
            results = model(frame, imgsz=640, conf=0.1, verbose=False)
            
            for r in results:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    label_name = model.names[cls_id] if hasattr(model, "names") else name
                    display_detections.append({
                        "box": box.xyxy[0],
                        "conf": box.conf[0],
                        "label": label_name,
                        "model": name
                    })

        # 2. Second Pass: Verify Fire if triggered (Optimized)
        # Using very low trigger threshold (0.05) to ensure nothing is missed
        trigger_words = ["fire", "smoke", "flame", "burning", "haze"]
        trigger_fire = any(d["label"].lower() in trigger_words and d["conf"] > 0.05 for d in display_detections)
        
        if trigger_fire and "fire" in models_dict:
            # Clear unconfirmed triggers from light model to avoid UI mess
            display_detections = [d for d in display_detections if d["label"].lower() not in trigger_words]
            
            # Run Heavy Verification on the same frame (Verified Mode)
            res_h = models_dict["fire"](frame, imgsz=640, conf=0.15, verbose=False)
            for r in res_h:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    label_name = models_dict["fire"].names[cls_id]
                    display_detections.append({
                        "box": box.xyxy[0],
                        "conf": box.conf[0],
                        "label": f"CONFIRMED {label_name}",
                        "model": "fire_heavy"
                    })

        # 3. Third Pass: Precise License Plate Detection (Triggered by vehicles)
        vehicle_types = ["car", "bus", "truck", "auto rickshaw", "motorcycle", "scooter"]
        has_vehicle = any(d["label"].lower() in vehicle_types for d in display_detections)
        if has_vehicle and "lpd" in models_dict:
            # Clear unconfirmed/less-precise plates
            display_detections = [d for d in display_detections if d["label"].lower() != "license plate"]
            
            # Run specialized LPD
            res_l = models_dict["lpd"](frame, imgsz=640, conf=0.2, verbose=False)
            for r in res_l:
                for box in r.boxes:
                    display_detections.append({
                        "box": box.xyxy[0],
                        "conf": box.conf[0],
                        "label": "Number Plate",
                        "model": "lpd"
                    })

        # 4. Draw Results
        for d in display_detections:
            x1, y1, x2, y2 = d["box"]
            color = (0, 255, 0) # Default
            lname = d["label"].lower()
            if "fire" in lname: color = (0, 0, 0) # Fixed later
            if "fire" in lname: color = (0, 0, 255)
            elif "smoke" in lname: color = (128, 128, 128)
            elif "plate" in lname: color = (0, 255, 255) # Yellow for plates
            elif d["model"] == "face": color = (255, 0, 0)
            
            # Show in UI if above reasonable threshold
            if d["conf"] > 0.1:
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                label_text = f"{d['label']} {d['conf']:.2f}"
                cv2.putText(frame, label_text, (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # 3. Show Window
        cv2.imshow("SecureVu - India Wildlife & Security Demo", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
