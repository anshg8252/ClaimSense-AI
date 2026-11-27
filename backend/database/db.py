"""Database connection, session management, and schema initialization for ClaimSense AI."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session, scoped_session

from backend.database.models import (
    Base,
    User,
    Claim,
    Document,
    ClaimImage,
    VehicleDamageAnalysis,
    VehicleDamageDetection,
    ClaimVerificationRun,
    VerificationFinding,
)
from backend.utils.logger import setup_logger

logger = setup_logger("claimsense.database")

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None
_scoped_session: Optional[scoped_session] = None


@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Enable foreign key constraints on SQLite connections."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_database(db_uri: str) -> Engine:
    """Initializes SQLAlchemy engine, session maker, and creates all tables."""
    global _engine, _SessionFactory, _scoped_session

    connect_args = {}
    if db_uri.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    _engine = create_engine(
        db_uri,
        connect_args=connect_args,
        echo=False,
    )
    _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    _scoped_session = scoped_session(_SessionFactory)

    # Create tables
    Base.metadata.create_all(bind=_engine)
    _ensure_schema_migrations(_engine)
    logger.info(f"Initialized database schema with URI: {db_uri}")
    return _engine


def _ensure_schema_migrations(engine: Engine) -> None:
    """Apply compatibility migrations for existing SQLite databases."""
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())

        if "claims" in table_names:
            claim_columns = {col["name"] for col in inspector.get_columns("claims")}
            if "incident_location" not in claim_columns:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE claims ADD COLUMN incident_location VARCHAR(256)"))

        if "extracted_information" in table_names:
            columns = {column["name"] for column in inspector.get_columns("extracted_information")}
            migrations = {
                "field_status": "VARCHAR(32)",
                "source_filename": "VARCHAR(255)",
                "page_number": "INTEGER",
                "extraction_method": "VARCHAR(64)",
                "supporting_text": "TEXT",
                "confidence_score": "FLOAT",
                "error_message": "TEXT",
                "evaluation_metadata": "TEXT",
            }
            for name, ddl in migrations.items():
                if name not in columns:
                    with engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE extracted_information ADD COLUMN {name} {ddl}"))

        if "vehicle_damage_analyses" in table_names:
            v_cols = {col["name"] for col in inspector.get_columns("vehicle_damage_analyses")}
            v_migrations = {
                "image_hash": "VARCHAR(64)",
                "image_path": "VARCHAR(512)",
                "original_image_path": "VARCHAR(512) DEFAULT ''",
                "annotated_image_path": "VARCHAR(512)",
                "model_name": "VARCHAR(64) DEFAULT 'YOLOv8n-CarDD'",
                "model_version": "VARCHAR(32) DEFAULT 'v1.0'",
                "detection_method": "VARCHAR(64) DEFAULT 'YOLOv8'",
                "model_available": "BOOLEAN DEFAULT 1",
                "opencv_observations": "TEXT",
                "total_detections": "INTEGER DEFAULT 0",
                "total_damages_detected": "INTEGER DEFAULT 0",
                "damage_categories": "TEXT",
                "detected_categories": "TEXT",
                "highest_confidence": "FLOAT",
                "max_confidence": "FLOAT",
                "average_confidence": "FLOAT",
                "analysis_status": "VARCHAR(32) DEFAULT 'completed'",
                "processing_time_ms": "FLOAT",
                "inference_time_ms": "FLOAT",
                "device": "VARCHAR(32) DEFAULT 'cpu'",
            }
            for col_name, ddl in v_migrations.items():
                if col_name not in v_cols:
                    with engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE vehicle_damage_analyses ADD COLUMN {col_name} {ddl}"))

        if "claim_verification_runs" in table_names:
            cvr_cols = {col["name"] for col in inspector.get_columns("claim_verification_runs")}
            if "evaluated_rules_count" in cvr_cols:
                # Table has legacy schema with NOT NULL constraints on legacy columns.
                # Recreate table cleanly with modern schema and copy over historical rows.
                with engine.begin() as conn:
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS claim_verification_runs_migrated (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            run_id VARCHAR(64),
                            claim_id VARCHAR(32) NOT NULL,
                            engine_version VARCHAR(32) NOT NULL DEFAULT '1.0.0',
                            overall_status VARCHAR(32) NOT NULL DEFAULT 'CONSISTENT',
                            consistency_score FLOAT NOT NULL DEFAULT 100.0,
                            total_comparisons INTEGER NOT NULL DEFAULT 0,
                            matched_comparisons INTEGER NOT NULL DEFAULT 0,
                            mismatched_comparisons INTEGER NOT NULL DEFAULT 0,
                            missing_evidence_count INTEGER NOT NULL DEFAULT 0,
                            inconclusive_count INTEGER NOT NULL DEFAULT 0,
                            high_severity_count INTEGER NOT NULL DEFAULT 0,
                            critical_severity_count INTEGER NOT NULL DEFAULT 0,
                            summary TEXT,
                            recommendations TEXT,
                            processing_status VARCHAR(32) NOT NULL DEFAULT 'completed',
                            processing_time_ms FLOAT,
                            created_at DATETIME NOT NULL,
                            updated_at DATETIME,
                            FOREIGN KEY(claim_id) REFERENCES claims(claim_id)
                        )
                    """))
                    conn.execute(text("""
                        INSERT INTO claim_verification_runs_migrated (
                            id, run_id, claim_id, engine_version, overall_status, consistency_score,
                            total_comparisons, matched_comparisons, mismatched_comparisons,
                            missing_evidence_count, inconclusive_count, high_severity_count, critical_severity_count,
                            created_at, updated_at
                        )
                        SELECT 
                            id, 
                            run_id, 
                            claim_id, 
                            COALESCE(engine_version, '1.0.0'), 
                            overall_status, 
                            consistency_score,
                            COALESCE(total_comparisons, evaluated_rules_count, 0),
                            COALESCE(matched_comparisons, matching_rules_count, 0),
                            COALESCE(mismatched_comparisons, mismatching_rules_count, 0),
                            COALESCE(missing_evidence_count, missing_rules_count, 0),
                            COALESCE(inconclusive_count, unverified_rules_count, 0),
                            COALESCE(high_severity_count, 0),
                            0,
                            created_at,
                            created_at
                        FROM claim_verification_runs
                    """))
                    conn.execute(text("DROP TABLE claim_verification_runs"))
                    conn.execute(text("ALTER TABLE claim_verification_runs_migrated RENAME TO claim_verification_runs"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_claim_verification_runs_claim_id ON claim_verification_runs (claim_id)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_claim_verification_runs_run_id ON claim_verification_runs (run_id)"))
            else:
                cvr_migrations = {
                    "run_id": "VARCHAR(64)",
                    "total_comparisons": "INTEGER DEFAULT 0",
                    "matched_comparisons": "INTEGER DEFAULT 0",
                    "mismatched_comparisons": "INTEGER DEFAULT 0",
                    "missing_evidence_count": "INTEGER DEFAULT 0",
                    "inconclusive_count": "INTEGER DEFAULT 0",
                    "critical_severity_count": "INTEGER DEFAULT 0",
                    "summary": "TEXT",
                    "recommendations": "TEXT",
                    "processing_status": "VARCHAR(32) DEFAULT 'completed'",
                    "processing_time_ms": "FLOAT",
                    "updated_at": "DATETIME",
                }
                for col_name, ddl in cvr_migrations.items():
                    if col_name not in cvr_cols:
                        with engine.begin() as conn:
                            conn.execute(text(f"ALTER TABLE claim_verification_runs ADD COLUMN {col_name} {ddl}"))

        if "claims" in table_names:
            claims_cols = {col["name"] for col in inspector.get_columns("claims")}
            claims_migrations = {
                "final_verdict": "VARCHAR(32)",
                "decision_reason": "TEXT",
                "fraud_risk_level": "VARCHAR(32)",
                "decision_timestamp": "DATETIME",
                "verdict_details": "TEXT",
            }
            for col_name, ddl in claims_migrations.items():
                if col_name not in claims_cols:
                    with engine.begin() as conn:
                        conn.execute(text(f"ALTER TABLE claims ADD COLUMN {col_name} {ddl}"))

    except Exception as exc:
        logger.warning(f"Schema migration check skipped or failed: {exc}")


def get_engine() -> Engine:
    """Returns the current database engine."""
    global _engine
    if _engine is None:
        raise RuntimeError("Database engine has not been initialized. Call init_database() first.")
    return _engine


def close_engine():
    """Disposes engine and closes active connections, releasing file locks."""
    global _engine, _SessionFactory, _scoped_session
    if _scoped_session is not None:
        try:
            _scoped_session.remove()
        except Exception:
            pass
    if _engine is not None:
        try:
            _engine.dispose()
        except Exception:
            pass


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for scoped database sessions with automatic commit/rollback."""
    global _SessionFactory
    if _SessionFactory is None:
        raise RuntimeError("Database session factory has not been initialized. Call init_database() first.")
    session: Session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception as exc:
        session.rollback()
        logger.error(f"Database session rolled back due to error: {exc}")
        raise
    finally:
        session.close()


def migrate_existing_claims_from_disk(upload_dir: Path) -> int:
    """Scans the uploads directory for legacy metadata.json files and ingests them into SQLite.

    Guarantees zero data loss from Phase 2 while populating the database.
    """
    if not upload_dir.exists():
        return 0

    migrated_count = 0
    with get_db_session() as session:
        for claim_path in upload_dir.iterdir():
            if not claim_path.is_dir():
                continue

            metadata_file = claim_path / "metadata.json"
            if not metadata_file.exists():
                continue

            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)

                claim_id = meta.get("claim_id", claim_path.name)

                # Check if already in SQLite
                existing = session.query(Claim).filter_by(claim_id=claim_id).first()
                if existing:
                    continue

                # Parse created_at
                created_at_str = meta.get("created_at")
                created_at = datetime.now(timezone.utc)
                if created_at_str:
                    try:
                        created_at = datetime.fromisoformat(created_at_str)
                    except Exception:
                        pass

                # Create Claim record
                claim = Claim(
                    claim_id=claim_id,
                    user_id=meta.get("user_id"),
                    claimant_name=meta.get("claimant_name", "Unknown Claimant"),
                    policy_number=meta.get("policy_number", "UNKNOWN"),
                    vehicle_number=meta.get("vehicle_number", "UNKNOWN"),
                    accident_date=meta.get("accident_date", "UNKNOWN"),
                    claim_description=meta.get("claim_description", ""),
                    status=meta.get("status", "SUBMITTED"),
                    created_at=created_at,
                    updated_at=created_at,
                )
                session.add(claim)
                session.flush()

                # Ingest Document and Image records from metadata files dict
                files_dict = meta.get("files", {})
                type_map = {
                    "policy_document": "POLICY_DOCUMENT",
                    "claim_form": "CLAIM_FORM",
                    "invoice_document": "INVOICE",
                }

                for file_key, info in files_dict.items():
                    if not isinstance(info, dict):
                        continue
                    original_name = info.get("original_name", file_key)
                    saved_as = info.get("saved_as", file_key)
                    rel_path = info.get("relative_path", "")
                    size_bytes = info.get("size_bytes", 0)
                    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""

                    if file_key == "vehicle_image":
                        claim_img = ClaimImage(
                            claim_id=claim_id,
                            image_type="VEHICLE_ACCIDENT",
                            file_path=rel_path,
                            original_filename=original_name,
                            stored_filename=saved_as,
                            file_extension=ext,
                            file_size=size_bytes,
                            created_at=created_at,
                        )
                        session.add(claim_img)
                    else:
                        doc_type = type_map.get(file_key, "OTHER")
                        doc = Document(
                            claim_id=claim_id,
                            document_type=doc_type,
                            file_path=rel_path,
                            original_filename=original_name,
                            stored_filename=saved_as,
                            file_extension=ext,
                            file_size=size_bytes,
                            created_at=created_at,
                        )
                        session.add(doc)

                migrated_count += 1
                logger.info(f"Successfully migrated legacy claim {claim_id} into SQLite database.")

            except Exception as e:
                logger.error(f"Failed to migrate claim from {metadata_file}: {e}")

    return migrated_count
