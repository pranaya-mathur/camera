import os
import yaml
from ultralytics import YOLO

def export_models(registry_path="models/registry.yaml"):
    with open(registry_path) as f:
        cfg = yaml.safe_load(f)
    
    for name, m in cfg["models"].items():
        pt_path = m["path"]
        if not pt_path.endswith(".pt"):
            continue
            
        if not os.path.exists(pt_path):
            print(f"[!] Model {name} weights not found at {pt_path}, skipping export.")
            continue
            
        engine_path = pt_path.replace(".pt", ".engine")
        if os.path.exists(engine_path):
            print(f"[*] {name} already exported to TensorRT ({engine_path}).")
            continue
            
        print(f"[*] Exporting {name} ({pt_path}) to TensorRT...")
        try:
            model = YOLO(pt_path)
            # format='engine' uses TensorRT
            # device=0 assumes GPU is available, else CPU (but TensorRT needs GPU)
            model.export(format='engine', device=0) 
            print(f"[+] Successfully exported {name} to {engine_path}")
        except Exception as e:
            print(f"[!] Failed to export {name}: {e}")

if __name__ == "__main__":
    export_models()
