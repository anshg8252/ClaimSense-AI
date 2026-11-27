import json
import os

with open("runs/phase9_19/evaluations/val_evaluation_results.json") as f:
    val_data = json.load(f)

with open("runs/phase9_19/evaluations/test_evaluation_results.json") as f:
    test_data = json.load(f)

print("=== VALIDATION SPLIT (tau=0.25) ===")
for k, v in val_data.items():
    m = v["op_tau_025"]
    pc = m["per_class"]
    print(f"{k:32} | mAP50: {v['map50']:.4f} | Prec: {m['precision']:.4f} | Rec: {m['recall']:.4f} | F1: {m['f1']:.4f} | Dent: {pc['dent']['recall']:.4f} | Crack: {pc['crack']['recall']:.4f} | Scratch: {pc['scratch']['recall']:.4f} | Lat: {v['avg_latency_ms']}ms")

print("\n=== HELD-OUT TEST SPLIT (tau=0.25) ===")
for k, v in test_data.items():
    m = v["op_tau_025"]
    pc = m["per_class"]
    print(f"{k:32} | mAP50: {v['map50']:.4f} | Prec: {m['precision']:.4f} | Rec: {m['recall']:.4f} | F1: {m['f1']:.4f} | Dent: {pc['dent']['recall']:.4f} | Crack: {pc['crack']['recall']:.4f} | Scratch: {pc['scratch']['recall']:.4f} | Lat: {v['avg_latency_ms']}ms")

print("\n=== HELD-OUT TEST SPLIT (tau=0.10) ===")
for k, v in test_data.items():
    m = v["op_tau_010"]
    pc = m["per_class"]
    print(f"{k:32} | Prec: {m['precision']:.4f} | Rec: {m['recall']:.4f} | F1: {m['f1']:.4f} | Dent: {pc['dent']['recall']:.4f} | Crack: {pc['crack']['recall']:.4f} | Scratch: {pc['scratch']['recall']:.4f} | FP: {m['fp']}")

print("\n=== PER CLASS COUNTS ON TEST SPLIT (tau=0.25) ===")
for k, v in test_data.items():
    print(f"\nModel: {k}")
    m = v["op_tau_025"]
    for c_name, c_metrics in m["per_class"].items():
        print(f"  {c_name:15}: GT={c_metrics['gt']}, TP={c_metrics['tp']}, FP={c_metrics['fp']}, FN={c_metrics['fn']}, P={c_metrics['precision']:.4f}, R={c_metrics['recall']:.4f}, F1={c_metrics['f1']:.4f}")
