
import cv2, redis, os
import cv2, redis, os, yaml, time

r=redis.Redis(host=os.getenv("REDIS_HOST","localhost"), port=6379)

# Load configuration
cfg_path = os.path.join(os.path.dirname(__file__), "cameras.yaml")
with open(cfg_path) as f:
    CAMS = yaml.safe_load(f)["cameras"]

caps={k:cv2.VideoCapture(v) for k,v in CAMS.items()}
print(f"[*] Starting ingestion for {len(CAMS)} cameras: {list(CAMS.keys())}")

while True:
    for cid,cap in caps.items():
        ret,frame=cap.read()
        if not ret: 
            # If it's a file, restart or skip
            continue
        
        # In multi-cam mode, we resize for efficiency
        frame=cv2.resize(frame,(640,360))
        _,buf=cv2.imencode(".jpg",frame)
        
        # Publish frames to 'frames' channel (motion.py will subscribe)
        r.publish("frames", cid.encode()+b"|" + buf.tobytes())
    
    # Slight sleep to control FPS and avoid overwhelming Redis
    time.sleep(0.01)
