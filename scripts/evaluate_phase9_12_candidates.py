import os
import glob
import json
import time
import hashlib
from collections import defaultdict
import numpy as np
import torch
from PIL import Image
from ultralytics import YOLO

CLASSES = ["dent", "scratch", "crack", "glass shatter", "lamp broken", "tire flat"]
TEST_IMG_DIR = "datasets/CarDD_300/test/images"
TEST_LBL_DIR = "datasets/CarDD_300/test/labels"
OUT_JSON = "runs/phase9_12/evaluation_results.json"

def compute_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def box_iou(b1, b2):
    # b: [x1, y1, x2, y2] normalized
    xA = max(b1[0], b2[0])
    yA = max(b1[1], b2[1])
    xB = min(b1[2], b2[2])
    yB = min(b1[3], b2[3])
    inter = max(0.0, xB - xA) * max(0.0, yB - yA)
    area1 = (b1[2] - b1[0]) * (b1[3] - b1[1])
    area2 = (b2[2] - b2[0]) * (b2[3] - b2[1])
    union = area1 + area2 - inter
    return inter / union if union > 0 else 0.0

def load_ground_truth():
    gt = {}
    lbl_files = glob.glob(os.path.join(TEST_LBL_DIR, "*.txt"))
    for lf in lbl_files:
        stem = os.path.splitext(os.path.basename(lf))[0]
        boxes = []
        with open(lf, "r") as f:
            for line in f:
                parts = line.strip().split()
                if not parts: continue
                c = int(parts[0])
                cx, cy, w, h = map(float, parts[1:5])
                x1, y1, x2, y2 = cx - w/2, cy - h/2, cx + w/2, cy + h/2
                boxes.append({"cls": c, "box": [x1, y1, x2, y2], "area": w*h})
        gt[stem] = boxes
    return gt

