
import yaml
from ultralytics import YOLO
import onnxruntime as ort

class ModelLoader:
    def __init__(self, path="models/registry.yaml"):
        with open(path) as f:
            self.cfg = yaml.safe_load(f)
        self.models = {}

    def load(self):
        import os
        for name, m in self.cfg["models"].items():
            if not os.path.exists(m["path"]):
                print(f"[!] Warning: Model {name} not found at {m['path']}, skipping.")
                continue
            if m["type"]=="ultralytics":
                self.models[name]=YOLO(m["path"])
            elif m["type"]=="yolo-world":
                from ultralytics import YOLOWorld
                self.models[name]=YOLOWorld(m["path"])
            elif m["type"]=="onnx":
                self.models[name]=ort.InferenceSession(m["path"])
        return self.models
