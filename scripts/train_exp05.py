"""Train EXP05 cleanly with batch=8 and proper main guard."""
import time
import hashlib
from ultralytics import YOLO

PROD_BASELINE = "models/phase5/best.pt"
EXPECTED_PROD_SHA = "90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565"

def verify_prod():
    h = hashlib.sha256()
    with open(PROD_BASELINE, "rb") as f:
        while c := f.read(65536): h.update(c)
    actual = h.hexdigest()
    assert actual == EXPECTED_PROD_SHA, f"Safety violation: {actual}"
    print(f"[SAFETY GUARANTEE] Production baseline verified: {actual}")

def main():
    verify_prod()
    model = YOLO(PROD_BASELINE)
    t0 = time.time()
    model.train(
        data="datasets/CarDD_Expanded_v1/dataset.yaml",
        epochs=20,
        imgsz=704,
        batch=8,
        workers=4,
        lr0=0.001,
        box=8.0,
        cls=0.80,
        dfl=1.5,
        device=0,
        seed=42,
        deterministic=True,
        project="runs/phase9_20/checkpoints",
        name="P920_EXP05_hires_finetune",
        exist_ok=True,
        plots=True,
        save=True,
        verbose=False,
    )
    print(f"EXP05 training finished in {time.time() - t0:.1f}s")
    verify_prod()

if __name__ == "__main__":
    main()
