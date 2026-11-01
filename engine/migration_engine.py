import os
import shutil
import threading
import time
from datetime import datetime

from database import get_connection
from config import (
    FILE_STABILITY_SECONDS,
    LOCAL_SECONDARY_PATH,
    LOCAL_SSD_PATH,
    MIGRATION_GUARD_SECONDS,
    SSD_MIN_FREE_MB,
    MAX_AUTOMATIC_PROMOTION_MB,
)


_recent_migrations = {}
_migration_lock = threading.RLock()


def _normalize(path):
    return os.path.normcase(os.path.abspath(path))


def mark_migration(source_file, destination_file=None):
    now = time.time()
    with _migration_lock:
        _recent_migrations[_normalize(source_file)] = now
        if destination_file:
            _recent_migrations[_normalize(destination_file)] = now


def is_internal_migration(path):
    normalized = _normalize(path)
    with _migration_lock:
        migration_time = _recent_migrations.get(normalized)
        if migration_time is None:
            return False
        if time.time() - migration_time <= MIGRATION_GUARD_SECONDS:
            return True
        _recent_migrations.pop(normalized, None)
        return False


def get_tier_path(tier):
    tier = tier.upper()
    if tier == "SSD":
        return LOCAL_SSD_PATH
    if tier == "SECONDARY":
        return LOCAL_SECONDARY_PATH
    return None


def get_tier_for_path(path):
    normalized = _normalize(path)
    if normalized.startswith(_normalize(LOCAL_SSD_PATH) + os.sep):
        return "SSD"
    if normalized == _normalize(LOCAL_SSD_PATH):
        return "SSD"
    if normalized.startswith(_normalize(LOCAL_SECONDARY_PATH) + os.sep):
        return "SECONDARY"
    if normalized == _normalize(LOCAL_SECONDARY_PATH):
        return "SECONDARY"
    return None


def _is_file_stable(path):
    try:
        stat = os.stat(path)
        age = time.time() - stat.st_mtime
        return age >= FILE_STABILITY_SECONDS
    except OSError:
        return False


def get_ssd_capacity():
    try:
        usage = shutil.disk_usage(LOCAL_SSD_PATH)
        return {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "free_mb": usage.free / (1024 * 1024),
            "used_percentage": (usage.used / usage.total) * 100,
        }
    except OSError:
        return None


def can_promote_to_ssd(file_size_bytes):
    capacity = get_ssd_capacity()
    if capacity is None:
        return False, "SSD is unavailable."

    if MAX_AUTOMATIC_PROMOTION_MB is not None:
        if file_size_bytes > MAX_AUTOMATIC_PROMOTION_MB * 1024 * 1024:
            return False, "File exceeds the automatic promotion size limit."

    reserve = SSD_MIN_FREE_MB * 1024 * 1024
    if capacity["free_bytes"] - file_size_bytes < reserve:
        return False, (
            f"Insufficient SSD capacity. Free={capacity['free_mb']:.1f} MB, "
            f"required reserve={SSD_MIN_FREE_MB} MB."
        )
    return True, "SSD capacity available."


def _record_migration(cursor, block_id, source_tier, destination_tier, temperature, reason):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
        INSERT INTO migration_history
        (block_id, source_tier, destination_tier, timestamp, temperature, reason)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (block_id, source_tier, destination_tier, timestamp, temperature, reason),
    )
    cursor.execute(
        """
        UPDATE blocks
        SET current_tier = ?,
            migration_count = migration_count + 1,
            last_migration_time = ?
        WHERE block_id = ?
        """,
        (destination_tier, timestamp, block_id),
    )


