"""Integration regression suite for Phase 9.20 + Phase 11 + Phase 12 fixes.

All tests operate strictly against temporary SQLite databases, temporary upload/report
directories, and synthetic/mocked fixtures so production assets remain untouched.
"""
import io
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

from backend.app import create_app
from backend.config import Config
from backend.database.db import close_engine, get_db_session
from backend.database.models import Claim, ClaimImage, ProcessingTask, User
from backend.services.queue.manager import RedisTaskBroker, TaskManager
from backend.services.receipt import freeze_report, get_active_frozen_report
from backend.services.vision.damage_detector import VehicleDamageDetector
from scripts.backup_database import (
    backup_sqlite_database,
    resolve_default_db_path,
    restore_sqlite_database,
)
from scripts.run_worker import run_worker_loop


def _make_photo_bytes(width: int = 160, height: int = 120) -> bytes:
    """Create an authentic-looking textured RGB JPEG image (passes non-synthetic guard)."""
    import numpy as np

    rng = np.random.default_rng(42)
    arr = rng.integers(30, 225, size=(height, width, 3), dtype=np.uint8)
    buf = io.BytesIO()
    Image.fromarray(arr, mode="RGB").save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class TestPhase920AndPhase1112Integration(unittest.TestCase):
    """Combined isolated regression tests for Phase 9.20 API and Phase 11/12 fixes."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="claimsense_int_test_"))
        cls.test_db_path = cls.temp_dir / "integration_test.db"
        cls.test_uploads_dir = cls.temp_dir / "uploads"
        cls.test_reports_dir = cls.temp_dir / "reports"
        cls.test_backups_dir = cls.temp_dir / "backups"

        cls.test_uploads_dir.mkdir(parents=True, exist_ok=True)
        cls.test_reports_dir.mkdir(parents=True, exist_ok=True)
        cls.test_backups_dir.mkdir(parents=True, exist_ok=True)

        class TestConfig(Config):
            TESTING = True
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{cls.test_db_path.as_posix()}"
            DATABASE_PATH = cls.test_db_path
            UPLOAD_FOLDER = cls.test_uploads_dir
            REPORTS_FOLDER = cls.test_reports_dir
            DATA_FOLDER = cls.temp_dir
            WTF_CSRF_ENABLED = False
            RATELIMIT_ENABLED = False
            SECRET_KEY = "integration-test-secret-key-at-least-32-chars"
            ASYNC_PROCESSING_ENABLED = False
            QUEUE_BROKER_TYPE = "threaded"

        cls.test_config = TestConfig
        cls.app = create_app(TestConfig)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        close_engine()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        with get_db_session() as db:
            user = db.query(User).filter_by(username="int_assessor").first()
            if not user:
                user = User(
                    username="int_assessor",
                    email="int_assessor@claimsense.test",
                    full_name="Integration Assessor",
                    role="assessor",
                )
                user.set_password("StrongPass123!")
                db.add(user)
                db.commit()
                db.refresh(user)
            self.user_id = user.id

    def _login(self):
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.user_id
            sess["role"] = "assessor"
            sess["username"] = "int_assessor"

    def _seed_claim_with_photo(self, claim_id: str) -> Path:
        claim_img_dir = self.test_uploads_dir / claim_id / "images"
        claim_img_dir.mkdir(parents=True, exist_ok=True)
        img_file = claim_img_dir / "vehicle_image_front.jpg"
        img_file.write_bytes(_make_photo_bytes())
        rel_path = f"{claim_id}/images/vehicle_image_front.jpg"

        with get_db_session() as db:
            existing = db.query(Claim).filter_by(claim_id=claim_id).first()
            if not existing:
                claim = Claim(
                    claim_id=claim_id,
                    user_id=self.user_id,
                    claimant_name="Integration Tester",
                    policy_number="POL-INT-2026-001",
                    vehicle_number="KA-01-XY-9999",
                    accident_date="2026-11-20",
                    claim_description="Front bumper dent and minor scratch.",
                    status="SUBMITTED",
                )
                db.add(claim)
                db.flush()
                db.add(
                    ClaimImage(
                        claim_id=claim_id,
                        image_type="VEHICLE_ACCIDENT",
                        file_path=rel_path,
                        original_filename="vehicle_image_front.jpg",
                        stored_filename="vehicle_image_front.jpg",
                        file_extension="jpg",
                        file_size=img_file.stat().st_size,
                    )
                )
                db.commit()
        return img_file

    # 1. Per-class threshold HTTP validation & backward compatibility
    def test_01_per_class_threshold_api_validation_and_compatibility(self):
        """Verify scalar & per-class dict acceptance and HTTP 400 rejection on invalid inputs."""
        claim_id = "CLM-20261125-T001"
        self._seed_claim_with_photo(claim_id)
        self._login()

        # Invalid dict (unknown class) -> must return 400, NOT silently fall back to 0.15
        res_unknown = self.client.post(
            f"/api/claims/{claim_id}/analyze-damage",
            json={"conf_threshold": {"unknown_damage": 0.25}},
        )
        self.assertEqual(res_unknown.status_code, 400)
        self.assertEqual(res_unknown.get_json()["error"], "Invalid Threshold")

        # Out-of-bounds dict -> 400
        res_oob = self.client.post(
            f"/api/claims/{claim_id}/analyze-damage",
            json={"conf_threshold": {"dent": 1.5}},
        )
        self.assertEqual(res_oob.status_code, 400)

        # Boolean value -> 400
        res_bool = self.client.post(
            f"/api/claims/{claim_id}/analyze-damage",
            json={"conf_threshold": True},
        )
        self.assertEqual(res_bool.status_code, 400)

        # Invalid query parameter -> 400
        res_bad_query = self.client.post(
            f"/api/claims/{claim_id}/analyze-damage?conf=not_a_number",
            json={},
        )
        self.assertEqual(res_bad_query.status_code, 400)

        # Valid per-class dict -> passed directly to process_claim_damage_detection
        mocked_result = {
            "success": True,
            "status": "completed",
            "analysis_status": "completed",
            "total_detections": 1,
            "damage_categories": ["dent"],
            "processing_time_ms": 12.5,
        }
        with patch(
            "backend.routes.claims.process_claim_damage_detection",
            return_value=mocked_result,
        ) as mock_proc:
            res_dict = self.client.post(
                f"/api/claims/{claim_id}/analyze-damage",
                json={"conf_threshold": {"dent": 0.18, "scratch": 0.28}, "force": True},
            )
            self.assertEqual(res_dict.status_code, 200)
            self.assertEqual(
                mock_proc.call_args.kwargs["conf_threshold"],
                {"dent": 0.18, "scratch": 0.28},
            )

        # Valid scalar threshold -> preserved
        with patch(
            "backend.routes.claims.process_claim_damage_detection",
            return_value=mocked_result,
        ) as mock_proc:
            res_scalar = self.client.post(
                f"/api/claims/{claim_id}/analyze-damage",
                json={"conf_threshold": 0.25, "force": True},
            )
            self.assertEqual(res_scalar.status_code, 200)
            self.assertEqual(mock_proc.call_args.kwargs["conf_threshold"], 0.25)

    # 2. Phase 5 default thresholds and checkpoint invariance
    def test_02_phase5_defaults_preserved(self):
        """Verify Phase 9.20 keeps 0.15 confidence, 0.45 IoU, and does not persist overrides."""
        import inspect

        detector = VehicleDamageDetector.get_production_singleton()
        sig = inspect.signature(detector.detect_damage)
        self.assertEqual(sig.parameters["conf_threshold"].default, 0.15)
        self.assertEqual(sig.parameters["iou_threshold"].default, 0.45)

        # Calling with a per-class dict must not mutate future default scalar calls
        _, eff_dict, _ = detector._resolve_conf_thresholds({"dent": 0.42})
        self.assertEqual(eff_dict[0], 0.42)
        base_def, eff_def, is_per_class = detector._resolve_conf_thresholds(0.15)
        self.assertEqual(base_def, 0.15)
        self.assertFalse(is_per_class)
        self.assertTrue(all(v == 0.15 for v in eff_def.values()))

    # 3. Frozen PDF evidence image embedding & separate upload_root / reports_root
    def test_03_freeze_report_embeds_evidence_from_upload_folder_and_saves_to_reports_folder(self):
        """Verify freeze_report and /freeze-report read uploads from UPLOAD_FOLDER and write PDFs to REPORTS_FOLDER."""
        claim_id = "CLM-20261125-T003"
        img_file = self._seed_claim_with_photo(claim_id)
        before_bytes = img_file.read_bytes()
        self._login()

        with patch(
            "backend.services.receipt.generate_document_intelligence_report_pdf",
            wraps=__import__(
                "backend.services.receipt", fromlist=["generate_document_intelligence_report_pdf"]
            ).generate_document_intelligence_report_pdf,
        ) as spy_pdf:
            res = self.client.post(f"/api/claims/{claim_id}/freeze-report")
            self.assertEqual(res.status_code, 201)
            body = res.get_json()
            self.assertTrue(body["success"])
            report_path = Path(body["report"]["report_path"])

            # Saved strictly inside REPORTS_FOLDER, NOT UPLOAD_FOLDER
            self.assertTrue(report_path.exists())
            self.assertEqual(report_path.parent.parent.resolve(), self.test_reports_dir.resolve())

            # generate_document_intelligence_report_pdf received UPLOAD_FOLDER (not REPORTS_FOLDER!)
            called_upload_root = Path(spy_pdf.call_args.kwargs["upload_root"]).resolve()
            self.assertEqual(called_upload_root, self.test_uploads_dir.resolve())

        # Customer upload remains completely unmodified
        self.assertEqual(img_file.read_bytes(), before_bytes)
        active = get_active_frozen_report(claim_id)
        self.assertIsNotNone(active)
        self.assertGreater(active["file_size_bytes"], 1000)

    # 4. Redis broker dispatch & explicit fallback logging
    def test_04_redis_broker_dispatch_and_explicit_fallback_logging(self):
        """Verify RedisTaskBroker enqueue/health with mocked redis and explicit warning on fallback."""
        fake_client = MagicMock()
        fake_client.ping.return_value = True
        fake_redis_mod = types.SimpleNamespace(
            Redis=types.SimpleNamespace(from_url=MagicMock(return_value=fake_client))
        )

        with patch.dict(sys.modules, {"redis": fake_redis_mod}):
            broker = RedisTaskBroker("redis://localhost:6379/0")
            self.assertTrue(broker.is_healthy())
            self.assertTrue(broker.enqueue("task-redis-01", "CLM-20261125-T004"))
            fake_client.rpush.assert_called_once()
            key, payload = fake_client.rpush.call_args.args
            self.assertEqual(key, RedisTaskBroker.QUEUE_KEY)
            self.assertEqual(json.loads(payload)["task_id"], "task-redis-01")

        # Missing redis package -> explicit warning + clean fallback to threaded
        tm = TaskManager()
        orig_redis = tm.redis_broker
        try:
            with patch.dict(sys.modules, {"redis": None}):
                with self.assertLogs("claimsense.queue", level="WARNING") as cm:
                    broken_broker = RedisTaskBroker("redis://localhost:6379/0")
                    self.assertFalse(broken_broker.is_healthy())
                    tm.redis_broker = broken_broker
                    with patch.object(Config, "QUEUE_BROKER_TYPE", "redis"):
                        active = tm.get_active_broker_name()
            self.assertEqual(active, "threaded")
            self.assertTrue(any("falling back" in msg.lower() for msg in cm.output))
        finally:
            tm.redis_broker = orig_redis

    # 5. Stale task recovery across both Redis and Threaded brokers + worker log status
    def test_05_stale_recovery_dispatches_to_active_broker_and_worker_logs_status(self):
        """Verify recover_stale_tasks routes to Redis when active, threaded otherwise, and worker logs status."""
        claim_id = "CLM-20261125-T005"
        self._seed_claim_with_photo(claim_id)

        stale_time = datetime.now(timezone.utc) - timedelta(seconds=600)
        with get_db_session() as db:
            db.add(
                ProcessingTask(
                    task_id="task-stale-redis-1",
                    claim_id=claim_id,
                    user_id=self.user_id,
                    task_type="CLAIM_PIPELINE",
                    status="PROCESSING",
                    current_stage="DAMAGE_ANALYSIS",
                    progress_percent=55,
                    retry_count=0,
                    max_retries=3,
                    created_at=stale_time,
                    updated_at=stale_time,
                )
            )
            db.commit()

        tm = TaskManager()
        mock_redis_broker = MagicMock()
        mock_redis_broker.is_healthy.return_value = True
        mock_redis_broker.enqueue.return_value = True

        orig_redis = tm.redis_broker
        try:
            tm.redis_broker = mock_redis_broker
            with patch.object(Config, "QUEUE_BROKER_TYPE", "redis"), \
                 patch.object(tm.threaded_broker, "enqueue") as mock_threaded_enqueue:
                recovered = tm.recover_stale_tasks(timeout_seconds=10)
            self.assertGreaterEqual(recovered, 1)
            mock_redis_broker.enqueue.assert_called_once_with(
                task_id="task-stale-redis-1", claim_id=claim_id
            )
            mock_threaded_enqueue.assert_not_called()
        finally:
            tm.redis_broker = orig_redis

        # Verify worker status log is COMPLETED/FAILED (never None)
        with patch.object(Config, "UPLOAD_FOLDER", self.test_uploads_dir), \
             patch.object(Config, "REPORTS_FOLDER", self.test_reports_dir), \
             patch("scripts.run_worker.execute_claim_processing_pipeline", return_value={"success": True, "summary": {}}):
            with self.assertLogs("claimsense.worker", level="INFO") as w_logs:
                run_worker_loop(
                    broker_type="threaded",
                    poll_interval=0.05,
                    single_run=True,
                    db_uri=self.test_config.SQLALCHEMY_DATABASE_URI,
                )
            self.assertTrue(any("completed with status: COMPLETED" in m for m in w_logs.output))
            self.assertFalse(any("status: None" in m for m in w_logs.output))

    # 6. Secret management in docker-compose.yml and worker/app production startup
    def test_06_secret_enforcement_in_compose_and_worker(self):
        """Verify docker-compose.yml has no hardcoded SECRET_KEY fallback and worker fails without SECRET_KEY."""
        repo_root = Path(__file__).resolve().parent.parent
        compose_text = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertNotIn("claimsense_prod_secret_token", compose_text)
        self.assertGreaterEqual(compose_text.count("SECRET_KEY=${SECRET_KEY:?"), 2)

        # Subprocess worker startup in production without SECRET_KEY must fail cleanly
        env = os.environ.copy()
        env["FLASK_ENV"] = "production"
        env["SECRET_KEY"] = ""
        proc = subprocess.run(
            [sys.executable, "-c", "import scripts.run_worker"],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("CRITICAL SECURITY CONFIGURATION ERROR", proc.stderr)

    # 7. Database backup & restore safety (refusing 0-byte DBs + temp DB round-trip)
    def test_07_backup_refuses_zero_byte_db_and_restores_temp_db(self):
        """Verify backup utility refuses 0-byte DBs, respects DATABASE_PATH, and restores cleanly."""
        empty_db = self.temp_dir / "empty.db"
        empty_db.write_bytes(b"")
        ok_empty, _, _ = backup_sqlite_database(empty_db, self.test_backups_dir)
        self.assertFalse(ok_empty)

        with patch.dict(os.environ, {"DATABASE_PATH": str(self.test_db_path)}):
            self.assertIn("integration_test.db", resolve_default_db_path())

        ok_real, backup_path, bhash = backup_sqlite_database(self.test_db_path, self.test_backups_dir)
        self.assertTrue(ok_real)
        self.assertIsNotNone(backup_path)
        self.assertEqual(len(bhash), 64)

        restored_db = self.temp_dir / "restored.db"
        self.assertTrue(restore_sqlite_database(backup_path, restored_db))
        conn = sqlite3.connect(str(restored_db))
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        conn.close()
        self.assertGreaterEqual(count, 1)

    # 8. Test startup never touches production database path
    def test_08_test_isolation_does_not_touch_production_database(self):
        """Verify isolated wsgi/worker startup uses temp DB and leaves repo data/claimsense.db untouched."""
        repo_root = Path(__file__).resolve().parent.parent
        data_db = repo_root / "data" / "claimsense.db"
        prod_db = repo_root / "backend" / "database" / "claimsense.db"
        before_data = data_db.stat().st_size if data_db.exists() else None
        before_prod = prod_db.stat().st_size if prod_db.exists() else None

        iso_dir = self.temp_dir / "iso_check"
        iso_dir.mkdir(parents=True, exist_ok=True)
        iso_db = iso_dir / "iso.db"
        env = os.environ.copy()
        env["DATABASE_PATH"] = str(iso_db)
        env["DATABASE_URL"] = f"sqlite:///{iso_db.as_posix()}"
        env["UPLOAD_FOLDER"] = str(iso_dir / "uploads")
        env["REPORTS_FOLDER"] = str(iso_dir / "reports")
        env["FLASK_ENV"] = "development"
        env["FLASK_DEBUG"] = "True"

        proc = subprocess.run(
            [sys.executable, "-c", "import wsgi; from scripts.run_worker import run_worker_loop; run_worker_loop(single_run=True)"],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(iso_db.exists())

        after_data = data_db.stat().st_size if data_db.exists() else None
        after_prod = prod_db.stat().st_size if prod_db.exists() else None
        self.assertEqual(before_data, after_data)
        self.assertEqual(before_prod, after_prod)


if __name__ == "__main__":
    unittest.main()
