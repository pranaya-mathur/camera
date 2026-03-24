
import redis, cv2, numpy as np, os
r=redis.Redis(host=os.getenv("REDIS_HOST","redis"), port=6379)
sub=r.pubsub(); sub.subscribe("frames")
prev={}
for msg in sub.listen():
    if msg["type"]!="message": continue
    cid,img=msg["data"].split(b"|",1)
    f=cv2.imdecode(np.frombuffer(img,np.uint8),1)
    g=cv2.cvtColor(f,cv2.COLOR_BGR2GRAY)
    if cid not in prev: prev[cid]=g; continue
    if cv2.absdiff(prev[cid],g).mean()>5:
        r.publish("motion", msg["data"])
    prev[cid]=g
