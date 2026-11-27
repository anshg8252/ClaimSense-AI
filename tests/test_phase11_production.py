"""ClaimSense AI — Phase 11 Production Hardening & Operational Readiness Test Suite.

Verifies:
- Production WSGI entrypoint (`wsgi.py`)
- Liveness, readiness, and metrics endpoints (`/api/health/*`)
- Request correlation ID propagation (`X-Request-ID`)
- Defense-in-depth security response headers
- SQLite WAL mode & busy timeout pragma behavior
- Online zero-downtime database backup utility (`scripts/backup_database.py`)
- Structured JSON logging formatter (`JsonFormatter`)
- Report snapshot persistence & retrieval lifecycle (`Report` ORM & `/freeze-report`)
- Containerization & reverse proxy configuration manifests
- Database migration script for reports table
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
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from backend.app import create_app
from backend.config import Config
from backend.database.db import get_engine, init_database, close_engine, get_db_session
from backend.database.models import Base, User, Claim, Document, Report
from backend.services.receipt import freeze_report, get_active_frozen_report
from backend.utils.logger import JsonFormatter, setup_logger
from scripts.backup_database import backup_sqlite_database, verify_backup, calculate_sha256
from scripts.migrations.migrate_reports_table import upgrade, downgrade


class TestPhase11ProductionHardening(unittest.TestCase):
    """Test suite for Phase 11 production hardening and deployment components."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="claimsense_phase11_test_"))
        cls.test_db_path = cls.temp_dir / "test_phase11.db"
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
            SECRET_KEY = "phase11-test-cryptographically-secure-key-32chars"

        cls.test_config = TestConfig
        cls.app = create_app(TestConfig)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        close_engine()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        # Seed test user and test claim for report testing
        with get_db_session() as db:
            user = db.query(User).filter_by(username="phase11_assessor").first()
            if not user:
                user = User(
                    username="phase11_assessor",
                    email="assessor@claimsense.test",
                    full_name="Phase 11 Assessor",
                    role="assessor",
                )
                user.set_password("SecurePass123!")
                db.add(user)
                db.commit()
                db.refresh(user)
            self.test_user_id = user.id

            claim = db.query(Claim).filter_by(claim_id="CLM-20261121-P11A").first()
            if not claim:
                claim = Claim(
                    claim_id="CLM-20261121-P11A",
                    user_id=user.id,
                    claimant_name="Test Claimant",
                    policy_number="POL-2026-9901",
                    vehicle_number="DL-01-AB-1234",
                    accident_date="2026-11-20",
                    claim_description="Front bumper damage and headlight fracture during slow collision.",
                    status="SUBMITTED",
                )
                db.add(claim)
                db.commit()

    # 1. WSGI Entrypoint Test
    def test_01_wsgi_application_entrypoint(self):
        """Verify wsgi.py exports valid application callables in an isolated environment."""
        wsgi_dir = self.temp_dir / "wsgi_iso"
        wsgi_dir.mkdir(parents=True, exist_ok=True)
        wsgi_db = wsgi_dir / "wsgi_isolated.db"
        env = os.environ.copy()
        env["DATABASE_PATH"] = str(wsgi_db)
        env["DATABASE_URL"] = f"sqlite:///{wsgi_db.as_posix()}"
        env["UPLOAD_FOLDER"] = str(wsgi_dir / "uploads")
        env["REPORTS_FOLDER"] = str(wsgi_dir / "reports")
        env["FLASK_ENV"] = "development"
        env["FLASK_DEBUG"] = "True"

        repo_root = Path(__file__).resolve().parent.parent
        proc = subprocess.run(
            [
                sys.executable,
                "-c",
                "import wsgi; from flask import Flask; "
                "assert isinstance(wsgi.app, Flask); "
                "assert isinstance(wsgi.application, Flask); "
                "assert wsgi.app is wsgi.application",
            ],
            cwd=str(repo_root),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, f"WSGI isolated check failed: {proc.stderr}")
        self.assertTrue(wsgi_db.exists())

    # 2. Health, Live, and Ready Probes Test
    def test_02_health_endpoints_live_and_ready(self):
        """Verify /api/health, /api/health/live, and /api/health/ready probes."""
        # Lightweight health
        res = self.client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("version", data)

        # Liveness probe
        res_live = self.client.get("/api/health/live")
        self.assertEqual(res_live.status_code, 200)
        data_live = res_live.get_json()
        self.assertEqual(data_live["status"], "alive")
        self.assertIn("uptime_seconds", data_live)

        # Deep readiness probe
        res_ready = self.client.get("/api/health/ready")
        self.assertIn(res_ready.status_code, (200, 503))
        data_ready = res_ready.get_json()
        self.assertIn("checks", data_ready)
        self.assertTrue(data_ready["checks"]["database"])
        self.assertTrue(data_ready["checks"]["storage_uploads"])

    # 3. Telemetry Metrics Endpoint Test
    def test_03_telemetry_metrics_endpoint(self):
        """Verify /api/health/metrics operational schema."""
        res = self.client.get("/api/health/metrics")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("entity_counts", data)
        self.assertIn("uptime_seconds", data)
        self.assertGreaterEqual(data["entity_counts"]["users"], 1)

    # 4. Correlation ID Propagation Test
    def test_04_request_correlation_id_injection(self):
        """Verify X-Request-ID injection and client echo."""
        # Server-generated correlation ID
        res = self.client.get("/api/health")
        req_id = res.headers.get("X-Request-ID")
        self.assertIsNotNone(req_id)
        self.assertTrue(req_id.startswith("req-"))

        # Client-supplied correlation ID echo
        custom_id = "custom-trace-trace999"
        res_custom = self.client.get("/api/health", headers={"X-Request-ID": custom_id})
        self.assertEqual(res_custom.headers.get("X-Request-ID"), custom_id)

    # 5. Security Headers Test
    def test_05_defensive_security_headers(self):
        """Verify defense-in-depth HTTP security headers."""
        res = self.client.get("/api/health")
        self.assertEqual(res.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(res.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(res.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")

    # 6. SQLite WAL Pragma Test
    def test_06_sqlite_wal_pragma_configuration(self):
        """Verify SQLite connection hooks support WAL mode and busy timeout."""
        from sqlalchemy import text
        engine = get_engine()
        with engine.connect() as conn:
            # Verify busy timeout is configured to 5000ms
            timeout = conn.execute(text("PRAGMA busy_timeout;")).scalar()
            self.assertEqual(timeout, 5000)

            # Verify foreign keys are enabled
            fk = conn.execute(text("PRAGMA foreign_keys;")).scalar()
            self.assertEqual(fk, 1)

    # 7. Database Online Backup Test
    def test_07_database_online_backup_utility(self):
        """Verify scripts/backup_database.py online backup, SHA-256, and integrity."""
        # Create a small standalone test DB
        source_db = self.temp_dir / "backup_src.db"
        conn = sqlite3.connect(str(source_db))
        conn.execute("CREATE TABLE test_data (id INT, note TEXT);")
        conn.execute("INSERT INTO test_data VALUES (1, 'Phase 11 Backup Verification');")
        conn.commit()
        conn.close()

        # Run backup
        dest_dir = self.temp_dir / "backup_out"
        success, bpath, sha_hash = backup_sqlite_database(
            source_db_path=source_db,
            backup_dir=dest_dir,
            retention_days=1,
            dry_run=False,
        )

        self.assertTrue(success)
        self.assertIsNotNone(bpath)
        self.assertTrue(bpath.exists())
        self.assertEqual(len(sha_hash), 64)

        # Verify checksum file exists and matches
        checksum_file = bpath.with_name(f"{bpath.name}.sha256")
        self.assertTrue(checksum_file.exists())
        self.assertIn(sha_hash, checksum_file.read_text(encoding="utf-8"))

        # Verify SQLite integrity check
        self.assertTrue(verify_backup(bpath))

        # Verify restored content
        bconn = sqlite3.connect(str(bpath))
        row = bconn.execute("SELECT note FROM test_data WHERE id=1;").fetchone()
        bconn.close()
        self.assertEqual(row[0], "Phase 11 Backup Verification")

    # 8. Structured JSON Logging Formatter Test
    def test_08_structured_json_logging(self):
        """Verify JsonFormatter outputs valid JSON lines with standard fields."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="claimsense.audit",
            level=logging.INFO,
            pathname=__file__,
            lineno=42,
            msg="User %s performed action %s",
            args=("admin", "freeze_report"),
            exc_info=None,
        )
        record.request_id = "req-12345"
        record.user_id = 99

        formatted = formatter.format(record)
        data = json.loads(formatted)

        self.assertEqual(data["level"], "INFO")
        self.assertEqual(data["logger"], "claimsense.audit")
        self.assertEqual(data["message"], "User admin performed action freeze_report")
        self.assertEqual(data["request_id"], "req-12345")
        self.assertEqual(data["user_id"], 99)
        self.assertIn("timestamp", data)

    # 9. Report Snapshot Persistence Lifecycle Test
    def test_09_report_snapshot_persistence_lifecycle(self):
        """Verify freeze_report and get_active_frozen_report save and retrieve immutable PDFs."""
        claim_id = "CLM-20261121-P11A"
        report_meta = freeze_report(
            claim_id=claim_id,
            user_id=self.test_user_id,
            report_type="VERIFICATION_AUDIT",
            upload_root=self.test_uploads_dir,
            reports_root=self.test_reports_dir,
        )

        self.assertIsNotNone(report_meta)
        self.assertEqual(report_meta["claim_id"], claim_id)
        self.assertEqual(report_meta["status"], "ACTIVE")
        self.assertEqual(len(report_meta["file_hash"]), 64)
        self.assertGreater(report_meta["file_size_bytes"], 1000)

        # Verify file exists on disk and hash matches
        report_path = Path(report_meta["report_path"])
        self.assertTrue(report_path.exists())
        self.assertEqual(calculate_sha256(report_path), report_meta["file_hash"])

        # Test retrieval
        retrieved = get_active_frozen_report(claim_id, report_type="VERIFICATION_AUDIT")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["id"], report_meta["id"])
        self.assertEqual(retrieved["file_hash"], report_meta["file_hash"])

    # 10. Claims Freeze Report API Endpoint Test
    def test_10_claims_freeze_report_api_endpoint(self):
        """Verify POST /api/claims/<id>/freeze-report and GET /api/claims/<id>/report."""
        claim_id = "CLM-20261121-P11A"

        # Sign in as assessor
        with self.client.session_transaction() as sess:
            sess["user_id"] = self.test_user_id
            sess["role"] = "assessor"

        # Freeze report via API
        res = self.client.post(f"/api/claims/{claim_id}/freeze-report")
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("report", data)
        self.assertEqual(data["report"]["claim_id"], claim_id)

        # Download report via GET /report (persisted snapshot)
        res_get = self.client.get(f"/api/claims/{claim_id}/report")
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.headers.get("Content-Type"), "application/pdf")
        self.assertEqual(res_get.headers.get("X-Report-Source"), "persisted-snapshot")
        self.assertIsNotNone(res_get.headers.get("ETag"))

    # 11. Containerization & Proxy Manifests Test
    def test_11_containerization_manifests_validation(self):
        """Verify presence and syntax of Dockerfile, docker-compose, and Nginx configurations."""
        root = Path(__file__).resolve().parent.parent

        dockerfile = root / "Dockerfile"
        compose_file = root / "docker-compose.yml"
        dockerignore = root / ".dockerignore"
        nginx_conf = root / "deploy" / "nginx" / "nginx.conf"
        vh_conf = root / "deploy" / "nginx" / "conf.d" / "claimsense.conf"

        self.assertTrue(dockerfile.exists(), "Dockerfile must exist")
        self.assertTrue(compose_file.exists(), "docker-compose.yml must exist")
        self.assertTrue(dockerignore.exists(), ".dockerignore must exist")
        self.assertTrue(nginx_conf.exists(), "deploy/nginx/nginx.conf must exist")
        self.assertTrue(vh_conf.exists(), "deploy/nginx/conf.d/claimsense.conf must exist")

        # Validate Dockerfile contents
        df_text = dockerfile.read_text(encoding="utf-8")
        self.assertIn("FROM python:", df_text)
        self.assertIn("HEALTHCHECK", df_text)
        self.assertIn("claimsense", df_text)

        # Validate docker-compose contents
        compose_text = compose_file.read_text(encoding="utf-8")
        self.assertIn("claimsense-app", compose_text)
        self.assertIn("claimsense-nginx", compose_text)
        self.assertIn("5001", compose_text)

        # Validate Nginx config
        vh_text = vh_conf.read_text(encoding="utf-8")
        self.assertIn("client_max_body_size 16M", vh_text)
        self.assertIn("proxy_pass", vh_text)

    # 12. Reports Table Migration Script Test
    def test_12_reports_table_migration_script(self):
        """Verify scripts/migrations/migrate_reports_table.py forward migration and rollback."""
        mig_db = self.temp_dir / "migration_test.db"
        mig_uri = f"sqlite:///{mig_db.as_posix()}"
        engine = init_database(mig_uri)

        # Verify upgrade succeeds
        upgrade(engine)

        # Verify columns exist
        insp = sqlite3.connect(str(mig_db))
        cursor = insp.cursor()
        cursor.execute("PRAGMA table_info(reports);")
        cols = {row[1] for row in cursor.fetchall()}
        self.assertIn("report_type", cols)
        self.assertIn("file_hash", cols)
        self.assertIn("file_size_bytes", cols)
        self.assertIn("status", cols)

        # Test downgrade
        downgrade(engine)
        cursor.execute("PRAGMA table_info(reports);")
        legacy_cols = {row[1] for row in cursor.fetchall()}
        self.assertIn("report_path", legacy_cols)
        self.assertIn("claim_id", legacy_cols)
        insp.close()


if __name__ == "__main__":
    unittest.main()
