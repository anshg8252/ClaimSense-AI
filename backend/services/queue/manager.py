"""Pluggable asynchronous task queue manager for ClaimSense AI (Phase 12).

Provides dual-engine task dispatching:
1. RedisTaskBroker: Redis list/queue protocol for containerized/Docker environments.
2. ThreadedTaskBroker: In-process ThreadPoolExecutor with persistent SQLite state for
   local Windows/macOS/Linux development and standalone test suites without external daemons.
"""
import concurrent.futures
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from backend.config import Config
from backend.database.db import get_db_session
from backend.database.models import ProcessingTask, Claim
from backend.services.tasks.claim_tasks import execute_claim_processing_pipeline
from backend.utils.logger import setup_logger

logger = setup_logger("claimsense.queue")

_EXECUTOR: Optional[concurrent.futures.ThreadPoolExecutor] = None


class ThreadedTaskBroker:
    """In-process thread-pool executor broker with persistent SQLite task tracking."""

    def __init__(self, max_workers: int = 4):
        global _EXECUTOR
        if _EXECUTOR is None:
            _EXECUTOR = concurrent.futures.ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="ClaimSenseWorker",
            )
        self.executor = _EXECUTOR

    def enqueue(self, task_id: str, claim_id: str) -> bool:
        """Dispatches claim processing job to background worker thread."""
        try:
            self.executor.submit(
                execute_claim_processing_pipeline,
                claim_id=claim_id,
                task_id=task_id,
                worker_id="thread_worker_pool",
            )
            return True
        except Exception as exc:
            logger.error(f"Failed to submit task '{task_id}' to ThreadPoolExecutor: {exc}")
            return False

    def is_healthy(self) -> bool:
        return self.executor is not None and not self.executor._shutdown


