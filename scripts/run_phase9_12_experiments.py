import os
import sys
import json
import hashlib
import time
import torch
from ultralytics import YOLO

PROD_BASELINE = "models/phase5/best.pt"
DATASET_YAML = "datasets/CarDD_Expanded_v1/dataset.yaml"
EXP_DIR = "runs/phase9_12/experiments"

def compute_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def verify_prod_invariant():
    expected = "90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565"
    actual = compute_sha256(PROD_BASELINE)
    assert actual == expected, f"CRITICAL SAFETY VIOLATION: Production model modified! {actual} != {expected}"
    print(f"[SAFETY CHECK] Production model verified invariant: {actual}")

def run_experiment(name, imgsz=640, epochs=25, batch=16, extra_args=None):
    print(f"\n=======================================================")
    print(f"Starting Experiment: {name}")
    print(f"imgsz={imgsz}, epochs={epochs}, batch={batch}")
    print(f"=======================================================\n")

    save_dir = os.path.join(EXP_DIR, name)
    os.makedirs(save_dir, exist_ok=True)

    # Initialize from pristine yolov8n.pt
    model = YOLO("yolov8n.pt")

    train_args = {
        "data": DATASET_YAML,
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch,
        "device": 0,
        "seed": 42,
        "deterministic": True,
        "project": EXP_DIR,
        "name": name,
        "exist_ok": True,
        "plots": True,
        "save": True,
        "verbose": False
    }
    if extra_args:
        train_args.update(extra_args)

    start_time = time.time()
    results = model.train(**train_args)
    duration = time.time() - start_time
    print(f"Training completed in {duration:.2f}s")

    best_pt = os.path.join(save_dir, "weights", "best.pt")
    assert os.path.exists(best_pt), f"best.pt not found at {best_pt}"
    best_sha = compute_sha256(best_pt)
    print(f"Candidate best.pt generated: {best_pt} (SHA256: {best_sha})")

    # Safety check after training
    verify_prod_invariant()

    return best_pt, duration

if __name__ == "__main__":
    verify_prod_invariant()
    os.makedirs(EXP_DIR, exist_ok=True)

    # Experiment 1: Expanded Baseline
    exp1_best, d1 = run_experiment("P912_EXP01_expanded_base", imgsz=640, epochs=25, batch=16)

    # Experiment 2: High Resolution
    exp2_best, d2 = run_experiment("P912_EXP02_hires_800", imgsz=800, epochs=25, batch=8)

    # Experiment 3: Loss Weighted & Augmentation Tuning
    exp3_best, d3 = run_experiment(
        "P912_EXP03_loss_tuned",
        imgsz=640,
        epochs=25,
        batch=16,
        extra_args={"box": 8.5, "cls": 1.2, "close_mosaic": 5}
    )

    print("\nAll 3 retraining experiments completed successfully!")
