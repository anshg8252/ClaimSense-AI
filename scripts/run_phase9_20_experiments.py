"""ClaimSense AI — Phase 9.20 Controlled GPU Model Experiments Runner.

Executes experiments EXP20-01 through EXP20-06 on NVIDIA RTX 3050 Laptop GPU.
Maintains strict production invariants and quarantines historical test sets.
"""

import os
import sys
import time
import json
import shutil
import hashlib
from collections import defaultdict
from pathlib import Path

import torch
from ultralytics import YOLO

# Production Invariants
PROD_BASELINE = "models/phase5/best.pt"
EXPECTED_PROD_SHA = "90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565"
PROD_DB = "backend/database/claimsense.db"
EXPECTED_DB_SHA = "b493fad6694f1e5493b0f283fee9a3f65bdfc3d41ca3792cbb6f90a80f644598"

DATASET_EXPANDED = "datasets/CarDD_Expanded_v1/dataset.yaml"
OUTPUT_DIR = "runs/phase9_20/checkpoints"
LOGS_DIR = "runs/phase9_20/logs"
EVALS_DIR = "runs/phase9_20/evaluations"

CARDD_NAMES = {
    0: "dent",
    1: "scratch",
    2: "crack",
    3: "glass shatter",
    4: "lamp broken",
    5: "tire flat",
}

CALIBRATED_THRESHOLDS = {
    0: 0.18,  # dent
    1: 0.28,  # scratch
    2: 0.25,  # crack
    3: 0.22,  # glass shatter
    4: 0.25,  # lamp broken
    5: 0.25,  # tire flat
}


def compute_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def verify_production_invariants():
    """Guarantees production checkpoint and database immutability."""
    actual_prod = compute_sha256(PROD_BASELINE)
    assert actual_prod == EXPECTED_PROD_SHA, (
        f"CRITICAL SAFETY VIOLATION: models/phase5/best.pt has been altered! {actual_prod}"
    )

    actual_db = compute_sha256(PROD_DB)
    assert actual_db == EXPECTED_DB_SHA, (
        f"CRITICAL SAFETY VIOLATION: claimsense.db has been altered! {actual_db}"
    )

    print(f"[SAFETY GUARANTEE] Production Model Verified: {actual_prod}")
    print(f"[SAFETY GUARANTEE] Production Database Verified: {actual_db}")


