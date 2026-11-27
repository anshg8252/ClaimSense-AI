"""Zero-downtime online SQLite database backup tool for ClaimSense AI (Production Hardened).

Leverages Python's sqlite3 online backup API to stream an atomic, consistent snapshot
of the database to a timestamped archive without locking active readers or writers.
"""
import argparse
import hashlib
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple


def calculate_sha256(file_path: Path) -> str:
    """Computes the SHA-256 digest of a file in 64 KB chunks."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def backup_sqlite_database(
    source_db_path: Path,
    backup_dir: Path,
    retention_days: int = 30,
    dry_run: bool = False,
) -> Tuple[bool, Optional[Path], Optional[str]]:
    """Performs an online backup of an SQLite database with SHA-256 verification and retention pruning.

    Returns:
        (success, backup_path, sha256_hash)
    """
    source_db_path = Path(source_db_path).resolve()
    backup_dir = Path(backup_dir).resolve()

    if not source_db_path.exists():
        print(f"[ERROR] Source database does not exist: {source_db_path}", file=sys.stderr)
        return False, None, None

    if source_db_path.stat().st_size == 0:
        print(
            f"[ERROR] Source database is empty (0 bytes): {source_db_path}. "
            f"Refusing to create a silent empty backup. Configure DATABASE_PATH or pass --db.",
            file=sys.stderr,
        )
        return False, None, None

    if not dry_run:
        backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_filename = f"claimsense_{timestamp}.db"
    backup_path = backup_dir / backup_filename
    checksum_path = backup_dir / f"{backup_filename}.sha256"

    if dry_run:
        print(f"[DRY-RUN] Would backup '{source_db_path}' -> '{backup_path}'")
        return True, backup_path, "dry-run-hash"

    start_time = time.time()
    try:
        source_conn = sqlite3.connect(str(source_db_path))
        dest_conn = sqlite3.connect(str(backup_path))

        with dest_conn:
            source_conn.backup(dest_conn, pages=100, sleep=0.01)

        dest_conn.close()
        source_conn.close()
    except Exception as exc:
        print(f"[ERROR] Backup execution failed: {exc}", file=sys.stderr)
        if backup_path.exists():
            backup_path.unlink(missing_ok=True)
        return False, None, None

    elapsed = round(time.time() - start_time, 2)
    file_size_bytes = backup_path.stat().st_size
    file_size_kb = round(file_size_bytes / 1024, 2)
    sha256_hash = calculate_sha256(backup_path)

    # Save cryptographic checksum file
    checksum_path.write_text(f"{sha256_hash}  {backup_filename}\n", encoding="utf-8")

    print(f"[SUCCESS] Database backed up successfully in {elapsed}s:")
    print(f"  Archive:  {backup_path} ({file_size_kb} KB)")
    print(f"  Checksum: {sha256_hash}")

    # Retention policy: Prune archives older than retention_days
    if retention_days > 0:
        pruned_count = prune_old_backups(backup_dir, retention_days)
        if pruned_count > 0:
            print(f"[CLEANUP] Pruned {pruned_count} historical backup(s) older than {retention_days} days.")

    return True, backup_path, sha256_hash


def prune_old_backups(backup_dir: Path, retention_days: int) -> int:
    """Removes backup archives older than the specified retention window."""
    now = time.time()
    cutoff_time = now - (retention_days * 86400)
    pruned = 0

    for file in backup_dir.glob("claimsense_*.db*"):
        if file.is_file() and file.stat().st_mtime < cutoff_time:
            try:
                file.unlink()
                pruned += 1
            except Exception as e:
                print(f"[WARNING] Could not delete old backup '{file}': {e}", file=sys.stderr)

    return pruned


def verify_backup(backup_path: Path) -> bool:
    """Verifies SQLite integrity of the backup file."""
    backup_path = Path(backup_path).resolve()
    if not backup_path.exists():
        print(f"[ERROR] Target file does not exist: {backup_path}", file=sys.stderr)
        return False

    try:
        conn = sqlite3.connect(str(backup_path))
        cursor = conn.cursor()
        cursor.execute("PRAGMA quick_check")
        result = cursor.fetchone()
        conn.close()
        is_ok = bool(result and result[0] == "ok")
        print(f"[INTEGRITY] Quick check for '{backup_path.name}': {'PASS (ok)' if is_ok else 'FAIL'}")
        return is_ok
    except Exception as exc:
        print(f"[ERROR] Integrity verification failed: {exc}", file=sys.stderr)
        return False


def restore_sqlite_database(backup_path: Path, target_db_path: Path) -> bool:
    """Restores a verified SQLite backup archive into target_db_path using the sqlite3 backup API."""
    backup_path = Path(backup_path).resolve()
    target_db_path = Path(target_db_path).resolve()

    if not verify_backup(backup_path):
        return False

    target_db_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        src_conn = sqlite3.connect(str(backup_path))
        dst_conn = sqlite3.connect(str(target_db_path))
        with dst_conn:
            src_conn.backup(dst_conn, pages=100, sleep=0.01)
        dst_conn.close()
        src_conn.close()
        return verify_backup(target_db_path)
    except Exception as exc:
        print(f"[ERROR] Restore execution failed: {exc}", file=sys.stderr)
        return False


def resolve_default_db_path() -> str:
    """Resolves the configured SQLite database path via DATABASE_PATH env var or backend.config.Config."""
    project_root = Path(__file__).resolve().parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    env_db = os.getenv("DATABASE_PATH", "").strip()
    if env_db:
        p = Path(env_db)
        return str(p if p.is_absolute() else (project_root / p))
    try:
        from backend.config import Config
        return str(Config.DATABASE_PATH)
    except Exception:
        return str(project_root / "data" / "claimsense.db")


def main():
    default_db = resolve_default_db_path()
    parser = argparse.ArgumentParser(description="ClaimSense AI SQLite Online Backup Utility")
    parser.add_argument(
        "--db",
        type=str,
        default=default_db,
        help=f"Path to source SQLite database (default: {default_db})",
    )
    parser.add_argument(
        "--dest",
        type=str,
        default="backups",
        help="Destination directory for backup archives (default: backups)",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=30,
        help="Number of days to retain daily backups (default: 30, 0 to disable)",
    )
    parser.add_argument(
        "--verify",
        type=str,
        default=None,
        help="Verify SQLite integrity of a specific backup archive file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate backup process without writing files",
    )

    args = parser.parse_args()

    if args.verify:
        success = verify_backup(Path(args.verify))
        sys.exit(0 if success else 1)

    project_root = Path(__file__).resolve().parent.parent
    db_path = project_root / args.db if not Path(args.db).is_absolute() else Path(args.db)
    dest_path = project_root / args.dest if not Path(args.dest).is_absolute() else Path(args.dest)

    success, bpath, _ = backup_sqlite_database(
        source_db_path=db_path,
        backup_dir=dest_path,
        retention_days=args.retention_days,
        dry_run=args.dry_run,
    )

    if success and bpath and not args.dry_run:
        verify_backup(bpath)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