def migrate_block(block_id, destination_tier, reason="POLICY"):
    destination_tier = destination_tier.upper()
    if destination_tier not in {"SSD", "SECONDARY"}:
        return False, "Invalid destination tier."

    with _migration_lock:
        connection = get_connection()
        cursor = connection.cursor()
        moved = False
        source_file = destination_file = None
        try:
            cursor.execute(
                """
                SELECT filename, current_tier, temperature, status
                FROM blocks
                WHERE block_id = ?
                """,
                (block_id,),
            )
            block = cursor.fetchone()
            if block is None:
                return False, "Block not found."

            filename, source_tier, temperature, status = block
            source_tier = source_tier.upper()
            if status != "ACTIVE":
                return False, "Block is not active."
            if source_tier == destination_tier:
                return False, "Block is already in the requested tier."

            source_path = get_tier_path(source_tier)
            destination_path = get_tier_path(destination_tier)
            if not source_path or not destination_path:
                return False, "Storage tier path not found."
            if not os.path.exists(source_path):
                return False, f"Source tier is unavailable: {source_path}"
            if not os.path.exists(destination_path):
                if destination_tier == "SECONDARY":
                    return False, f"Secondary tier is unavailable: {destination_path}"
                os.makedirs(destination_path, exist_ok=True)

            source_file = os.path.join(source_path, filename)
            destination_file = os.path.join(destination_path, filename)

            if not os.path.isfile(source_file):
                return False, f"Physical file not found: {source_file}"
            if os.path.exists(destination_file):
                return False, f"Destination file already exists: {destination_file}"

            source_size_bytes = os.path.getsize(source_file)

            if destination_tier == "SSD":
                try:
                    size_bytes = source_size_bytes
                except OSError as error:
                    return False, f"Unable to read file size: {error}"
                capacity_ok, capacity_message = can_promote_to_ssd(size_bytes)
                if not capacity_ok:
                    return False, capacity_message

            if not _is_file_stable(source_file):
                return False, "File is still changing; migration postponed for stability."

            os.makedirs(destination_path, exist_ok=True)
            mark_migration(source_file, destination_file)
            shutil.move(source_file, destination_file)
            moved = True

            if not os.path.isfile(destination_file):
                raise IOError("Destination verification failed after migration.")

            # Basic consistency verification: source is gone and destination exists.
            destination_size = os.path.getsize(destination_file)
            if destination_size != source_size_bytes:
                raise IOError(
                    f"Migration verification failed: source was {source_size_bytes} bytes "
                    f"but destination is {destination_size} bytes."
                )

            _record_migration(
                cursor,
                block_id,
                source_tier,
                destination_tier,
                float(temperature or 0),
                reason,
            )
            connection.commit()

            return True, (
                f"Block {block_id} physically migrated from {source_tier} "
                f"to {destination_tier}. Reason: {reason}."
            )

        except Exception as error:
            connection.rollback()
            if moved and source_file and destination_file:
                try:
                    if os.path.exists(destination_file) and not os.path.exists(source_file):
                        shutil.move(destination_file, source_file)
                except Exception:
                    pass
            return False, f"Migration failed: {str(error)}"
        finally:
            connection.close()


def reconcile_physical_state():
    """
    Reconcile database tier metadata against the actual managed folders.

    If both configured roots are available, active DB rows whose files are
    absent from both roots are marked DELETED (history is preserved). If either
    root is unavailable, missing-file pruning is skipped to avoid falsely
    deleting records merely because a drive is disconnected or has a different
    drive letter on this PC.
    """
    connection = get_connection()
    cursor = connection.cursor()
    try:
        ssd_available = os.path.isdir(LOCAL_SSD_PATH)
        secondary_available = os.path.isdir(LOCAL_SECONDARY_PATH)
        can_confirm_absence = ssd_available and secondary_available

        cursor.execute(
            "SELECT block_id, filename, current_tier, status FROM blocks WHERE status = 'ACTIVE'"
        )
        blocks = cursor.fetchall()
        repaired = []
        marked_missing = []

        for block_id, filename, current_tier, status in blocks:
            ssd_file = os.path.join(LOCAL_SSD_PATH, filename)
            secondary_file = os.path.join(LOCAL_SECONDARY_PATH, filename)

            ssd_exists = ssd_available and os.path.isfile(ssd_file)
            secondary_exists = secondary_available and os.path.isfile(secondary_file)

            detected_tier = None
            if ssd_exists:
                detected_tier = "SSD"
            elif secondary_exists:
                detected_tier = "SECONDARY"

            if detected_tier:
                if detected_tier != current_tier:
                    cursor.execute(
                        "UPDATE blocks SET current_tier = ?, status = 'ACTIVE' WHERE block_id = ?",
                        (detected_tier, block_id),
                    )
                    repaired.append((block_id, current_tier, detected_tier))
                else:
                    cursor.execute(
                        "UPDATE blocks SET status = 'ACTIVE' WHERE block_id = ?",
                        (block_id,),
                    )
            elif can_confirm_absence:
                cursor.execute(
                    "UPDATE blocks SET status = 'DELETED' WHERE block_id = ?",
                    (block_id,),
                )
                marked_missing.append(block_id)
            else:
                # The file is not currently visible in either configured root.
                # If both roots are available, this is a confirmed missing file;
                # otherwise it may be on a disconnected drive. Hide it from
                # active views without deleting its history.
                cursor.execute(
                    "UPDATE blocks SET status = ? WHERE block_id = ?",
                    ("DELETED" if can_confirm_absence else "OFFLINE", block_id),
                )
                if can_confirm_absence:
                    marked_missing.append(block_id)

        connection.commit()
        if marked_missing:
            print(
                f"Startup reconciliation: marked {len(marked_missing)} stale "
                "database block(s) DELETED because their files are absent "
                "from both configured storage roots."
            )
        return repaired
    finally:
        connection.close()
