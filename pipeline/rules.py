
import redis, json, os
from datetime import datetime

r=redis.Redis(host=os.getenv("REDIS_HOST","redis"), port=6379)
sub=r.pubsub(); sub.subscribe("detections")

for msg in sub.listen():
    if msg["type"]!="message": continue
    data=json.loads(msg["data"])
    cam = data.get("cam", "unknown")
    
    for d in data.get("detections", []):
        label = d.get("label", "").lower()
        cls_id = d.get("cls", -1)
        
        # 1. Intrusion Alert: Person at night (10 PM to 6 AM)
        if label == "person":
            h = datetime.now().hour
            if h >= 22 or h < 6:
                r.publish("alerts", json.dumps({"type": "intrusion", "cam": cam}))
        
        # 2. Wildlife Alert: Monkey, Snake or Cow (index 3 in our list)
        elif label in ["monkey", "snake", "reptile"] or (label == "cow" or cls_id == 3):
            r.publish("alerts", json.dumps({
                "type": "animal_intrusion", 
                "cam": cam, 
                "animal": label if label else "unknown_animal"
            }))
        
        # 3. Fire/Smoke Alert: Critical
        elif label in ["fire", "smoke"]:
            r.publish("alerts", json.dumps({
                "type": "fire_hazard",
                "cam": cam,
                "label": label
            }))
