
import cv2
import time
import json
import os
import argparse
import numpy as np
from models.loader import ModelLoader

def evaluate_video(video_path):
    print(f"[*] Starting Evaluation for: {os.path.basename(video_path)}")
    loader = ModelLoader()
    models = loader.load()
    
    cap = cv2.VideoCapture(video_path)
    stats = {
        "total_frames": 0,
        "yolo_time": [],
        "fire_time": [],
        "detections": {
            "fire": 0,
            "smoke": 0,
            "person": 0,
            "fp_ignore": 0
        },
        "fps_list": []
    }

    while True:
        ret, frame = cap.read()
        if not ret: break
        
        start_frame = time.time()
        stats["total_frames"] += 1
        
        # 1. EVALUATE YOLO-WORLD
        t1 = time.time()
        res_y = models["yolo"](frame, imgsz=640, conf=0.20, verbose=False)
        stats["yolo_time"].append(time.time() - t1)
        
        found_person = False
        for r in res_y:
            for b in r.boxes:
                label = models["yolo"].names[int(b.cls[0])]
                if label == "person": stats["detections"]["person"] += 1
        
        # 2. EVALUATE FIRE MODEL
        t2 = time.time()
        res_f = models["fire"](frame, imgsz=800, conf=0.45, verbose=False)
        stats["fire_time"].append(time.time() - t2)
        
        for r in res_f:
            for b in r.boxes:
                label = models["fire"].names[int(b.cls[0])]
                if label.lower() == "fire": stats["detections"]["fire"] += 1
                elif label.lower() == "smoke": stats["detections"]["smoke"] += 1

        stats["fps_list"].append(1 / (time.time() - start_frame))
        
        if stats["total_frames"] % 50 == 0:
            print(f"[*] Processed {stats['total_frames']} frames... Current Avg FPS: {np.mean(stats['fps_list']):.2f}")

    # Generate Report
    report = {
        "video": os.path.basename(video_path),
        "total_frames": stats["total_frames"],
        "performance": {
            "avg_fps": float(np.mean(stats["fps_list"])),
            "avg_yolo_latency_ms": float(np.mean(stats["yolo_time"]) * 1000),
            "avg_fire_latency_ms": float(np.mean(stats["fire_time"]) * 1000),
        },
        "detections": stats["detections"]
    }
    
    with open("eval_report.json", "w") as f:
        json.dump(report, f, indent=4)
    
    print("\n" + "="*30)
    print(" EVALUATION COMPLETE ")
    print("="*30)
    print(f"Total Frames: {report['total_frames']}")
    print(f"Average FPS: {report['performance']['avg_fps']:.2f}")
    print(f"YOLO Latency: {report['performance']['avg_yolo_latency_ms']:.1f}ms")
    print(f"Fire Latency: {report['performance']['avg_fire_latency_ms']:.1f}ms")
    print(f"Detections: {report['detections']}")
    print("Report saved to: eval_report.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("video")
    args = parser.parse_args()
    evaluate_video(args.video)
