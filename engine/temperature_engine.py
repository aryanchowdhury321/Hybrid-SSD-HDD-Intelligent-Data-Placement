import math
from datetime import datetime, timedelta

from config import (
    HEAT_HALF_LIFE_SECONDS,
    HEAT_SCALE,
    HOT_THRESHOLD,
    READ_HEAT_WEIGHT,
    WARM_THRESHOLD,
    WRITE_HEAT_WEIGHT,
)


TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


def _parse_timestamp(value):
    try:
        return datetime.strptime(value, TIMESTAMP_FORMAT)
    except (TypeError, ValueError):
        return None


def calculate_temperature(access_history, now=None):
    """
    Calculate logical data heat from timestamped access history.

    Each access contributes according to its operation weight and an
    exponential recency-decay function.  The half-life means that an
    access contributes half as much heat after HEAT_HALF_LIFE_SECONDS.

    This is a logical workload score (0-100), not physical temperature.
    """
    now = now or datetime.now()
    heat_score = 0.0

    for operation, timestamp_text in access_history:
        access_time = _parse_timestamp(timestamp_text)
        if access_time is None:
            continue

        age_seconds = max(0.0, (now - access_time).total_seconds())
        decay = math.pow(0.5, age_seconds / HEAT_HALF_LIFE_SECONDS)

        operation = str(operation).upper()
        if operation == "WRITE":
            weight = WRITE_HEAT_WEIGHT
        elif operation == "READ":
            weight = READ_HEAT_WEIGHT
        else:
            continue

        heat_score += weight * decay

    temperature = min(100.0, heat_score * HEAT_SCALE)
    return round(temperature, 1)


def get_temperature_label(temperature):
    if temperature >= HOT_THRESHOLD:
        return "HOT"
    if temperature >= WARM_THRESHOLD:
        return "WARM"
    return "COLD"


def get_heat_explanation(access_history, now=None):
    """Return an explainable summary useful for the GUI/review demo."""
    now = now or datetime.now()
    reads = writes = 0
    recent_reads = recent_writes = 0

    for operation, timestamp_text in access_history:
        access_time = _parse_timestamp(timestamp_text)
        if access_time is None:
            continue
        age = max(0.0, (now - access_time).total_seconds())
        if str(operation).upper() == "READ":
            reads += 1
            if age <= HEAT_HALF_LIFE_SECONDS:
                recent_reads += 1
        elif str(operation).upper() == "WRITE":
            writes += 1
            if age <= HEAT_HALF_LIFE_SECONDS:
                recent_writes += 1

    return {
        "reads_considered": reads,
        "writes_considered": writes,
        "recent_reads": recent_reads,
        "recent_writes": recent_writes,
        "half_life_minutes": round(HEAT_HALF_LIFE_SECONDS / 60, 1),
    }


def update_block_temperature(block_id, connection=None):
    """Recalculate one block using only recent access history."""
    owns_connection = connection is None
    if owns_connection:
        from database import get_connection
        connection = get_connection()

    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT block_id, status FROM blocks WHERE block_id = ?",
            (block_id,),
        )
        block = cursor.fetchone()
        if block is None:
            return False, "Block not found."

        cutoff = datetime.now() - timedelta(seconds=HEAT_HALF_LIFE_SECONDS * 8)
        cutoff_text = cutoff.strftime(TIMESTAMP_FORMAT)

        cursor.execute(
            """
            SELECT operation, timestamp
            FROM access_history
            WHERE block_id = ? AND timestamp >= ?
            ORDER BY id DESC
            """,
            (block_id, cutoff_text),
        )
        history = cursor.fetchall()
        temperature = calculate_temperature(history)
        label = get_temperature_label(temperature)
        timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)

        cursor.execute(
            """
            UPDATE blocks
            SET temperature = ?, last_temperature_update = ?
            WHERE block_id = ?
            """,
            (temperature, timestamp, block_id),
        )

        if owns_connection:
            connection.commit()

        return True, {
            "block_id": block_id,
            "temperature": temperature,
            "label": label,
            "history_events_considered": len(history),
        }
    finally:
        if owns_connection:
            connection.close()


def refresh_all_temperatures():
    """Recalculate every active block so heat naturally cools over time."""
    from database import get_connection

    connection = get_connection()
    try:
        cursor = connection.cursor()
        cursor.execute("SELECT block_id FROM blocks WHERE status = 'ACTIVE'")
        block_ids = [row[0] for row in cursor.fetchall()]
        results = []
        for block_id in block_ids:
            success, result = update_block_temperature(block_id, connection)
            if success:
                results.append(result)
        connection.commit()
        return results
    finally:
        connection.close()
