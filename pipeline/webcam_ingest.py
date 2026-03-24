
import cv2, redis, os
r=redis.Redis(host=os.getenv("REDIS_HOST","localhost"), port=6379)
CAMS={"webcam":0}

caps={k:cv2.VideoCapture(v) for k,v in CAMS.items()}
print("Starting webcam ingestion... Press Ctrl+C to stop.")
while True:
    for cid,cap in caps.items():
        ret,frame=cap.read()
        if not ret: continue
        frame=cv2.resize(frame,(640,360))
        _,buf=cv2.imencode(".jpg",frame)
        r.publish("frames", cid.encode()+b"|" + buf.tobytes())
