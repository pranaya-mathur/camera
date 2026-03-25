import cv2, redis, os, json, numpy as np
from datetime import datetime
from models.loader import ModelLoader
from pipeline.detection_settings import load_config, box_conf

# Visual demo with YOLO-World (Open Vocabulary for India context)

def main():
    CFG = load_config()
    print("[*] Initializing models...")
    loader = ModelLoader()
    models_dict = loader.load()
    
    if not models_dict:
        print("[!] ERROR: No models loaded.")
        return

    # Set classes for YOLO-World
    if "yolo" in models_dict and hasattr(models_dict["yolo"], "set_classes"):
        models_dict["yolo"].set_classes(CFG["yolo_world_classes"])

    print(f"[*] Active models: {list(models_dict.keys())}")
    
    print("[*] Connecting to webcam...")
    # Use 0 for laptop webcam (adjust if needed per cameras.yaml)
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
        
        # ULTIMATE DEBUG MODE: RUN EVERY MODEL ON EVERY FRAME
        for name, model in models_dict.items():
            # Use 800 high resolution for maximum detail
            # Set confidence very low (0.05) to catch even ghost detections
            results = model(frame, imgsz=800, conf=0.05, verbose=False)
            
            for r in results:
                for box in r.boxes:
                    conf = float(box.conf[0])
                    if conf < 0.05: continue
                    
                    cls_id = int(box.cls[0])
                    label = model.names[cls_id] if hasattr(model, "names") else name
                    
                    # Log to terminal for user to see
                    print(f"[{name.upper()}] saw {label} at {conf:.2f}")
                    
                    display_detections.append({
                        "box": box.xyxy[0],
                        "conf": conf,
                        "label": f"{name}:{label}",
                        "model": name
                    })

        # Draw ALL Results
        for d in display_detections:
            x1, y1, x2, y2 = d["box"]
            color = (0, 255, 0) # Default Green
            lname = d["label"].lower()
            
            if "fire" in lname: color = (0, 0, 255) # Red
            elif "smoke" in lname: color = (128, 128, 128) # Gray
            elif "face" in lname: color = (255, 0, 0) # Blue
            elif "plate" in lname: color = (0, 255, 255) # Yellow
            
            cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
            cv2.putText(frame, f"{d['label']} {d['conf']:.2f}", (int(x1), int(y1)-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        # Show Window
        cv2.imshow("SecureVu - India Wildlife & Security Demo", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
