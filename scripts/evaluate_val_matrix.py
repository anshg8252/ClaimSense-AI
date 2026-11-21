"""Complete validation evaluation across all Phase 9.20 candidates + baseline.

Evaluates on datasets/CarDD_Expanded_v1/val (45 images) at:
1. Fixed threshold tau = 0.25
2. Calibrated per-class thresholds
Outputs runs/phase9_20/evaluations/val_evaluation_matrix.json
"""

import os
import time
import json
import hashlib
from collections import defaultdict
from pathlib import Path
import torch
from ultralytics import YOLO

PROD_BASELINE = "models/phase5/best.pt"
EXPECTED_PROD_SHA = "90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565"

DATASET_EXPANDED = "datasets/CarDD_Expanded_v1/dataset.yaml"
VAL_IMAGES_DIR = "datasets/CarDD_Expanded_v1/val/images"
VAL_LABELS_DIR = "datasets/CarDD_Expanded_v1/val/labels"

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


def get_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while c := f.read(65536):
            h.update(c)
    return h.hexdigest()


def evaluate_checkpoint(name, model_path, imgsz, conf_mode="fixed"):
    model = YOLO(model_path)
    img_files = sorted(Path(VAL_IMAGES_DIR).glob("*.jpg"))
    assert len(img_files) == 45, f"Expected 45 validation images, got {len(img_files)}"

    effective_thresh = (
        CALIBRATED_THRESHOLDS
        if conf_mode == "calibrated"
        else {cid: 0.25 for cid in range(6)}
    )
    base_conf = min(effective_thresh.values())

    gt_by_class = defaultdict(int)
    tp_by_class = defaultdict(int)
    fp_by_class = defaultdict(int)
    latencies = []

    for img_p in img_files:
        stem = img_p.stem
        lbl_p = Path(VAL_LABELS_DIR) / f"{stem}.txt"

        gt_boxes = []
        if lbl_p.exists():
            with open(lbl_p) as f:
                for line in f:
                    parts = line.strip().split()
                    if parts:
                        cid = int(parts[0])
                        gt_by_class[cid] += 1
                        gt_boxes.append((cid, [float(x) for x in parts[1:]]))

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
            for b in results[0].boxes:
                cid = int(b.cls[0].item())
                conf = float(b.conf[0].item())
                if conf >= effective_thresh.get(cid, 0.25):
                    pred_boxes.append((cid, conf, b.xywhn[0].tolist()))

        matched_gt = set()
        for p_cid, p_conf, p_xywh in pred_boxes:
            match_found = False
            for gt_idx, (g_cid, g_xywh) in enumerate(gt_boxes):
                if gt_idx in matched_gt or p_cid != g_cid:
                    continue
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
                union = (px2 - px1) * (py2 - py1) + (gx2 - gx1) * (gy2 - gy1) - inter
                iou = inter / union if union > 0 else 0.0

                if iou >= 0.50:
                    match_found = True
                    matched_gt.add(gt_idx)
                    break

            if match_found:
                tp_by_class[p_cid] += 1
            else:
                fp_by_class[p_cid] += 1

    # Official val run
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

    per_class = {}
    tot_tp = sum(tp_by_class.values())
    tot_fp = sum(fp_by_class.values())
    tot_gt = sum(gt_by_class.values())

    for cid in range(6):
        cname = CARDD_NAMES[cid]
        tp = tp_by_class[cid]
        fp = fp_by_class[cid]
        gt = gt_by_class[cid]
        p = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        r = tp / gt if gt > 0 else 0.0
        f1 = (2 * p * r) / (p + r) if (p + r) > 0 else 0.0
        per_class[cname] = {
            "class_id": cid,
            "tp": tp,
            "fp": fp,
            "gt": gt,
            "precision": round(p, 4),
            "recall": round(r, 4),
            "f1": round(f1, 4),
        }

    op = tot_tp / (tot_tp + tot_fp) if (tot_tp + tot_fp) > 0 else 0.0
    or_ = tot_tp / tot_gt if tot_gt > 0 else 0.0
    of1 = (2 * op * or_) / (op + or_) if (op + or_) > 0 else 0.0

    return {
        "conf_mode": conf_mode,
        "effective_thresholds": {CARDD_NAMES[k]: v for k, v in effective_thresh.items()},
        "overall": {
            "precision": round(op, 4),
            "recall": round(or_, 4),
            "f1": round(of1, 4),
            "mAP50": round(map50, 4),
            "mAP50_95": round(map50_95, 4),
            "total_tp": tot_tp,
            "total_fp": tot_fp,
            "total_gt": tot_gt,
            "mean_latency_ms": round(sum(latencies) / len(latencies), 2),
        },
        "per_class": per_class,
    }


def main():
    actual_prod = get_sha256(PROD_BASELINE)
    assert actual_prod == EXPECTED_PROD_SHA, f"Safety violation: {actual_prod}"

    models_to_eval = [
        ("BASELINE_Phase5", PROD_BASELINE, 640),
        ("P920_EXP01_loss_rebalance", "runs/phase9_20/checkpoints/P920_EXP01_loss_rebalance/weights/best.pt", 640),
        ("P920_EXP02_box_refinement", "runs/phase9_20/checkpoints/P920_EXP02_box_refinement/weights/best.pt", 640),
        ("P920_EXP03_hires_704", "runs/phase9_20/checkpoints/P920_EXP03_hires_704/weights/best.pt", 704),
        ("P920_EXP04_phase5_finetune", "runs/phase9_20/checkpoints/P920_EXP04_phase5_finetune/weights/best.pt", 640),
        ("P920_EXP05_hires_finetune", "runs/phase9_20/checkpoints/P920_EXP05_hires_finetune/weights/best.pt", 704),
        ("P920_EXP06_regularized", "runs/phase9_20/checkpoints/P920_EXP06_regularized/weights/best.pt", 640),
    ]

    all_records = []

    for name, path, imgsz in models_to_eval:
        print(f"\nEvaluating: {name} (imgsz={imgsz})")
        sha = get_sha256(path)
        eval_fixed = evaluate_checkpoint(name, path, imgsz, conf_mode="fixed")
        eval_calib = evaluate_checkpoint(name, path, imgsz, conf_mode="calibrated")

        record = {
            "model_name": name,
            "checkpoint_path": path,
            "sha256": sha,
            "imgsz": imgsz,
            "fixed_tau_025": eval_fixed,
            "calibrated_per_class": eval_calib,
        }
        all_records.append(record)

    out_file = "runs/phase9_20/evaluations/val_evaluation_matrix.json"
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(all_records, f, indent=2)

    print(f"\nEvaluation matrix saved to {out_file}")


if __name__ == "__main__":
    main()
