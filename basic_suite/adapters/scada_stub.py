import json
import os
import time


class ScadaBridge:
    """SCADA-like stub: records tags to local JSONL for integration testing."""

    def __init__(self):
        self.path = os.getenv("SCADA_TAG_LOG", "storage/scada_tags_basic.jsonl")

    def write_tag(self, tag: str, value) -> dict:
        row = {"ts": time.time(), "tag": tag, "value": value}
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        return {"status": "ok", "row": row, "path": self.path}
