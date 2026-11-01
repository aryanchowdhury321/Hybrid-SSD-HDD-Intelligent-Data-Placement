import os
import sqlite3
from datetime import datetime

from config import DATABASE_PATH, DATA_DIR


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _add_column_if_missing(cursor, table_name, column_name, definition):
    columns = {
        row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def initialize_database():
    os.makedirs(DATA_DIR, exist_ok=True)

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blocks (
            block_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            size_kb REAL NOT NULL,
            current_tier TEXT NOT NULL,
            access_count INTEGER DEFAULT 0,
            read_count INTEGER DEFAULT 0,
            write_count INTEGER DEFAULT 0,
            last_access_time TEXT,
            temperature REAL DEFAULT 0,
            migration_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'ACTIVE',
            created_time TEXT,
            last_temperature_update TEXT,
            last_migration_time TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS access_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_id TEXT NOT NULL,
            operation TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS migration_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            block_id TEXT NOT NULL,
            source_tier TEXT NOT NULL,
            destination_tier TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            temperature REAL DEFAULT 0,
            reason TEXT DEFAULT 'POLICY'
        )
    """)

    # Upgrade databases created by older versions without destroying data.
    _add_column_if_missing(cursor, "blocks", "status", "TEXT DEFAULT 'ACTIVE'")
    _add_column_if_missing(cursor, "blocks", "created_time", "TEXT")
    _add_column_if_missing(cursor, "blocks", "last_temperature_update", "TEXT")
    _add_column_if_missing(cursor, "blocks", "last_migration_time", "TEXT")
    _add_column_if_missing(cursor, "migration_history", "temperature", "REAL DEFAULT 0")
    _add_column_if_missing(cursor, "migration_history", "reason", "TEXT DEFAULT 'POLICY'")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "UPDATE blocks SET status = COALESCE(status, 'ACTIVE')"
    )
    cursor.execute(
        "UPDATE blocks SET created_time = COALESCE(created_time, ?)"
        , (now,)
    )
    cursor.execute(
        """
        UPDATE migration_history
        SET reason = 'LEGACY'
        WHERE reason IS NULL OR (reason = 'POLICY' AND COALESCE(temperature, 0) = 0)
        """
    )

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_access_block_time ON access_history(block_id, timestamp)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_blocks_tier_status ON blocks(current_tier, status)")

    connection.commit()
    connection.close()


def register_block(block_id, filename, size_kb, current_tier="SECONDARY"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            INSERT INTO blocks
            (
                block_id, filename, size_kb, current_tier,
                access_count, read_count, write_count,
                temperature, migration_count, status, created_time
            )
            VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 'ACTIVE', ?)
        """, (block_id, filename, size_kb, current_tier.upper(), timestamp))
        connection.commit()
        return True, "Block registered successfully."
    except sqlite3.IntegrityError:
        connection.rollback()
        return False, "Block ID already exists."
    finally:
        connection.close()


def get_next_block_id():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT block_id FROM blocks WHERE block_id LIKE 'B%'")
    rows = cursor.fetchall()
    connection.close()

    highest_number = 0
    for (block_id,) in rows:
        try:
            highest_number = max(highest_number, int(block_id[1:]))
        except (ValueError, TypeError):
            continue
    return f"B{highest_number + 1:03d}"


def _block_select_sql(include_deleted=False):
    status_clause = "" if include_deleted else "AND status = 'ACTIVE'"
    return f"""
        SELECT
            block_id, filename, size_kb, current_tier,
            access_count, read_count, write_count,
            last_access_time, temperature, migration_count,
            status, created_time, last_temperature_update,
            last_migration_time
        FROM blocks
        WHERE filename = ? {status_clause}
        ORDER BY block_id
        LIMIT 1
    """


def get_block_by_filename(filename, include_deleted=False):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(_block_select_sql(include_deleted), (filename,))
    block = cursor.fetchone()
    connection.close()
    return block


def get_block_by_filename_and_tier(filename, tier, include_deleted=False):
    """Find a block using both its filename and physical tier."""
    connection = get_connection()
    cursor = connection.cursor()
    status_clause = "" if include_deleted else "AND status = 'ACTIVE'"
    try:
        cursor.execute(f"""
            SELECT
                block_id, filename, size_kb, current_tier,
                access_count, read_count, write_count,
                last_access_time, temperature, migration_count,
                status, created_time, last_temperature_update,
                last_migration_time
            FROM blocks
            WHERE filename = ? AND current_tier = ? {status_clause}
            ORDER BY block_id
            LIMIT 1
        """, (filename, tier.upper()))
        return cursor.fetchone()
    finally:
        connection.close()


