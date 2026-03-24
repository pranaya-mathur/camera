
import redis, json, os, asyncio
from backend.app import broadcast, alerts

r=redis.Redis(host=os.getenv("REDIS_HOST","redis"), port=6379)
sub=r.pubsub(); sub.subscribe("alerts")

async def main():
    for msg in sub.listen():
        if msg["type"]!="message": continue
        evt=json.loads(msg["data"])
        alerts.append(evt)
        await broadcast(evt)

if __name__=="__main__":
    asyncio.run(main())
