"""ClaimSense AI — Phase 12 Asynchronous Processing & Queue Architecture Test Suite.

Verifies:
- ProcessingTask ORM schema, status enums, stage progression, serialization
- TaskManager idempotency (duplicate prevention) and dual-broker dispatching
- Asynchronous claim submission (HTTP 202 Accepted with task payload)
- Backward-compatible synchronous fallback (HTTP 201 Created with ?sync=true)
- Task status endpoint (/api/claims/<claim_id>/status) and stage tracking
- Multi-user tenant and role access isolation on task endpoints
- Manual retry task endpoint (/api/claims/<claim_id>/retry-task)
- Stale task auto-recovery and timeout handling
- Readiness probe integration (task_queue check)
- Operational metrics telemetry (queue depth and task status counts)
"""
import io
import json
import logging
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

from flask import Flask

from backend.app import create_app
from backend.config import Config
from backend.database.db import get_engine, init_database, close_engine, get_db_session
from backend.database.models import Base, User, Claim, Document, ClaimImage, ProcessingTask
from backend.services.queue.manager import TaskManager, queue_manager
from backend.services.tasks.claim_tasks import execute_claim_processing_pipeline, update_task_stage


class TestPhase12AsyncProcessing(unittest.TestCase):
    """Test suite for Phase 12 asynchronous processing and task queue subsystems."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="claimsense_phase12_test_"))
        cls.test_db_path = cls.temp_dir / "test_phase12.db"
        cls.test_uploads_dir = cls.temp_dir / "uploads"
        cls.test_reports_dir = cls.temp_dir / "reports"
        cls.test_backups_dir = cls.temp_dir / "backups"

        cls.test_uploads_dir.mkdir(parents=True, exist_ok=True)
        cls.test_reports_dir.mkdir(parents=True, exist_ok=True)
        cls.test_backups_dir.mkdir(parents=True, exist_ok=True)

        class TestConfig(Config):
            TESTING = True
            SQLALCHEMY_DATABASE_URI = f"sqlite:///{cls.test_db_path.as_posix()}"
            UPLOAD_FOLDER = cls.test_uploads_dir
            REPORTS_FOLDER = cls.test_reports_dir
            DATA_FOLDER = cls.temp_dir
            WTF_CSRF_ENABLED = False
            RATELIMIT_ENABLED = False
            SECRET_KEY = "phase12-test-cryptographically-secure-key-32chars"
            ASYNC_PROCESSING_ENABLED = True
            QUEUE_BROKER_TYPE = "threaded"
            TASK_MAX_RETRIES = 3
            TASK_TIMEOUT_SECONDS = 5

        cls.test_config = TestConfig
        cls.app = create_app(TestConfig)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        close_engine()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        """Seed test users and clean state before each test."""
        with get_db_session() as db:
            # User 1: Primary Claimant
            self.user1 = db.query(User).filter_by(username="claimant_one").first()
            if not self.user1:
                self.user1 = User(
                    username="claimant_one",
                    email="user1@claimsense.test",
                    full_name="Claimant One",
                    role="claimant",
                )
                self.user1.set_password("Password123!")
                db.add(self.user1)

            # User 2: Second Claimant (Tenant Isolation)
            self.user2 = db.query(User).filter_by(username="claimant_two").first()
            if not self.user2:
                self.user2 = User(
                    username="claimant_two",
                    email="user2@claimsense.test",
                    full_name="Claimant Two",
                    role="claimant",
                )
                self.user2.set_password("Password123!")
                db.add(self.user2)

            db.commit()
            db.refresh(self.user1)
            db.refresh(self.user2)
            self.user1_id = self.user1.id
            self.user2_id = self.user2.id

    def _login_as(self, user_id: int, role: str = "claimant"):
        with self.client.session_transaction() as sess:
            sess["user_id"] = user_id
            sess["role"] = role
            sess["username"] = f"user_{user_id}"

    def _create_dummy_claim(self, claim_id: str, user_id: int) -> Claim:
        with get_db_session() as db:
            claim = db.query(Claim).filter_by(claim_id=claim_id).first()
            if not claim:
                claim = Claim(
                    claim_id=claim_id,
                    user_id=user_id,
                    claimant_name="Test Claimant",
                    policy_number="POL-2026-8801",
                    vehicle_number="KA-05-MN-9988",
                    accident_date="2026-11-20",
                    claim_description="Collision with rear barrier resulting in bumper distortion.",
                    status="SUBMITTED",
                )
                db.add(claim)
                db.commit()
                db.refresh(claim)
            return claim

    # 1. ProcessingTask ORM CRUD and Serialization Test
    def test_01_processing_task_orm_lifecycle(self):
        """Verify ProcessingTask creation, stage transitions, and serialization."""
        claim_id = "CLM-20261121-T01A"
        self._create_dummy_claim(claim_id, self.user1_id)

        task_id = "task-test-01a"
        with get_db_session() as db:
            task = ProcessingTask(
                task_id=task_id,
                claim_id=claim_id,
                user_id=self.user1_id,
                task_type="CLAIM_PIPELINE",
                status="QUEUED",
                current_stage="INTAKE",
                progress_percent=10,
            )
            db.add(task)
            db.commit()

        # Update stage
        update_task_stage(
            task_id=task_id,
            status="PROCESSING",
            stage="OCR_PROCESSING",
            progress_percent=25,
            worker_id="worker-unit-test",
        )

        with get_db_session() as db:
            refreshed = db.query(ProcessingTask).filter_by(task_id=task_id).first()
            self.assertIsNotNone(refreshed)
            self.assertEqual(refreshed.status, "PROCESSING")
            self.assertEqual(refreshed.current_stage, "OCR_PROCESSING")
            self.assertEqual(refreshed.progress_percent, 25)
            self.assertEqual(refreshed.worker_id, "worker-unit-test")
            self.assertIsNotNone(refreshed.started_at)

            # Dictionary serialization check
            d = refreshed.to_dict()
            self.assertEqual(d["task_id"], task_id)
            self.assertEqual(d["claim_id"], claim_id)
            self.assertEqual(d["status"], "processing")
            self.assertEqual(d["current_stage"], "OCR_PROCESSING")

    # 2. Idempotency Check: Duplicate Task Prevention
    def test_02_task_manager_idempotency_prevents_duplicate_active_tasks(self):
        """Verify TaskManager does not create redundant tasks for a claim already queued/processing."""
        claim_id = "CLM-20261121-T02A"
        self._create_dummy_claim(claim_id, self.user1_id)

        task1, is_new1 = queue_manager.enqueue_claim_task(claim_id, user_id=self.user1_id, sync=False)
        self.assertTrue(is_new1)
        self.assertIsNotNone(task1)

        # Immediate secondary enqueue attempt
        task2, is_new2 = queue_manager.enqueue_claim_task(claim_id, user_id=self.user1_id, sync=False)
        self.assertFalse(is_new2)
        self.assertEqual(task1.task_id, task2.task_id)

    # 3. Asynchronous Claim Submission (HTTP 202 Accepted)
    def test_03_async_claim_submission_returns_202_accepted(self):
        """Verify multipart claim submission with async enabled returns HTTP 202 with task info."""
        self._login_as(self.user1_id)

        # Prepare dummy files
        data = {
            "claimant_name": "Async Applicant",
            "policy_number": "POL-2026-9911",
            "vehicle_number": "MH-02-XY-9000",
            "accident_date": "2026-11-20",
            "incident_location": "Expressway KM 42",
            "claim_description": "Vehicle damaged on highway during sudden braking.",
            "policy_document": (io.BytesIO(b"%PDF-1.4 Mock Policy"), "policy.pdf"),
            "claim_form": (io.BytesIO(b"%PDF-1.4 Mock Claim Form"), "claim.pdf"),
            "invoice_document": (io.BytesIO(b"%PDF-1.4 Mock Invoice"), "invoice.pdf"),
            "vehicle_image": (io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF Mock JPEG"), "damage.jpg"),
        }

        with patch.object(queue_manager, "enqueue_claim_task") as mock_enqueue:
            # Mock return from enqueue
            mock_task = MagicMock()
            mock_task.task_id = "task-mock-9988"
            mock_task.status = "QUEUED"
            mock_enqueue.return_value = (mock_task, True)

            response = self.client.post(
                "/api/claims",
                data=data,
                content_type="multipart/form-data",
            )

            self.assertEqual(response.status_code, 202)
            res_json = response.get_json()
            self.assertTrue(res_json["success"])
            self.assertEqual(res_json["task_id"], "task-mock-9988")
            self.assertEqual(res_json["status"], "queued")
            self.assertIn("status_url", res_json)
            self.assertIn("/api/claims/", res_json["status_url"])

    # 4. Synchronous Claim Submission Fallback (HTTP 201 Created with ?sync=true)
    def test_04_sync_claim_submission_fallback_returns_201_created(self):
        """Verify submitting claim with ?sync=true runs synchronous pipeline and returns HTTP 201."""
        self._login_as(self.user1_id)

        data = {
            "claimant_name": "Sync Applicant",
            "policy_number": "POL-2026-9922",
            "vehicle_number": "KA-01-EE-1122",
            "accident_date": "2026-11-20",
            "claim_description": "Synchronous test incident description for backward compatibility.",
            "policy_document": (io.BytesIO(b"%PDF-1.4 Mock Policy"), "policy.pdf"),
            "claim_form": (io.BytesIO(b"%PDF-1.4 Mock Claim Form"), "claim.pdf"),
            "invoice_document": (io.BytesIO(b"%PDF-1.4 Mock Invoice"), "invoice.pdf"),
            "vehicle_image": (io.BytesIO(b"\xff\xd8\xff\xe0\x00\x10JFIF Mock JPEG"), "damage.jpg"),
        }

        with patch("backend.routes.claims.process_document") as mock_doc, \
             patch("backend.routes.claims.ingest_extracted_claim_data"), \
             patch("backend.routes.claims.process_claim_damage_detection") as mock_det:

            mock_doc.return_value = {"document_type": "POLICY_DOCUMENT", "fields": {}}
            mock_det.return_value = {"analysis_status": "completed", "total_detections": 1}

            response = self.client.post(
                "/api/claims?sync=true",
                data=data,
                content_type="multipart/form-data",
            )

            self.assertEqual(response.status_code, 201)
            res_json = response.get_json()
            self.assertTrue(res_json["success"])
            self.assertIn("claim_id", res_json)
            self.assertIn("damage_analysis", res_json)

    # 5. Task Status Polling Endpoint Test
    def test_05_task_status_endpoint_returns_stage_progression(self):
        """Verify GET /api/claims/<claim_id>/status returns accurate task metadata."""
        claim_id = "CLM-20261121-T05A"
        self._create_dummy_claim(claim_id, self.user1_id)

        with get_db_session() as db:
            task = ProcessingTask(
                task_id="task-test-05a",
                claim_id=claim_id,
                user_id=self.user1_id,
                task_type="CLAIM_PIPELINE",
                status="PROCESSING",
                current_stage="DAMAGE_ANALYSIS",
                progress_percent=55,
                worker_id="thread-worker-01",
            )
            db.add(task)
            db.commit()

        self._login_as(self.user1_id)
        res = self.client.get(f"/api/claims/{claim_id}/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["task_id"], "task-test-05a")
        self.assertEqual(data["status"], "processing")
        self.assertEqual(data["stage"], "DAMAGE_ANALYSIS")
        self.assertEqual(data["progress_percent"], 55)

    # 6. Access Control & Tenant Isolation on Task Status
    def test_06_task_status_unauthorized_isolation(self):
        """Verify Claimant Two cannot poll task status for Claimant One's claim."""
        claim_id = "CLM-20261121-T06A"
        self._create_dummy_claim(claim_id, self.user1_id)

        with get_db_session() as db:
            task = ProcessingTask(
                task_id="task-test-06a",
                claim_id=claim_id,
                user_id=self.user1_id,
                task_type="CLAIM_PIPELINE",
                status="PROCESSING",
                current_stage="INTAKE",
                progress_percent=10,
            )
            db.add(task)
            db.commit()

        # Login as User 2 (different claimant)
        self._login_as(self.user2_id, role="claimant")
        res = self.client.get(f"/api/claims/{claim_id}/status")
        self.assertEqual(res.status_code, 403)

        # Unauthenticated query
        with self.client.session_transaction() as sess:
            sess.clear()
        res_anon = self.client.get(f"/api/claims/{claim_id}/status")
        self.assertEqual(res_anon.status_code, 401)

    # 7. Retry Task Endpoint Test
    def test_07_retry_claim_task_endpoint(self):
        """Verify POST /api/claims/<claim_id>/retry-task re-enqueues processing task."""
        claim_id = "CLM-20261121-T07A"
        self._create_dummy_claim(claim_id, self.user1_id)

        # Seed failed task
        with get_db_session() as db:
            task = ProcessingTask(
                task_id="task-test-07-failed",
                claim_id=claim_id,
                user_id=self.user1_id,
                task_type="CLAIM_PIPELINE",
                status="FAILED",
                current_stage="DAMAGE_ANALYSIS",
                progress_percent=55,
                error_message="Simulated GPU OOM error",
            )
            db.add(task)
            db.commit()

        self._login_as(self.user1_id)
        res = self.client.post(f"/api/claims/{claim_id}/retry-task")
        self.assertEqual(res.status_code, 202)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "queued")
        self.assertIn("re-enqueued", data["message"])

    # 8. Readiness Probe Task Queue Health Check
    def test_08_health_ready_probe_verifies_task_queue(self):
        """Verify /api/health/ready verifies task_queue availability."""
        res = self.client.get("/api/health/ready")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["ready"])
        self.assertIn("task_queue", data["checks"])
        self.assertTrue(data["checks"]["task_queue"])
        self.assertIn("task_broker", data["details"])

    # 9. Health Metrics Telemetry Includes Task Queue Counters
    def test_09_health_metrics_telemetry_includes_queue_telemetry(self):
        """Verify /api/health/metrics provides task queue depth and status counts."""
        res = self.client.get("/api/health/metrics")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("queue", data)
        q = data["queue"]
        self.assertIn("active_broker", q)
        self.assertIn("broker_healthy", q)
        self.assertIn("queue_depth", q)
        self.assertIn("task_counts", q)
        self.assertIn("queued", q["task_counts"])
        self.assertIn("processing", q["task_counts"])
        self.assertIn("completed", q["task_counts"])

    # 10. Stale Task Detection and Recovery
    def test_10_stale_task_recovery_mechanism(self):
        """Verify recover_stale_tasks recovers or fails stuck tasks past timeout."""
        claim_id = "CLM-20261121-T10A"
        self._create_dummy_claim(claim_id, self.user1_id)

        stale_time = datetime.now(timezone.utc) - timedelta(seconds=600)
        task_id = "task-test-stale-01"

        with get_db_session() as db:
            stale_task = ProcessingTask(
                task_id=task_id,
                claim_id=claim_id,
                user_id=self.user1_id,
                task_type="CLAIM_PIPELINE",
                status="PROCESSING",
                current_stage="OCR_PROCESSING",
                progress_percent=25,
                retry_count=0,
                max_retries=2,
                created_at=stale_time,
                updated_at=stale_time,
            )
            db.add(stale_task)
            db.commit()

        # Run recovery with 10-second timeout threshold
        recovered = queue_manager.recover_stale_tasks(timeout_seconds=10)
        self.assertGreaterEqual(recovered, 1)

        with get_db_session() as db:
            recovered_task = db.query(ProcessingTask).filter_by(task_id=task_id).first()
            self.assertEqual(recovered_task.retry_count, 1)
            self.assertEqual(recovered_task.status, "QUEUED")
            self.assertIn("auto-recovered", recovered_task.error_message)

    # 11. Worker CLI Single-Run Execution
    def test_11_worker_cli_single_run(self):
        """Verify run_worker.py executes cleanly in single-run mode against isolated DB."""
        from scripts.run_worker import run_worker_loop

        with patch.object(Config, "UPLOAD_FOLDER", self.test_uploads_dir), \
             patch.object(Config, "REPORTS_FOLDER", self.test_reports_dir):
            run_worker_loop(
                broker_type="threaded",
                poll_interval=0.1,
                single_run=True,
                db_uri=self.test_config.SQLALCHEMY_DATABASE_URI,
            )


if __name__ == "__main__":
    unittest.main()