def get_block_by_id(block_id):
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT
            block_id, filename, size_kb, current_tier,
            access_count, read_count, write_count,
            last_access_time, temperature, migration_count,
            status, created_time, last_temperature_update,
            last_migration_time
        FROM blocks
        WHERE block_id = ?
    """, (block_id,))
    block = cursor.fetchone()
    connection.close()
    return block


def register_file_if_needed(file_path, current_tier="SECONDARY"):
    filename = os.path.basename(file_path)
    existing_block = get_block_by_filename(filename, include_deleted=True)

    try:
        file_size_bytes = os.path.getsize(file_path)
        size_kb = round(file_size_bytes / 1024, 2)
    except OSError:
        size_kb = 0

    if existing_block is not None:
        block_id = existing_block[0]
        connection = get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                UPDATE blocks
                SET size_kb = ?, current_tier = ?, status = 'ACTIVE'
                WHERE block_id = ?
            """, (size_kb, current_tier.upper(), block_id))
            connection.commit()
            return True, block_id, "File already registered; metadata refreshed."
        finally:
            connection.close()

    block_id = get_next_block_id()
    success, message = register_block(block_id, filename, size_kb, current_tier)
    if success:
        return True, block_id, f"New file registered as {block_id}."
    return False, None, message


def update_filename(block_id, new_filename):
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE blocks SET filename = ?, status = 'ACTIVE' WHERE block_id = ?",
            (new_filename, block_id),
        )
        if cursor.rowcount == 0:
            connection.rollback()
            return False, "Block not found."
        connection.commit()
        return True, "Filename updated successfully."
    except sqlite3.IntegrityError:
        connection.rollback()
        return False, "Filename already exists."
    finally:
        connection.close()


def mark_block_deleted(block_id):
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute(
            "UPDATE blocks SET status = 'DELETED' WHERE block_id = ?",
            (block_id,),
        )
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def update_block_temperature(block_id, temperature):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    connection = get_connection()
    cursor = connection.cursor()
    try:
        cursor.execute("""
            UPDATE blocks
            SET temperature = ?, last_temperature_update = ?
            WHERE block_id = ?
        """, (temperature, timestamp, block_id))
        connection.commit()
        return cursor.rowcount > 0
    finally:
        connection.close()


def get_all_blocks(include_deleted=False):
    connection = get_connection()
    cursor = connection.cursor()
    status_clause = "" if include_deleted else "WHERE status = 'ACTIVE'"
    cursor.execute(f"""
        SELECT
            block_id, filename, size_kb, current_tier,
            access_count, read_count, write_count,
            last_access_time, temperature, migration_count,
            status, created_time, last_temperature_update,
            last_migration_time
        FROM blocks
        {status_clause}
        ORDER BY block_id
    """)
    blocks = cursor.fetchall()
    connection.close()
    return blocks


def get_active_block_ids():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT block_id FROM blocks WHERE status = 'ACTIVE' ORDER BY block_id")
    ids = [row[0] for row in cursor.fetchall()]
    connection.close()
    return ids


def get_system_statistics():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("SELECT COUNT(*) FROM blocks WHERE status = 'ACTIVE'")
    total_blocks = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM blocks WHERE status = 'ACTIVE' AND current_tier = 'SSD'")
    ssd_blocks = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM blocks WHERE status = 'ACTIVE' AND current_tier = 'SECONDARY'")
    secondary_blocks = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM blocks WHERE status = 'ACTIVE' AND temperature >= 70")
    hot_blocks = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM blocks WHERE status = 'ACTIVE' AND temperature >= 40 AND temperature < 70")
    warm_blocks = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM blocks WHERE status = 'ACTIVE' AND temperature < 40")
    cold_blocks = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM migration_history WHERE destination_tier = 'SSD'")
    promotions = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM migration_history WHERE destination_tier = 'SECONDARY'")
    demotions = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM migration_history")
    total_migrations = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(AVG(temperature), 0) FROM blocks WHERE status = 'ACTIVE'")
    average_temperature = round(cursor.fetchone()[0], 1)
    connection.close()
    return {
        "total_blocks": total_blocks,
        "ssd_blocks": ssd_blocks,
        "secondary_blocks": secondary_blocks,
        "hot_blocks": hot_blocks,
        "warm_blocks": warm_blocks,
        "cold_blocks": cold_blocks,
        "promotions": promotions,
        "demotions": demotions,
        "total_migrations": total_migrations,
        "average_temperature": average_temperature,
    }


def get_migration_history():
    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute("""
        SELECT block_id, source_tier, destination_tier,
               temperature, reason, timestamp
        FROM migration_history
        ORDER BY id DESC
    """)
    migrations = cursor.fetchall()
    connection.close()
    return migrations


def get_access_history(block_id, limit=None):
    connection = get_connection()
    cursor = connection.cursor()
    query = """
        SELECT operation, timestamp
        FROM access_history
        WHERE block_id = ?
        ORDER BY id DESC
    """
    params = [block_id]
    if limit is not None:
        query += " LIMIT ?"
        params.append(int(limit))
    cursor.execute(query, params)
    rows = cursor.fetchall()
    connection.close()
    return rows


def discover_managed_files(tier_paths):
    """Discover existing files after startup without registering anything outside managed roots."""
    discovered = []
    for tier, root in tier_paths:
        if not os.path.isdir(root):
            continue
        for current_root, _, filenames in os.walk(root):
            for filename in filenames:
                path = os.path.join(current_root, filename)
                try:
                    success, block_id, message = register_file_if_needed(path, tier)
                    if success:
                        discovered.append((block_id, filename, tier, message))
                except OSError:
                    continue
    return discovered
