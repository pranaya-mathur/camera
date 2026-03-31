import json
import os
import redis


class IoTBridge:
    """Configurable stub bridge: forwards simple commands/events to Redis channels."""

    def __init__(self):
        self.r = redis.Redis(host=os.getenv("REDIS_HOST", "localhost"), port=6379)
        self.cmd_channel = os.getenv("IOT_CMD_CHANNEL", "iot_cmd")
        self.event_channel = os.getenv("IOT_EVENT_CHANNEL", "iot_events")

    def send_command(self, payload: dict) -> dict:
        self.r.publish(self.cmd_channel, json.dumps(payload))
        return {"status": "queued", "channel": self.cmd_channel, "payload": payload}

    def publish_event(self, payload: dict) -> dict:
        self.r.publish(self.event_channel, json.dumps(payload))
        return {"status": "published", "channel": self.event_channel, "payload": payload}
