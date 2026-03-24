
import cv2, redis, os
r=redis.Redis(host=os.getenv("REDIS_HOST","redis"), port=6379)
CAMS={"cam1":"rtsp://example"}

caps={k:cv2.VideoCapture(v) for k,v in CAMS.items()}
while True:
    for cid,cap in caps.items():
        ret,frame=cap.read()
        if not ret: continue
        frame=cv2.resize(frame,(640,360))
        _,buf=cv2.imencode(".jpg",frame)
        r.publish("frames", cid.encode()+b"|" + buf.tobytes())
