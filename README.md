# ClaimSense AI

> **Explainable AI-Assisted Vehicle Insurance Claim Verification & Evidence Cross-Referencing Platform**
> *Academic Decision-Support Prototype &mdash; Final-Year B.Tech Major Project (Session 2026–2027)*

[![Python](https://img.shields.io/badge/Python-3.10%2B%20%7C%203.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/Backend-Flask%20%3E%3D3.0%20(3.1.3%20installed)-black?logo=flask)](https://flask.palletsprojects.com/)
[![ORM](https://img.shields.io/badge/ORM-SQLAlchemy%202.0%2B-red)](https://www.sqlalchemy.org/)
[![Database](https://img.shields.io/badge/Database-SQLite%203%20%7C%20WAL%20Telemetry-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![Computer Vision](https://img.shields.io/badge/Vision-Ultralytics%20YOLOv8-blueviolet)](https://github.com/ultralytics/ultralytics)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.0%2B%20%7C%20CUDA%2012.8-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![Tests](https://img.shields.io/badge/Tests-41%20Vision%20%7C%2040%20Passed%20(1%20Skipped)-brightgreen)](tests/)
[![Governance Status](https://img.shields.io/badge/Governance-Research%20Complete%20%7C%20No%20Promotion-orange)](#-project-status--model-governance)

---

> [!CAUTION]
> ### 🛑 GOVERNANCE STATUS: RESEARCH COMPLETE — NO MODEL PROMOTION
> * **Phase 9.19 Research:** Formally closed.
> * **Phase 9.20 Research & Forensic Verification:** Completed and independently verified.
> * **Active Production Model:** `models/phase5/best.pt` remains the **only authorized production checkpoint** (SHA-256: `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565`).
> * **Candidate Model Status:** All experimental candidate checkpoints (`EXP20-01` through `EXP20-06`) **failed production promotion gates and are rejected for deployment**.
> * **Inference Architecture:** Per-class thresholding is implemented in `backend/services/vision/damage_detector.py` as an **opt-in, backward-compatible software feature**. Production defaults (`conf_threshold = 0.15`, `iou_threshold = 0.45`) remain unmodified.
> * **Next Milestone:** Phase 9.21 is proposed as the next research iteration; it has **not started**.

---

> [!IMPORTANT]
> **Academic Scope & Responsible AI Disclaimer:**
> ClaimSense AI is engineered strictly as an **assistive decision-support prototype** for insurance claims examiners and technical evaluators. It assists human assessors by cross-referencing multi-source evidentiary artifacts (official policy schedules, claim submission forms, repair invoices, claimant accident narratives, and vehicle photographs).
> **ClaimSense AI does NOT autonomously approve, adjust, or deny claims, nor does it assert legal proof of insurance fraud.** All algorithmic findings, damage classifications, and consistency scores require human assessor review and validation.

---

## 👥 Project Team & Academic Governance

* **Institution:** ABES Engineering College, Ghaziabad
* **Department:** Department of Computer Science & Engineering
* **Academic Session:** 2026–2027
* **Faculty Supervisor:** Ms. Sonia Lamba, Assistant Professor, Department of CSE

**Project Contributors:**
1. **Ansh Gupta** &mdash; Roll No. 2300320120051
2. **Ankit Yadav** &mdash; Roll No. 2300320120048
3. **Ananya Chauhan** &mdash; Roll No. 2300320120041

---

## 📌 Project Overview

Motor vehicle insurance claim adjudication routinely requires reconciling disparate, heterogeneous, and often contradictory sources of evidence:
* **Structured Policy Records:** Policy validity windows, insured vehicle registration numbers, coverage terms, and named beneficiaries.
* **Intake Claim Forms:** First-party loss descriptions, claimed incident timestamps, location statements, and driver declarations.
* **Repair Shop Documentation:** Garage work estimates, repair invoices, replacement part descriptions, and labor line items.
* **Claimant Accident Narratives:** Free-text descriptions detailing sequence of events, points of physical impact, and claimed damages.
* **Photographic Evidence:** High-resolution vehicle photographs depicting physical impact, paint scratches, dents, and fractures.

In traditional workflows, manual cross-referencing across these silos is labor-intensive, error-prone, and susceptible to cognitive fatigue. Relying on a single automated model introduces severe brittleness: an algorithm cannot discern whether a detected dent existed before the collision or whether a repair shop billed for a bumper that the photograph proves is completely undamaged.

**ClaimSense AI** solves this challenge through an **evidence cross-referencing architecture**. Rather than trusting any single model, ClaimSense AI independently parses documents, detects visual vehicle damage via Computer Vision, reconstructs accident timelines via rule-based NLP, and submits all extracted entities to a **deterministic Cross-Source Verification Engine**. The system generates transparent, explainable consistency scores, highlights discrepancies, and compiles comprehensive audit reports for human claim assessors.

---

## 🚦 Project Status & Model Governance

### Current Status Matrix
| Component | Baseline / Reference | Current Status | Governance Classification |
| :--- | :--- | :--- | :--- |
| **Production Model Checkpoint** | `models/phase5/best.pt` | Active & Verified | **IMMUTABLE PRODUCTION BASELINE** |
| **Phase 9.19 Research Program** | 4-Workstream Plan | Concluded | **RESEARCH CLOSED** |
| **Phase 9.20 Research Experiments** | EXP20-01 to EXP20-06 | Evaluated on Virgin Suite | **REJECTED FOR PRODUCTION** |
| **Inference Architecture** | `damage_detector.py` | Per-Class Thresholding Added | **COMMITTED (Opt-In / Backward-Compatible)** |
| **Virgin Benchmark Suite** | 164-Image Multi-Source | Sealed & Locked | **CERTIFIED INDEPENDENT BENCHMARK** |
| **Phase 9.21 Proposed Scope** | Multi-Angle / Patch Tiling | Planned | **NOT STARTED** |

### Absolute Model Governance Invariants
1. **Production Checkpoint Invariant:** `models/phase5/best.pt` has an immutable SHA-256 hash of `90d489e46ff8521edff88d522f0feffa164ac38a53b84700594c02a69e515565`. It is never overwritten by experimental runs.
2. **No Automatic Model Promotion:** Candidate checkpoints cannot be promoted without formal 5-gate audit sign-off, independent benchmark evaluation, and regression test verification.
3. **Threshold Invariant:** Production default thresholds remain strictly fixed at scalar `conf_threshold = 0.15` and `iou_threshold = 0.45`.
4. **Data Isolation:** Experimental runs and artifacts are strictly isolated under `runs/` and never written to customer upload directories or production database stores.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    subgraph Intake["1. Evidentiary Intake & Storage"]
        CF["Claim Details & Narrative"]
        DOCS["Documents (Policy, Form, Invoice)"]
        IMG["Vehicle Accident Photographs"]
    end

    subgraph Security["Security & Access Boundaries"]
        AUTH["Werkzeug Session Auth & RBAC"]
        CSRF["Flask-WTF CSRF & Rate Limiter"]
        VAL["Magic Bytes & Size Validation"]
    end

    Intake --> Security

    subgraph Pipelines["2. Multi-Modal Analysis Pipelines"]
        direction TB
        OCR["Document Intelligence Pipeline\n(Tesseract OCR + PyMuPDF + python-docx)\n• Policy Window & Insured Name\n• Vehicle Registration\n• Invoice Line Items & Costs"]
        NLP["Accident Narrative Pipeline\n(Deterministic Rule-Based NLP)\n• Component Mentions & Impact Regions\n• Chronological Timeline Reconstruction\n• Temporal Consistency Checks"]
        CV["Computer Vision Pipeline\n(Ultralytics YOLOv8 Architecture)\n• 6 Damage Classes (Dent, Scratch, Crack, etc.)\n• Spatial Region Mapping (Front/Rear/Side)\n• Bounding Box Localization & Confidence\n• Opt-In Per-Class Threshold Filtering"]
    end

    Security --> Pipelines

    subgraph Verification["3. Deterministic Verification Engine (Phase 7)"]
        direction TB
        FC["Field Comparator\n(Damerau-Levenshtein, OCR Substitution Tolerance, ISO Dates)"]
        DC["Damage Comparator\n(Spatial/Category Clustering, Invoice Overhead Separation)"]
        SC["Scoring & Evidence Coverage Engine\n(Neutral Inconclusive Scoring, Severity Breakdown)"]
        FC --> SC
        DC --> SC
    end

    Pipelines --> Verification

    subgraph Persistence["4. Relational & Telemetry Data Stores"]
        PROD_DB[("Primary Database\nclaimsense.db\n(SQLAlchemy ORM)")]
        SHADOW_DB[("Shadow Telemetry\nshadow_telemetry.db\n(Dedicated WAL Mode)")]
    end

    Verification --> PROD_DB

    subgraph Presentation["5. Assessor Decision Support & Reporting"]
        UI["Assessor Web Dashboard\n(Responsive Vanilla HTML5 / CSS3 / ES6)"]
        PDF["Consolidated Audit PDF Report\n(ReportLab 8-Page Formatted Document)"]
    end

    PROD_DB --> UI
    PROD_DB --> PDF
```

---

## 🚗 Vehicle Damage Detection Architecture

### Supported Damage Classes
The vision pipeline supports six fine-grained automotive damage categories:
1. `dent` &mdash; Surface indentations and body panel concavities.
2. `scratch` &mdash; Linear abrasions, paint scuffs, and clear-coat scrapes.
3. `crack` &mdash; Hairline fractures, fissures, and structural splits in plastic/metal bumpers.
4. `glass shatter` &mdash; Fractured or spider-webbed windshields, windows, and light clusters.
5. `lamp broken` &mdash; Cracked, shattered, or displaced headlamps, tail lamps, and indicator housings.
6. `tire flat` &mdash; Deflated, punctured, bead-separated, or blown-out tires.

### Detection, Localization & Confidence Scoring
- **Detection Head:** Ultralytics YOLOv8 architecture performing multi-class classification and bounding box regression in a single forward pass.
- **Spatial Localization:** Predicted boxes are mapped to vehicle quadrant regions (`front_left`, `front_right`, `rear_left`, `rear_right`, `center`, `roof`) for cross-source spatial corroboration against the claimant narrative.
- **Production Default Parameters:**
  - `conf_threshold = 0.15` (Scalar confidence filter)
  - `iou_threshold = 0.45` (Non-Maximum Suppression IoU threshold)

### Backward-Compatible Per-Class Threshold Architecture
Implemented in `backend/services/vision/damage_detector.py`:
- **Scalar Path (Default):** Callers passing scalar floats or ints (e.g. `conf_threshold=0.15`) execute the exact legacy inference path with zero computational overhead and identical output.
- **Dictionary Path (Opt-In):** Callers may pass granular threshold dictionaries mapping class IDs or names:
  ```python
  thresholds = {
      "dent": 0.18,
      "scratch": 0.28,
      "crack": 0.25,
      "glass shatter": 0.22,
      "lamp broken": 0.25,
      "tire flat": 0.25,
  }
  detector.detect_damage(image, conf_threshold=thresholds)
  ```
- **Fallback & Robustness:** String normalization handles `'glass shatter'`, `'glass_shatter'`, and `'glass-shatter'`. Missing classes automatically fall back to `default_fallback = 0.15`. Invalid keys raise clear `ValueError`.
- **Production Status:** Research threshold mappings are **not production defaults**; the default argument remains scalar `0.15`.

---

## 🔬 Phase 9.19 Research Summary

Phase 9.19 focused on analyzing the limits of the previous Phase 9.12–9.18 accuracy program:
1. **Benchmark Exposure & Quarantine:** Historical evaluation revealed that `datasets/CarDD_300/test/` (45 images) had been repeatedly evaluated across multiple research sessions. It was officially declared a **consumed exploratory benchmark** and strictly quarantined to prevent data leakage.
2. **Root Cause Analysis of Hairline Cracks:** Identified the fundamental receptive field and bounding box regression constraints that cause rectangular YOLOv8 heads to generate loose proposals around ultra-thin fissures, depressing intersection-over-union scores below standard matching criteria.
3. **Phase Closure:** Confirmed that further model fine-tuning required fresh, unexposed benchmark imagery and granular per-class threshold controls before any candidate could be considered for promotion.

---

## 🔬 Phase 9.20 Research & Forensic Verification Summary

Phase 9.20 executed an end-to-end research workflow spanning benchmark governance, threshold architecture implementation, six controlled GPU experiments, and independent evaluation on a newly sealed virgin benchmark suite.

### The Six Phase 9.20 Controlled GPU Experiments

| Run ID | Model Code | Training Objective & Configuration | Epochs | Peak VRAM | Status |
| :--- | :--- | :--- | :---: | :---: | :---: |
| **EXP20-01** | `P920_EXP01_loss_rebalance` | Balanced classification loss (`cls=0.85`, `box=7.5`, 640px) | 25 | 1,928.1 MB | Converged |
| **EXP20-02** | `P920_EXP02_box_refinement` | Heightened box loss (`box=8.0`, `dfl=1.8`, `cls=0.80`, 640px) | 25 | 1,940.5 MB | Converged |
| **EXP20-03** | `P920_EXP03_hires_704` | Multi-scale high resolution (`imgsz=704`, `cls=0.85`, batch=12) | 25 | 1,880.2 MB | Converged |
| **EXP20-04** | `P920_EXP04_phase5_finetune` | Fine-tuning from Phase 5 baseline checkpoint (lr0=0.001, 640px) | 20 | 1,960.0 MB | Converged |
| **EXP20-05** | `P920_EXP05_hires_finetune` | High-resolution fine-tuning from Phase 5 (`imgsz=704`, batch=8) | 20 | 1,510.4 MB | Converged |
| **EXP20-06** | `P920_EXP06_regularized` | Mixup data regularization (`mixup=0.1`, `cls=0.90`, 640px) | 25 | 1,950.0 MB | Converged |

### Independent Benchmark Evaluation (164 Virgin Images, 122 GT Instances)
Evaluated strictly at $\text{IoU} \ge 0.50$ matching criterion:

| Model Evaluated | Mode | Precision | Recall | F1 Score | False Positives | True Positives | Latency |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **BASELINE_Phase5** | Fixed $\tau=0.25$ | 0.07% | 10.66% | 0.0015 | 17,488 | 13 | 271 ms |
| **BASELINE_Phase5** | Calibrated Per-Class | 0.07% | 10.66% | 0.0014 | 18,894 | 13 | 177 ms |
| **EXP20-01** | Fixed $\tau=0.25$ | 0.41% | 0.82% | 0.0054 | 245 | 1 | 166 ms |
| **EXP20-01** | Calibrated Per-Class | 0.38% | 0.82% | 0.0052 | 260 | 1 | 89 ms |
| **EXP20-03** | Fixed $\tau=0.25$ | 0.00% | 0.00% | 0.0000 | 374 | 0 | 193 ms |
| **EXP20-03** | Calibrated Per-Class | 0.00% | 0.00% | 0.0000 | 397 | 0 | 168 ms |

> [!WARNING]
> **Scientific Interpretation of Benchmark Findings:**
> 1. **Massive False-Positive Containment:** Candidate models successfully suppressed background hallucinations. EXP20-01 reduced false positives from 17,488 down to 245 (over $71\times$ reduction).
> 2. **Unacceptable Operational Recall:** Despite false-positive reduction, candidate recall on the out-of-distribution virgin suite remained critically low (0.82% for EXP01, 0.00% for EXP03).
> 3. **Geometric Localization Degradation:** EXP20-03 predicted bounding boxes that encompassed whole vehicle assemblies rather than tight damage contours, yielding average IoUs of $0.35 - 0.44$, which fell below the mandatory $\text{IoU} \ge 0.50$ threshold.
> 4. **Governance Verdict:** Because candidate models failed Gate 2 (Dent Recall Retention) and Gate 3 (F1 Score Improvement), **no candidate checkpoint is approved for production deployment**.

---

## 🔒 Benchmark Governance & Provenance

The Phase 9.20 Virgin Benchmark was staged to provide an uncompromised evaluation set:
* **Total Image Count:** 164 authentic vehicle images.
* **Ground Truth Instances:** 122 verified damage instances across all 6 classes.
* **Source Composition:**
  - 120 canonical images from `CarDD_DomainAdaptation_v1/processed`.
  - 44 dual-blind adjudicated images from `CarDD_Independent_Val_v1` (Batch 01 & 02).
* **Cryptographic Seal:** `67c582847713ff071c1c22952b2e88cc4f9c3165b61b33462d654be270764fad` ([benchmark_lock_manifest.json](runs/phase9_20/benchmark/benchmark_lock_manifest.json)).
* **Zero Leakage Verified:** Cryptographic SHA-256 cross-checks confirmed **0 collisions** with training sets (`CarDD_Expanded_v1/train`) and quarantined test sets (`CarDD_300/test`).
* **Consumed Status:** The 164 images now constitute a locked benchmark; future models may not be iteratively tuned against this set to prevent overfitting.

---

## 💻 GPU Experiment Environment

All Phase 9.20 GPU training and evaluation runs were executed on dedicated hardware with telemetry logged:
* **Host Operating System:** Microsoft Windows 11 Home Single Language (Build 26100, x86_64)
* **GPU Accelerator:** 1x NVIDIA GeForce RTX 3050 Laptop GPU (4.00 GB GDDR6, 60W TGP)
* **CUDA Driver / Runtime:** CUDA 12.8
* **Deep Learning Framework:** PyTorch `2.11.0+cu128`
* **Computer Vision Suite:** Ultralytics YOLOv8 `8.4.215`
* **Python Runtime:** Python `3.13.2` 64-bit

---

## 🧪 Testing Infrastructure & Verification

The repository maintains an automated test battery with test fixtures and defensive execution guards:

```powershell
# Run the complete computer vision regression suite
pytest tests/test_phase5_vision.py -v

# Run the per-class threshold unit test suite
pytest tests/test_per_class_thresholds.py -v

# Run both vision suites together
pytest tests/test_phase5_vision.py tests/test_per_class_thresholds.py -v
```

### Verified Test Outcome
* `tests/test_phase5_vision.py`: **29 passed, 1 skipped, 0 failed** (51.05s)
  - *Skipped test note:* `test_kcm0_history_and_integrity_preserved` checks for an ephemeral test claim `CLM-20261116-KCM0` from Phase 5 development; because the clean production database does not contain this transient claim, the test defensively invokes `self.skipTest()`.
* `tests/test_per_class_thresholds.py`: **11 passed, 0 skipped, 0 failed** (9.86s)
* **Combined Computer Vision Battery:** **40 passed, 1 skipped, 0 failed (100% of executed tests passing).**

---

## 🗃️ Datasets & Multi-Modal Roles

ClaimSense AI uses specialized datasets for distinct functional subsystems:
1. **CarDD (Damage Detection):** Vehicle damage bounding boxes across 6 categories (`dent`, `scratch`, `crack`, `glass shatter`, `lamp broken`, `tire flat`). Used exclusively for YOLOv8 training and evaluation.
2. **FUNSD (Form Understanding):** Academic dataset for scanned document understanding, key-value pair extraction, and layout intelligence. Used for document pipeline architecture reference.
3. **SROIE (Receipt OCR):** Academic dataset for invoice and receipt optical character recognition. Used for repair bill entity extraction evaluation.

> [!NOTE]
> Neither FUNSD nor SROIE contain vehicle damage photographs. Vehicle damage detection models are trained solely on CarDD automotive imagery.

---

## 📁 Repository Structure

```text
ClaimSense-AI/
├── backend/                               # Core backend application
│   ├── app.py                             # Flask application factory
│   ├── config.py                          # Environment configuration
│   ├── database/                          # Persistence layer
│   │   ├── models.py                      # SQLAlchemy ORM models
│   │   └── claimsense.db                  # [Local] Primary SQLite production database
│   ├── routes/                            # REST API blueprints (auth, claims, health)
│   └── services/                          # Domain services
│       ├── ocr/                           # Document intelligence & OCR
│       ├── nlp/                           # Rule-based narrative & timeline analysis
│       ├── verification/                  # Phase 7 Cross-Source Verification engine
│       └── vision/                        # Damage detection & threshold resolution
│           ├── damage_detector.py         # YOLOv8 detector with per-class threshold support
│           └── shadow_worker.py           # Hardened shadow trial worker
├── datasets/                              # Dataset roots (excluded from git)
│   └── phase9_20_benchmark/               # Locked 164-image independent virgin benchmark
│       ├── images/                        # 164 benchmark images
│       └── labels/                        # 122 ground-truth YOLO labels
├── frontend/                              # Responsive assessor web application
│   ├── index.html                         # Assessor dashboard
│   ├── app.js                             # Frontend application controller
│   └── style.css                          # Modern responsive styling
├── models/                                # Production model checkpoints
│   └── phase5/
│       └── best.pt                        # Authoritative production checkpoint (SHA-256: 90d489e46...)
├── reports/                               # Generated verification PDFs and intake receipts
├── runs/                                  # Research experiments and audit reports
│   ├── phase9_20/                         # Phase 9.20 research and forensic artifacts
│   │   ├── architecture/                  # Per-class threshold design & compatibility reports
│   │   ├── benchmark/                     # Lock manifest & provenance records
│   │   ├── checkpoints/                   # Checkpoints for EXP01–EXP06 (symlinked)
│   │   ├── evaluations/                   # Virgin benchmark & validation matrices (JSON)
│   │   ├── forensic_verification/         # 7 formal forensic audit deliverables
│   │   └── reports/                       # Master Phase 9.20 reports
│   └── ml_accuracy_program_final_report.md# Master ML accuracy program report
├── scripts/                               # Operational & evaluation CLI tools
├── tests/                                 # Automated test suite
│   ├── test_per_class_thresholds.py       # Per-class threshold architecture unit tests
│   ├── test_phase5_vision.py              # Computer vision regression suite
│   └── test_e2e.py                        # Master E2E integration test suite
├── .env.example                           # Configuration template
├── requirements.txt                       # Python dependencies
└── README.md                              # Master project documentation
```

---

## 🛠️ Installation, Setup & Execution

### System Prerequisites
* **Operating System:** Windows 10/11, Ubuntu 20.04+, or macOS.
* **Python Runtime:** Python 3.10 to Python 3.13 (Verified on Python 3.13.2).
* **Git:** Version control client.
* **GPU (Optional):** NVIDIA GPU with CUDA 11.8+ / 12.8+ for accelerated inference.

### 1. Setup & Environment
```powershell
# Clone the repository
git clone https://github.com/anshg8252/ClaimSense-AI.git
cd ClaimSense-AI

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install package dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure Environment
```powershell
Copy-Item .env.example .env
```

### 3. Launch the Application
```powershell
python backend/app.py
```
Open `http://127.0.0.1:5001/` in any modern web browser to access the assessor dashboard.

---

## 🗺️ Project Roadmap

| Phase | Milestone Name | Status | Summary |
| :---: | :--- | :---: | :--- |
| **Phase 1–6** | Foundations, DB, OCR, Vision, NLP | **Completed** | Full multi-modal claim ingestion and processing pipelines. |
| **Phase 7** | Cross-Source Verification | **Completed** | Deterministic consistency engine, 8-page PDF audit reports. |
| **Phase 8** | Dataset Preparation & Gate P | **Closed at Gate P** | Multi-tier datasets, dual-blind annotation, offline safety hardening. |
| **Phase 9.12–9.18** | ML Accuracy Program | **Completed & Closed** | Crack forensics, CarDD retraining, Gate 5 scorecard, baseline retained. |
| **Phase 9.19** | Pre-Start Readiness & Closure | **Completed & Closed** | Quarantine boundary confirmed, CarDD_300/test sealed as consumed. |
| **Phase 9.20** | Advanced Detection & Forensic Audit | **Completed & Verified** | Per-class thresholding implemented; EXP01–06 evaluated; no model promotion. |
| **Phase 9.21** | Patch Tiling & Polygon Segmentation | **Proposed / Planned** | Proposed next phase: SAHI inference tiling and polygon instance segmentation. Not started. |

---

## 📚 Key Phase 9.20 Research & Forensic Reports

All Phase 9.20 engineering and governance deliverables are maintained directly in the repository:

* **Forensic Verification Deliverables (`runs/phase9_20/forensic_verification/`):**
  * [Master Forensic Verification Report](runs/phase9_20/forensic_verification/phase9_20_forensic_verification.md) &mdash; Comprehensive forensic report across all 6 GPU runs, benchmarks, and production safety invariants.
  * [Training Completion Audit Table](runs/phase9_20/forensic_verification/training_completion_audit.csv) &mdash; Per-experiment hardware telemetry, loss convergence, epoch counts, and hashes.
  * [Benchmark Metric Reconciliation Table](runs/phase9_20/forensic_verification/benchmark_metric_reconciliation.csv) &mdash; 140-row independent metric reconciliation across validation and virgin suites.
  * [Benchmark Provenance & Zero-Leakage Audit](runs/phase9_20/forensic_verification/benchmark_provenance_verification.md) &mdash; 164-image source lineage, hash verification, and quarantine enforcement.
  * [Production Code & Asset Safety Audit](runs/phase9_20/forensic_verification/production_code_safety_audit.md) &mdash; Byte-exact verification of `best.pt`, `claimsense.db`, and `damage_detector.py` diff.
  * [Test Execution Reconciliation Report](runs/phase9_20/forensic_verification/test_execution_reconciliation.md) &mdash; Complete reconciliation of test collection and skipped test analysis.
  * [Final Model Governance Decision](runs/phase9_20/forensic_verification/final_governance_decision.md) &mdash; Formal 5-gate audit sign-off: *VERIFIED — RESEARCH COMPLETE, NO PROMOTION*.

* **Phase 9.20 Stage Reports (`runs/phase9_20/`):**
  * [Phase 9.20 Final Execution Report](runs/phase9_20/reports/phase9_20_final_report.md) &mdash; Master report summarizing Stages 1 through 4 execution.
  * [Per-Class Threshold Architecture Design](runs/phase9_20/architecture/per_class_threshold_design.md) &mdash; Software architecture and backward-compatibility specification.
  * [Dent Recall Regression Hypotheses](runs/phase9_20/reports/dent_recall_regression_hypotheses.md) &mdash; Root-cause analysis of IoU matching and domain shift dynamics.
  * [False-Positive Reduction Strategy](runs/phase9_20/reports/false_positive_reduction_strategy.md) &mdash; Background negative mining and activation barrier analysis.

---

## 📄 License & Academic Attribution

This project is developed as a **Final-Year B.Tech Major Project** within the Department of Computer Science & Engineering at **ABES Engineering College, Ghaziabad**.
* Maintained strictly for educational evaluation and research purposes.
* Third-party research datasets (CarDD, FUNSD, SROIE) remain the intellectual property of their respective academic creators and are governed by their original licenses.
