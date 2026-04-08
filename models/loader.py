import os
from pathlib import Path

import yaml
from ultralytics import YOLO
import onnxruntime as ort


class ModelLoader:
    def __init__(self, path=None):
        path = path or os.getenv("MODEL_REGISTRY", "models/registry.yaml")
        reg = Path(path)
        if not reg.is_file():
            raise FileNotFoundError(f"Model registry not found: {reg.resolve()}")
        self._repo_root = reg.resolve().parent.parent
        with reg.open() as f:
            self.cfg = yaml.safe_load(f)
        self.models = {}

    def load(self):
        for name, m in self.cfg["models"].items():
            base_path = m["path"]
            if not os.path.isabs(base_path):
                base_path = str(self._repo_root / base_path)
            engine_path = base_path.replace(".pt", ".engine")
            
            # Prefer TensorRT engine if it exists
            if os.path.exists(engine_path):
                print(f"[*] Loading TensorRT engine for {name}: {engine_path}")
                self.models[name] = YOLO(engine_path, task='detect')
                continue
                
            if not os.path.exists(base_path):
                print(f"[!] Warning: Model {name} weights not found at {base_path}, skipping.")
                continue
                
            if m["type"]=="ultralytics":
                self.models[name]=YOLO(base_path)
            elif m["type"]=="yolo-world":
                from ultralytics import YOLOWorld
                self.models[name]=YOLOWorld(base_path)
            elif m["type"]=="onnx":
                self.models[name]=ort.InferenceSession(base_path)
            
            # Cleanup between loads to prevent MPS buffer issues
            import gc
            gc.collect()
            try:
                import torch
                if torch.backends.mps.is_available():
                    torch.mps.empty_cache()
            except: pass

        return self.models
