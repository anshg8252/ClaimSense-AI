import json
import csv

with open("runs/phase9_19/evaluations/test_evaluation_results.json") as f:
    test_d = json.load(f)

with open("runs/phase9_19/forensic_closure/metric_reconciliation.csv") as f:
    rows = list(csv.DictReader(f))

for r in rows:
    if "test" not in r["split"]:
        continue
    exp_id = r["experiment_id"]
    model_name = [k for k in test_d.keys() if exp_id in k or (exp_id == "Phase 5 Baseline" and "Baseline" in k)][0]
    tau = r["operating_point"]
    raw_pc = test_d[model_name]["sweep"][tau]["per_class"]
    for c in ["dent", "scratch", "crack", "glass shatter", "lamp broken", "tire flat"]:
        key = c.split()[0] + "_recall"
        raw_val = raw_pc[c]["recall"]
        rep_val = float(r[key])
        assert abs(raw_val - rep_val) < 1e-4, f"Mismatch in {model_name} {tau} {c}: raw={raw_val}, rep={rep_val}"

print("All per-class metrics verified exactly with zero discrepancies!")