def evaluate_model_on_val(model_path: str, conf_mode="fixed", imgsz=640):
    """Evaluates a checkpoint on the validation set at fixed or per-class thresholds."""
    model = YOLO(model_path)
    val_images_dir = "datasets/CarDD_Expanded_v1/val/images"
    val_labels_dir = "datasets/CarDD_Expanded_v1/val/labels"

    img_files = sorted(Path(val_images_dir).glob("*.jpg"))
    assert len(img_files) == 45, f"Expected 45 validation images, found {len(img_files)}"

    effective_thresh = (
        CALIBRATED_THRESHOLDS
        if conf_mode == "calibrated"
        else {cid: 0.25 for cid in range(6)}
    )
    base_conf = min(effective_thresh.values())

    # Accumulate metrics
    gt_by_class = defaultdict(int)
    tp_by_class = defaultdict(int)
    fp_by_class = defaultdict(int)

    latencies = []

    for img_p in img_files:
        stem = img_p.stem
        lbl_p = Path(val_labels_dir) / f"{stem}.txt"

        # Load GT boxes
        gt_boxes = []
        if lbl_p.exists():
            with open(lbl_p) as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        cid = int(parts[0])
                        gt_by_class[cid] += 1
                        gt_boxes.append((cid, [float(x) for x in parts[1:]]))

        # Run inference
        t0 = time.perf_counter()
        results = model.predict(
            source=str(img_p),
            conf=base_conf,
            iou=0.45,
            imgsz=imgsz,
            device=0,
            verbose=False,
        )
        latencies.append((time.perf_counter() - t0) * 1000.0)

        pred_boxes = []
        if results and len(results) > 0 and results[0].boxes is not None:
            res_boxes = results[0].boxes
            for b in res_boxes:
                cid = int(b.cls[0].item())
                conf = float(b.conf[0].item())
                if conf >= effective_thresh.get(cid, 0.25):
                    # Normalized xywh
                    xywhn = b.xywhn[0].tolist()
                    pred_boxes.append((cid, conf, xywhn))

        # Evaluate matches at IoU 0.50
        matched_gt = set()
        for p_cid, p_conf, p_xywh in pred_boxes:
            match_found = False
            for gt_idx, (g_cid, g_xywh) in enumerate(gt_boxes):
                if gt_idx in matched_gt or p_cid != g_cid:
                    continue
                # Calculate IoU
                px1 = p_xywh[0] - p_xywh[2] / 2
                py1 = p_xywh[1] - p_xywh[3] / 2
                px2 = p_xywh[0] + p_xywh[2] / 2
                py2 = p_xywh[1] + p_xywh[3] / 2

                gx1 = g_xywh[0] - g_xywh[2] / 2
                gy1 = g_xywh[1] - g_xywh[3] / 2
                gx2 = g_xywh[0] + g_xywh[2] / 2
                gy2 = g_xywh[1] + g_xywh[3] / 2

                ix1 = max(px1, gx1)
                iy1 = max(py1, gy1)
                ix2 = min(px2, gx2)
                iy2 = min(py2, gy2)

                iw = max(0.0, ix2 - ix1)
                ih = max(0.0, iy2 - iy1)
                inter = iw * ih

                p_area = (px2 - px1) * (py2 - py1)
                g_area = (gx2 - gx1) * (gy2 - gy1)
                union = p_area + g_area - inter
                iou = inter / union if union > 0 else 0.0

                if iou >= 0.50:
                    match_found = True
                    matched_gt.add(gt_idx)
                    break

            if match_found:
                tp_by_class[p_cid] += 1
            else:
                fp_by_class[p_cid] += 1

    # Standard Ultralytics val run for overall mAP50 and mAP50-95
    val_res = model.val(
        data=DATASET_EXPANDED,
        split="val",
        imgsz=imgsz,
        batch=16,
        conf=base_conf,
        iou=0.45,
        device=0,
        verbose=False,
    )
    map50 = float(val_res.results_dict.get("metrics/mAP50(B)", 0.0))
    map50_95 = float(val_res.results_dict.get("metrics/mAP50-95(B)", 0.0))

    # Calculate per-class metrics
    per_class_metrics = {}
    tot_tp = sum(tp_by_class.values())
    tot_fp = sum(fp_by_class.values())
    tot_gt = sum(gt_by_class.values())

    macro_p = []
    macro_r = []

    for cid in range(6):
        cname = CARDD_NAMES[cid]
        tp = tp_by_class[cid]
        fp = fp_by_class[cid]
        gt = gt_by_class[cid]
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / gt if gt > 0 else 0.0
        f1 = (2 * prec * rec) / (prec + rec) if (prec + rec) > 0 else 0.0
        per_class_metrics[cname] = {
            "class_id": cid,
            "tp": tp,
            "fp": fp,
            "gt": gt,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
        }
        if gt > 0:
            macro_p.append(prec)
            macro_r.append(rec)

    overall_prec = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) > 0 else 0.0
    overall_rec = tot_tp / tot_gt if tot_gt > 0 else 0.0
    overall_f1 = (
        (2 * overall_prec * overall_rec) / (overall_prec + overall_rec)
        if (overall_prec + overall_rec) > 0
        else 0.0
    )

    return {
        "conf_mode": conf_mode,
        "effective_thresholds": effective_thresh,
        "overall": {
            "precision": round(overall_prec, 4),
            "recall": round(overall_rec, 4),
            "f1": round(overall_f1, 4),
            "mAP50": round(map50, 4),
            "mAP50_95": round(map50_95, 4),
            "total_tp": tot_tp,
            "total_fp": tot_fp,
            "total_gt": tot_gt,
            "mean_latency_ms": round(sum(latencies) / len(latencies), 2),
        },
        "per_class": per_class_metrics,
    }


