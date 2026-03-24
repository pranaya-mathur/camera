
import redis, cv2, numpy as np, json, os, datetime
from datetime import datetime
from models.loader import ModelLoader

r=redis.Redis(host=os.getenv("REDIS_HOST","redis"), port=6379)
sub=r.pubsub(); sub.subscribe("motion")

models_dict=ModelLoader().load()

# Set classes for YOLO-World
if "yolo" in models_dict and hasattr(models_dict["yolo"], "set_classes"):
    # Adding Indian vehicles and license plates
    models_dict["yolo"].set_classes([
        "person", "dog", "cat", "cow", "monkey", "snake", "reptile", "backpack", "bag", 
        "fire", "smoke", "flame", "burning", "haze",
        "auto rickshaw", "motorcycle", "scooter", "car", "bus", "truck", "license plate"
    ])

print(f"[*] Loaded models: {list(models_dict.keys())}")

for msg in sub.listen():
    if msg["type"]!="message": continue
    cid,img=msg["data"].split(b"|",1)
    f=cv2.imdecode(np.frombuffer(img,np.uint8),1)
    
    all_detections = []
    
    # 1. First Pass: Light Models (Monitor Mode)
    for name, model in models_dict.items():
        if name == "fire": continue # Skip heavy model initially
        # Using 640 confirmed as 'Perfect'
        res = model(f, imgsz=640, conf=0.1, verbose=False)
        for rlt in res:
            for b in rlt.boxes:
                cls_id = int(b.cls)
                label = model.names[cls_id] if hasattr(model, "names") else name
                
                all_detections.append({
                    "cls": cls_id,
                    "label": label,
                    "conf": float(b.conf),
                    "model": name,
                    "box": b.xyxy[0].tolist()
                })

    # 2. Second Pass: Verify Fire if triggered (Optimized)
    trigger_words = ["fire", "smoke", "flame", "burning", "haze"]
    trigger = any(d["label"].lower() in trigger_words and d["conf"] > 0.05 for d in all_detections)
    
    if trigger and "fire" in models_dict:
        # Remove unconfirmed triggers
        all_detections = [d for d in all_detections if d["label"].lower() not in trigger_words]
        
        # Run Heavy Verification
        res_h = models_dict["fire"](f, imgsz=640, conf=0.2, verbose=False)
        for rlt in res_h:
            for b in rlt.boxes:
                cls_id = int(b.cls)
                label = models_dict["fire"].names[cls_id]
                all_detections.append({
                    "cls": cls_id,
                    "label": label,
                    "conf": float(b.conf),
                    "model": "fire_heavy",
                    "box": b.xyxy[0].tolist()
                })

    # 3. Third Pass: Precise License Plate Detection (Triggered by vehicles)
    vehicle_types = ["car", "bus", "truck", "auto rickshaw", "motorcycle", "scooter"]
    has_vehicle = any(d["label"].lower() in vehicle_types for d in all_detections)
    if has_vehicle and "lpd" in models_dict:
        # Remove YOLO-World's less precise license plate detections
        all_detections = [d for d in all_detections if d["label"].lower() != "license plate"]
        
        # Run specialized LPD
        res_l = models_dict["lpd"](f, imgsz=640, conf=0.2, verbose=False)
        for rlt in res_l:
            for b in rlt.boxes:
                all_detections.append({
                    "cls": int(b.cls[0]),
                    "label": "License Plate",
                    "conf": float(b.conf[0]),
                    "model": "lpd",
                    "box": b.xyxy[0].tolist()
                })

    if all_detections:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Detections: {[d['label'] for d in all_detections]}")
        
    r.publish("detections", json.dumps({"cam":cid.decode(), "detections":all_detections}))
