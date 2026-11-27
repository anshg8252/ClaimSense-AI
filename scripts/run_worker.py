#!/usr/bin/env python3
"""ClaimSense AI — Standalone Task Queue Worker Daemon (Phase 12).

Consumes background claims processing tasks from Redis or SQLite queues,
executes the multi-stage pipeline, updates task progression, and handles
graceful shutdown signals.
"""
import argparse
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.config import Config
from backend.database.db import init_database, get_db_session
from backend.database.models import ProcessingTask
from backend.services.queue.manager import queue_manager, RedisTaskBroker
from backend.services.tasks.claim_tasks import execute_claim_processing_pipeline
from backend.utils.logger import setup_logger

logger = setup_logger("claimsense.worker")

RUNNING = True


def handle_shutdown(signum, frame):
    """Graceful shutdown signal trap."""
    global RUNNING
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    logger.info(f"Received termination signal {sig_name}. Initiating graceful shutdown...")
    RUNNING = False


def run_worker_loop(
    broker_type: str = "auto",
    poll_interval: float = 1.0,
    single_run: bool = False,
    db_uri: Optional[str] = None,
):
    """Main worker execution loop."""
    global RUNNING
    logger.info(f"Starting ClaimSense AI Task Worker [Broker: {broker_type}, PID: {os.getpid()}]")

    # Register OS signal handlers (SIGINT and SIGTERM where supported)
    signal.signal(signal.SIGINT, handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, handle_shutdown)

    # Initialize database schemas
    resolved_db_uri = db_uri or getattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///data/claimsense.db")
    init_database(resolved_db_uri)

    redis_broker = None
    if broker_type in ("redis", "auto"):
        redis_broker = queue_manager.redis_broker
        if redis_broker and redis_broker.is_healthy():
            logger.info(f"Worker connected to Redis at {Config.REDIS_URL}")
        else:
            logger.warning("Redis is unreachable or not configured. Falling back to DB-polling broker.")
            redis_broker = None

    worker_id = f"worker-{os.getpid()}-{int(time.time())}"
    tasks_processed = 0

    while RUNNING:
        try:
            # 1. Recover stale tasks periodically
            if tasks_processed % 10 == 0:
                recovered = queue_manager.recover_stale_tasks(
                    timeout_seconds=getattr(Config, "TASK_TIMEOUT_SECONDS", 300)
                )
                if recovered > 0:
                    logger.info(f"Worker recovered {recovered} stale tasks.")

            task_payload = None

            # 2. Try Redis queue if available
            if redis_broker and redis_broker.is_healthy():
                client = redis_broker._client
                if client:
                    # Non-blocking pop with short timeout
                    raw = client.blpop(RedisTaskBroker.QUEUE_KEY, timeout=int(max(1, poll_interval)))
                    if raw:
                        _, val = raw
                        try:
                            task_payload = json.loads(val.decode("utf-8") if isinstance(val, bytes) else val)
                        except Exception as parse_err:
                            logger.error(f"Failed to parse Redis task JSON: {parse_err}")

            # 3. Fallback to SQLite task table polling
            if not task_payload:
                with get_db_session() as db:
                    task_record = (
                        db.query(ProcessingTask)
                        .filter_by(status="QUEUED")
                        .order_by(ProcessingTask.created_at.asc())
                        .first()
                    )
                    if task_record:
                        task_payload = {
                            "task_id": task_record.task_id,
                            "claim_id": task_record.claim_id,
                        }

            # 4. Execute task if discovered
            if task_payload:
                task_id = task_payload.get("task_id")
                claim_id = task_payload.get("claim_id")
                logger.info(f"Worker claimed task '{task_id}' for claim '{claim_id}'.")

                result = execute_claim_processing_pipeline(
                    claim_id=claim_id,
                    task_id=task_id,
                    worker_id=worker_id,
                )
                tasks_processed += 1
                status_label = result.get("status") or ("COMPLETED" if result.get("success") else "FAILED")
                logger.info(f"Task '{task_id}' completed with status: {status_label}")

                if single_run:
                    logger.info("Single-run flag active; exiting worker loop.")
                    break
            else:
                if single_run:
                    logger.info("No queued tasks discovered in single-run mode; exiting.")
                    break
                time.sleep(poll_interval)

        except Exception as exc:
            logger.error(f"Unexpected worker loop exception: {exc}", exc_info=True)
            time.sleep(poll_interval)

    logger.info(f"Worker shutdown cleanly. Total tasks processed: {tasks_processed}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClaimSense AI Asynchronous Task Worker")
    parser.add_argument("--broker", default="auto", choices=["auto", "redis", "threaded"], help="Task broker type")
    parser.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds")
    parser.add_argument("--single-run", action="store_true", help="Process at most one job then exit")
    args = parser.parse_args()

    run_worker_loop(
        broker_type=args.broker,
        poll_interval=args.interval,
        single_run=args.single_run,
    )