def evaluate_model(model_name, weight_path, gt_data, iou_thresh=0.40):
    print(f"\n==========================================")
    print(f"Evaluating {model_name} ({weight_path})")
    print(f"==========================================")

    sha256_hash = compute_sha256(weight_path)
    model = YOLO(weight_path)

    # 1. Official YOLO val metrics on test set
    val_res = model.val(
        data="datasets/CarDD_Expanded_v1/dataset.yaml",
        split="test",
        device=0,
        verbose=False,
        plots=False
    )

    map50 = float(val_res.box.map50)
    map50_95 = float(val_res.box.map)
    class_map50 = {CLASSES[i]: float(val_res.box.maps[i]) for i in range(len(CLASSES))} if len(val_res.box.maps) == len(CLASSES) else {}

    # 2. Latency benchmark (warmup + 45 test images)
    test_imgs = sorted(glob.glob(os.path.join(TEST_IMG_DIR, "*.jpg")))
    # Warmup
    for _ in range(5):
        _ = model.predict(test_imgs[0], device=0, verbose=False)

    latencies = []
    all_predictions = {}
    for im in test_imgs:
        stem = os.path.splitext(os.path.basename(im))[0]
        t0 = time.perf_counter()
        res = model.predict(im, conf=0.01, device=0, verbose=False)[0]
        latencies.append((time.perf_counter() - t0) * 1000.0)

        preds = []
        for box in res.boxes:
            c = int(box.cls[0].item())
            conf = float(box.conf[0].item())
            xyxyn = box.xyxyn[0].tolist()
            preds.append({"cls": c, "conf": conf, "box": xyxyn})
        all_predictions[stem] = preds

    avg_latency_ms = float(np.mean(latencies))

    # 3. Operational threshold sweep
    thresholds = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.50]
    sweep_results = {}

    for tau in thresholds:
        tp_per_class = defaultdict(int)
        fp_per_class = defaultdict(int)
        fn_per_class = defaultdict(int)
        gt_counts = defaultdict(int)

        for stem, gt_boxes in gt_data.items():
            preds = [p for p in all_predictions[stem] if p["conf"] >= tau]
            # sort preds by confidence desc
            preds = sorted(preds, key=lambda x: x["conf"], reverse=True)

            matched_gt = set()
            for p in preds:
                p_cls = p["cls"]
                best_iou = 0.0
                best_g_idx = -1
                for g_idx, g in enumerate(gt_boxes):
                    if g_idx in matched_gt: continue
                    if g["cls"] != p_cls: continue
                    iou = box_iou(p["box"], g["box"])
                    if iou > best_iou:
                        best_iou = iou
                        best_g_idx = g_idx
                if best_iou >= iou_thresh and best_g_idx >= 0:
                    matched_gt.add(best_g_idx)
                    tp_per_class[p_cls] += 1
                else:
                    fp_per_class[p_cls] += 1

            for g_idx, g in enumerate(gt_boxes):
                gt_counts[g["cls"]] += 1
                if g_idx not in matched_gt:
                    fn_per_class[g["cls"]] += 1

        total_tp = sum(tp_per_class.values())
        total_fp = sum(fp_per_class.values())
        total_fn = sum(fn_per_class.values())
        total_gt = sum(gt_counts.values())

        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
        recall = total_tp / total_gt if total_gt > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        per_class_metrics = {}
        for c_idx, c_name in enumerate(CLASSES):
            c_tp = tp_per_class[c_idx]
            c_fp = fp_per_class[c_idx]
            c_fn = fn_per_class[c_idx]
            c_gt = gt_counts[c_idx]
            c_prec = c_tp / (c_tp + c_fp) if (c_tp + c_fp) > 0 else 0.0
            c_rec = c_tp / c_gt if c_gt > 0 else 0.0
            c_f1 = 2 * c_prec * c_rec / (c_prec + c_rec) if (c_prec + c_rec) > 0 else 0.0
            per_class_metrics[c_name] = {
                "tp": c_tp, "fp": c_fp, "fn": c_fn, "gt": c_gt,
                "precision": round(c_prec, 4), "recall": round(c_rec, 4), "f1": round(c_f1, 4)
            }

        sweep_results[f"tau_{tau:.2f}"] = {
            "overall": {
                "tp": total_tp, "fp": total_fp, "fn": total_fn, "gt": total_gt,
                "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)
            },
            "per_class": per_class_metrics
        }

    res_obj = {
        "model_name": model_name,
        "weight_path": weight_path,
        "sha256": sha256_hash,
        "map50": round(map50, 4),
        "map50_95": round(map50_95, 4),
        "class_map50": class_map50,
        "avg_latency_ms": round(avg_latency_ms, 2),
        "sweep_results": sweep_results
    }

    # Print summary at standard tau=0.25
    s025 = sweep_results["tau_0.25"]
    print(f"Metrics @ tau=0.25 (IoU >= {iou_thresh}):")
    print(f"  Overall mAP50={map50:.4f}, mAP50-95={map50_95:.4f}, Latency={avg_latency_ms:.1f}ms")
    print(f"  Precision={s025['overall']['precision']}, Recall={s025['overall']['recall']}, F1={s025['overall']['f1']}")
    print(f"  Crack Recall: {s025['per_class']['crack']['recall']} ({s025['per_class']['crack']['tp']}/{s025['per_class']['crack']['gt']})")
    print(f"  Scratch Recall: {s025['per_class']['scratch']['recall']} ({s025['per_class']['scratch']['tp']}/{s025['per_class']['scratch']['gt']})")
    print(f"  Dent Recall: {s025['per_class']['dent']['recall']} ({s025['per_class']['dent']['tp']}/{s025['per_class']['dent']['gt']})")

    return res_obj

if __name__ == "__main__":
    gt_data = load_ground_truth()
    models_to_eval = [
        ("Phase 5 Baseline (Production)", "models/phase5/best.pt"),
        ("P912-EXP01 Expanded Base", "runs/phase9_12/experiments/P912_EXP01_expanded_base/weights/best.pt"),
        ("P912-EXP02 HiRes 800", "runs/phase9_12/experiments/P912_EXP02_hires_800/weights/best.pt"),
        ("P912-EXP03 Loss Tuned", "runs/phase9_12/experiments/P912_EXP03_loss_tuned/weights/best.pt")
    ]

    all_results = {}
    for name, path in models_to_eval:
        if os.path.exists(path):
            all_results[name] = evaluate_model(name, path, gt_data)
        else:
            print(f"Skipping {name}: {path} does not exist yet.")

    with open(OUT_JSON, "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nAll evaluations saved to {OUT_JSON}")
