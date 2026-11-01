"""Automatic, capacity-aware storage tier optimization."""

from config import HOT_THRESHOLD, SSD_DEMOTION_THRESHOLD, SSD_MIN_FREE_MB
from database import get_all_blocks
from engine.migration_engine import (
    can_promote_to_ssd,
    get_ssd_capacity,
    migrate_block,
)
from engine.placement_engine import decide_placement
from engine.temperature_engine import refresh_all_temperatures


def _file_size_bytes(block):
    try:
        return max(0, int(float(block[2]) * 1024))
    except (TypeError, ValueError):
        return 0


def ensure_ssd_capacity(required_bytes, exclude_block_id=None):
    """Free SSD capacity by demoting the coldest eligible SSD files."""
    capacity = get_ssd_capacity()
    if capacity is None:
        return False, "SSD is unavailable."

    reserve = SSD_MIN_FREE_MB * 1024 * 1024
    if capacity["free_bytes"] - required_bytes >= reserve:
        return True, "SSD capacity available."

    candidates = []
    for block in get_all_blocks():
        block_id, filename, size_kb, tier, *_ = block
        temperature = float(block[8] or 0)
        if block_id == exclude_block_id or tier != "SSD":
            continue
        if temperature <= SSD_DEMOTION_THRESHOLD:
            candidates.append((temperature, block_id, filename, _file_size_bytes(block)))

    candidates.sort(key=lambda item: (item[0], -item[3]))

    for _, block_id, _, _ in candidates:
        success, _ = migrate_block(
            block_id,
            "SECONDARY",
            reason="SSD_CAPACITY_EVICTION",
        )
        if success:
            capacity = get_ssd_capacity()
            if capacity and capacity["free_bytes"] - required_bytes >= reserve:
                return True, "SSD capacity freed by demoting cold data."

    return False, "Not enough SSD capacity and no eligible cold data could be evicted."


def optimize_block(block_id, reason="AUTOMATIC_POLICY"):
    """Evaluate one block and migrate only when policy requires it."""
    blocks = {row[0]: row for row in get_all_blocks()}
    block = blocks.get(block_id)
    if block is None:
        return False, "Block not found or inactive."

    current_tier = block[3]
    temperature = float(block[8] or 0)
    target = decide_placement(temperature, current_tier)

    if target == current_tier:
        return True, "No migration required."

    if target == "SSD":
        required_bytes = _file_size_bytes(block)
        ok, message = can_promote_to_ssd(required_bytes)
        if not ok:
            ok, message = ensure_ssd_capacity(required_bytes, exclude_block_id=block_id)
            if not ok:
                return False, message

    return migrate_block(block_id, target, reason=reason)


def run_optimization_cycle():
    """
    Refresh all temperatures, demote cold SSD data, then promote hot HDD data.

    Demotions happen first so a full SSD can make room for hot data.
    """
    temperature_results = refresh_all_temperatures()
    blocks = get_all_blocks()
    actions = []

    # First remove genuinely cold data from SSD.
    demotions = [
        row for row in blocks
        if row[3] == "SSD" and float(row[8] or 0) <= SSD_DEMOTION_THRESHOLD
    ]
    demotions.sort(key=lambda row: float(row[8] or 0))

    for block in demotions:
        success, message = migrate_block(
            block[0],
            "SECONDARY",
            reason="TEMPERATURE_COOL_DOWN",
        )
        if success:
            actions.append({"block_id": block[0], "action": "DEMOTION", "message": message})

    # Then promote HOT secondary data, hottest first.
    promotions = [
        row for row in get_all_blocks()
        if row[3] == "SECONDARY" and float(row[8] or 0) >= HOT_THRESHOLD
    ]
    promotions.sort(key=lambda row: float(row[8] or 0), reverse=True)

    for block in promotions:
        success, message = optimize_block(
            block[0],
            reason="TEMPERATURE_HOT",
        )
        if success and "migrated" in message.lower():
            actions.append({"block_id": block[0], "action": "PROMOTION", "message": message})

    return {
        "temperatures_refreshed": len(temperature_results),
        "migrations": actions,
        "ssd_capacity": get_ssd_capacity(),
    }