class RedisTaskBroker:
    """Redis-backed task broker using Redis list / queue protocol."""

    QUEUE_KEY = "claimsense:tasks:claims"

    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self._client = None
        self._connect()

    def _connect(self):
        try:
            import redis
        except ImportError:
            logger.warning(
                "Python 'redis' package is not installed; RedisTaskBroker disabled and falling back to ThreadedTaskBroker."
            )
            self._client = None
            return

        try:
            self._client = redis.Redis.from_url(self.redis_url, socket_timeout=2.0)
            self._client.ping()
        except Exception as exc:
            logger.warning(f"Redis unreachable at {self.redis_url} ({exc}); falling back to ThreadedTaskBroker.")
            self._client = None

    def is_healthy(self) -> bool:
        if not self._client:
            self._connect()
        if self._client:
            try:
                return bool(self._client.ping())
            except Exception:
                return False
        return False

    def enqueue(self, task_id: str, claim_id: str) -> bool:
        if not self.is_healthy():
            return False
        payload = json.dumps({
            "task_id": task_id,
            "claim_id": claim_id,
            "enqueued_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            self._client.rpush(self.QUEUE_KEY, payload)
            return True
        except Exception as exc:
            logger.error(f"Failed to push task '{task_id}' to Redis queue: {exc}")
            return False

    def get_queue_depth(self) -> int:
        if self.is_healthy():
            try:
                return int(self._client.llen(self.QUEUE_KEY))
            except Exception:
                return 0
        return 0


class TaskManager:
    """Singleton task manager handling enqueueing, status polling, and broker selection."""

    _instance: Optional["TaskManager"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        self.threaded_broker = ThreadedTaskBroker(max_workers=4)
        self.redis_broker = None
        redis_url = getattr(Config, "REDIS_URL", "redis://localhost:6379/0")
        if redis_url:
            self.redis_broker = RedisTaskBroker(redis_url)

        self._initialized = True

    def get_active_broker_name(self) -> str:
        """Determines active broker: 'redis' if available and requested, else 'threaded'."""
        broker_type = getattr(Config, "QUEUE_BROKER_TYPE", "auto")
        if broker_type in ("redis", "auto"):
            if self.redis_broker and self.redis_broker.is_healthy():
                return "redis"
            if broker_type == "redis":
                logger.warning("QUEUE_BROKER_TYPE='redis' requested but Redis is unavailable; falling back to 'threaded' broker.")
        return "threaded"

    def enqueue_claim_task(
        self,
        claim_id: str,
        user_id: Optional[int] = None,
        sync: bool = False,
    ) -> Tuple[ProcessingTask, bool]:
        """Enqueues or synchronously executes a claim processing job.

        Returns:
            (ProcessingTask, is_newly_enqueued)
        """
        # 1. Idempotency Check: Return existing active task if already processing
        with get_db_session() as db:
            existing_task = (
                db.query(ProcessingTask)
                .filter(
                    ProcessingTask.claim_id == claim_id,
                    ProcessingTask.status.in_(["QUEUED", "PROCESSING"]),
                )
                .order_by(ProcessingTask.created_at.desc())
                .first()
            )
            if existing_task:
                logger.info(f"Idempotent task match: Claim '{claim_id}' already has active task '{existing_task.task_id}'.")
                db.expunge(existing_task)
                return existing_task, False

            # 2. Mint new task record
            task_id = f"task-{uuid.uuid4().hex[:16]}"
            new_task = ProcessingTask(
                task_id=task_id,
                claim_id=claim_id,
                user_id=user_id,
                task_type="CLAIM_PIPELINE",
                status="QUEUED",
                current_stage="INTAKE",
                progress_percent=5,
                retry_count=0,
                max_retries=getattr(Config, "TASK_MAX_RETRIES", 3),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(new_task)
            db.commit()
            db.refresh(new_task)
            db.expunge(new_task)

        # 3. Synchronous execution if requested
        if sync:
            logger.info(f"Executing task '{task_id}' synchronously for claim '{claim_id}'.")
            execute_claim_processing_pipeline(claim_id=claim_id, task_id=task_id, worker_id="synchronous_direct")
            with get_db_session() as db:
                refreshed = db.query(ProcessingTask).filter_by(task_id=task_id).first()
                if refreshed:
                    db.expunge(refreshed)
                return refreshed or new_task, True

        # 4. Asynchronous dispatching via active broker
        active_broker = self.get_active_broker_name()
        enqueued = False

        if active_broker == "redis" and self.redis_broker:
            enqueued = self.redis_broker.enqueue(task_id=task_id, claim_id=claim_id)
            if enqueued:
                logger.info(f"Task '{task_id}' enqueued to Redis for claim '{claim_id}'.")

        # Fallback to threaded broker if Redis dispatching failed or not active
        if not enqueued:
            enqueued = self.threaded_broker.enqueue(task_id=task_id, claim_id=claim_id)
            logger.info(f"Task '{task_id}' enqueued to ThreadedBroker for claim '{claim_id}'.")

        return new_task, True

    def get_task_status(self, claim_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves latest processing task state for a claim."""
        with get_db_session() as db:
            task = (
                db.query(ProcessingTask)
                .filter_by(claim_id=claim_id)
                .order_by(ProcessingTask.created_at.desc())
                .first()
            )
            if task:
                return task.to_dict()
        return None

    def get_queue_metrics(self) -> Dict[str, Any]:
        """Collects operational task queue telemetry."""
        counts = {"queued": 0, "processing": 0, "completed": 0, "failed": 0}
        with get_db_session() as db:
            try:
                for status_key in counts.keys():
                    counts[status_key] = (
                        db.query(ProcessingTask)
                        .filter(ProcessingTask.status == status_key.upper())
                        .count()
                    )
            except Exception:
                pass

        active_broker = self.get_active_broker_name()
        queue_depth = 0
        if active_broker == "redis" and self.redis_broker:
            queue_depth = self.redis_broker.get_queue_depth()

        return {
            "active_broker": active_broker,
            "broker_healthy": True,
            "queue_depth": queue_depth,
            "task_counts": counts,
        }

    def recover_stale_tasks(self, timeout_seconds: int = 300) -> int:
        """Detects tasks stuck in PROCESSING past the timeout threshold and marks them FAILED or retries."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=timeout_seconds)
        recovered = 0
        tasks_to_requeue = []

        with get_db_session() as db:
            stale_tasks = (
                db.query(ProcessingTask)
                .filter(
                    ProcessingTask.status == "PROCESSING",
                    ProcessingTask.updated_at < cutoff,
                )
                .all()
            )
            for task in stale_tasks:
                if task.retry_count < task.max_retries:
                    task.retry_count += 1
                    task.status = "QUEUED"
                    task.current_stage = "INTAKE"
                    task.error_message = f"Stale task auto-recovered on retry {task.retry_count}/{task.max_retries}"
                    task.updated_at = now
                    tasks_to_requeue.append((task.task_id, task.claim_id))
                else:
                    task.status = "FAILED"
                    task.error_code = "TASK_TIMEOUT"
                    task.error_message = f"Task exceeded processing timeout of {timeout_seconds}s without heartbeat."
                    task.completed_at = now
                    task.updated_at = now
                recovered += 1
            if recovered > 0:
                db.commit()

        # Re-dispatch recovered tasks through the configured active broker after DB commit
        if tasks_to_requeue:
            active_broker = self.get_active_broker_name()
            for task_id, claim_id in tasks_to_requeue:
                enqueued = False
                if active_broker == "redis" and self.redis_broker:
                    enqueued = self.redis_broker.enqueue(task_id=task_id, claim_id=claim_id)
                if not enqueued:
                    self.threaded_broker.enqueue(task_id=task_id, claim_id=claim_id)

        if recovered > 0:
            logger.info(f"Recovered {recovered} stale processing tasks.")
        return recovered


# Global singleton instance
queue_manager = TaskManager()
