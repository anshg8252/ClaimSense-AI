import os
import glob
import hashlib
import json
import csv

checkpoints_dir = "runs/detect/runs/phase9_20/checkpoints"
experiments = sorted(os.listdir(checkpoints_dir))
report = {}

for exp in experiments:
    exp_path = os.path.join(checkpoints_dir, exp)
    if not os.path.isdir(exp_path):
        continue
    best_pt = os.path.join(exp_path, "weights", "best.pt")
    last_pt = os.path.join(exp_path, "weights", "last.pt")
    results_csv = os.path.join(exp_path, "results.csv")
    args_yaml = os.path.join(exp_path, "args.yaml")
    
    best_sha = None
    best_size = 0
    if os.path.exists(best_pt):
        h = hashlib.sha256()
        with open(best_pt, "rb") as f:
            while c := f.read(65536):
                h.update(c)
        best_sha = h.hexdigest()
        best_size = os.path.getsize(best_pt)
    
    last_sha = None
    last_size = 0
    if os.path.exists(last_pt):
        h = hashlib.sha256()
        with open(last_pt, "rb") as f:
            while c := f.read(65536):
                h.update(c)
        last_sha = h.hexdigest()
        last_size = os.path.getsize(last_pt)
        
    epochs_csv = 0
    last_epoch = None
    final_metrics = {}
    if os.path.exists(results_csv):
        with open(results_csv, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = [h.strip() for h in next(reader, [])]
            rows = list(reader)
            epochs_csv = len(rows)
            if rows:
                last_row = [v.strip() for v in rows[-1]]
                row_dict = dict(zip(headers, last_row))
                last_epoch = int(row_dict.get("epoch", -1))
                final_metrics = {}
                for k, v in row_dict.items():
                    try:
                        final_metrics[k] = float(v)
                    except ValueError:
                        final_metrics[k] = v
    
    args = {}
    if os.path.exists(args_yaml):
        with open(args_yaml, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if ":" in line:
                    k, v = line.split(":", 1)
                    k = k.strip()
                    v = v.strip()
                    args[k] = v
            
    report[exp] = {
        "best_size": best_size,
        "best_sha": best_sha,
        "last_size": last_size,
        "last_sha": last_sha,
        "results_csv_rows": epochs_csv,
        "last_epoch": last_epoch,
        "target_epochs": args.get("epochs"),
        "imgsz": args.get("imgsz"),
        "batch": args.get("batch"),
        "lr0": args.get("lr0"),
        "box": args.get("box"),
        "cls": args.get("cls"),
        "dfl": args.get("dfl"),
        "model": args.get("model"),
        "data": args.get("data"),
        "final_metrics": final_metrics
    }

with open("runs/phase9_20/training_audit_summary.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2)

print("Audit summary written to runs/phase9_20/training_audit_summary.json")