def run_experiment(exp_id, init_weights, imgsz, epochs, batch, lr0, loss_kwargs):
    """Executes a single controlled GPU training run."""
    print(f"\n=======================================================")
    print(f"RUNNING EXPERIMENT: {exp_id}")
    print(f"Init: {init_weights}, imgsz: {imgsz}, epochs: {epochs}, batch: {batch}, lr0: {lr0}")
    print(f"Loss params: {loss_kwargs}")
    print(f"=======================================================\n")

    verify_production_invariants()
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    exp_dir = os.path.join(OUTPUT_DIR, exp_id)
    os.makedirs(exp_dir, exist_ok=True)

    # Initialize model
    model = YOLO(init_weights)

    train_args = {
        "data": DATASET_EXPANDED,
        "epochs": epochs,
        "imgsz": imgsz,
        "batch": batch,
        "lr0": lr0,
        "device": 0,
        "seed": 42,
        "deterministic": True,
        "project": OUTPUT_DIR,
        "name": exp_id,
        "exist_ok": True,
        "plots": True,
        "save": True,
        "verbose": False,
    }
    train_args.update(loss_kwargs)

    t0 = time.time()
    train_results = model.train(**train_args)
    duration = time.time() - t0
    peak_vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)

    # Best checkpoint path
    best_pt = os.path.join(exp_dir, "weights", "best.pt")
    if not os.path.exists(best_pt):
        # Fall back to root of run if ultralytics placed it there
        alt_best = os.path.join(OUTPUT_DIR, exp_id, "weights", "best.pt")
        if os.path.exists(alt_best):
            best_pt = alt_best

    assert os.path.exists(best_pt), f"Best checkpoint not found for {exp_id} at {best_pt}!"
    best_sha = compute_sha256(best_pt)

    print(f"[{exp_id}] Training completed in {duration:.1f}s. Peak VRAM: {peak_vram_mb:.1f}MB.")
    print(f"[{exp_id}] Best Checkpoint SHA-256: {best_sha}")

    # Evaluate at fixed 0.25
    eval_fixed = evaluate_model_on_val(best_pt, conf_mode="fixed", imgsz=imgsz)
    # Evaluate at calibrated per-class thresholds
    eval_calibrated = evaluate_model_on_val(best_pt, conf_mode="calibrated", imgsz=imgsz)

    return {
        "experiment_id": exp_id,
        "checkpoint_path": best_pt,
        "sha256": best_sha,
        "duration_seconds": round(duration, 1),
        "peak_vram_mb": round(peak_vram_mb, 1),
        "parameters": {
            "init_weights": init_weights,
            "imgsz": imgsz,
            "epochs": epochs,
            "batch": batch,
            "lr0": lr0,
            "loss_params": loss_kwargs,
        },
        "evaluation_fixed": eval_fixed,
        "evaluation_calibrated": eval_calibrated,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)
    os.makedirs(EVALS_DIR, exist_ok=True)

    verify_production_invariants()

    # First, evaluate the production baseline under identical conditions
    print("\n--- Evaluating Production Baseline (models/phase5/best.pt) ---")
    base_eval_fixed = evaluate_model_on_val(PROD_BASELINE, conf_mode="fixed", imgsz=640)
    base_eval_calib = evaluate_model_on_val(PROD_BASELINE, conf_mode="calibrated", imgsz=640)

    baseline_record = {
        "experiment_id": "BASELINE_Phase5",
        "checkpoint_path": PROD_BASELINE,
        "sha256": EXPECTED_PROD_SHA,
        "duration_seconds": 0.0,
        "peak_vram_mb": 412.0,
        "parameters": {
            "init_weights": "Pre-trained Phase 5 Production Model",
            "imgsz": 640,
            "epochs": 25,
            "batch": 16,
            "loss_params": "box=7.5, cls=0.5, dfl=1.5",
        },
        "evaluation_fixed": base_eval_fixed,
        "evaluation_calibrated": base_eval_calib,
    }

    experiment_definitions = [
        (
            "P920_EXP01_loss_rebalance",
            "yolov8n.pt",
            640,
            25,
            16,
            0.01,
            {"box": 7.5, "cls": 0.85, "dfl": 1.5},
        ),
        (
            "P920_EXP02_box_refinement",
            "yolov8n.pt",
            640,
            25,
            16,
            0.01,
            {"box": 8.0, "cls": 0.80, "dfl": 1.8},
        ),
        (
            "P920_EXP03_hires_704",
            "yolov8n.pt",
            704,
            25,
            12,
            0.01,
            {"box": 7.5, "cls": 0.85, "dfl": 1.5},
        ),
        (
            "P920_EXP04_phase5_finetune",
            PROD_BASELINE,
            640,
            20,
            16,
            0.001,
            {"box": 7.5, "cls": 0.85, "dfl": 1.5},
        ),
        (
            "P920_EXP05_hires_finetune",
            PROD_BASELINE,
            704,
            20,
            12,
            0.001,
            {"box": 8.0, "cls": 0.80, "dfl": 1.5},
        ),
        (
            "P920_EXP06_regularized",
            "yolov8n.pt",
            640,
            25,
            16,
            0.01,
            {"box": 7.5, "cls": 0.90, "dfl": 1.5, "mixup": 0.1},
        ),
    ]

    all_results = [baseline_record]

    for exp_id, init_w, imgsz, epochs, batch, lr0, loss_kwargs in experiment_definitions:
        res = run_experiment(exp_id, init_w, imgsz, epochs, batch, lr0, loss_kwargs)
        all_results.append(res)
        verify_production_invariants()

    # Save full evaluation matrix
    out_matrix = os.path.join(EVALS_DIR, "val_evaluation_matrix.json")
    with open(out_matrix, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    print(f"\nAll 6 experiments completed and recorded in {out_matrix}")


if __name__ == "__main__":
    main()
