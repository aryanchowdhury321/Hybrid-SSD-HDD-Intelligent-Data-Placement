from engine.access_monitor import record_access
from engine.migration_engine import migrate_block
from engine.placement_engine import get_block_placement
from engine.temperature_engine import get_temperature_label, update_block_temperature


def process_access(block_id, operation):
    operation = operation.upper()
    if operation not in {"READ", "WRITE"}:
        return False, {"message": "Invalid operation. Use READ or WRITE."}

    success, message = record_access(block_id, operation)
    if not success:
        return False, {"message": message}

    temperature_success, temperature_data = update_block_temperature(block_id)
    if not temperature_success:
        return False, {"message": temperature_data}

    placement_success, placement_data = get_block_placement(block_id)
    if not placement_success:
        return False, {"message": placement_data}

    current_tier = placement_data["current_tier"]
    recommended_tier = placement_data["recommended_tier"]
    temperature = placement_data["temperature"]
    migration_message = "No migration required."

    if current_tier != recommended_tier:
        migration_success, migration_message = migrate_block(
            block_id,
            recommended_tier,
            reason=f"ACCESS_TRIGGERED_{operation}",
        )
        if not migration_success:
            # The access itself succeeded; report the placement issue without
            # pretending that the file moved.
            migration_message = f"Migration postponed: {migration_message}"

    # Read the actual current tier after a possible migration.
    from database import get_block_by_id
    refreshed = get_block_by_id(block_id)
    actual_tier = refreshed[3] if refreshed else current_tier

    return True, {
        "block_id": block_id,
        "operation": operation,
        "temperature": temperature,
        "label": get_temperature_label(temperature),
        "current_tier": actual_tier,
        "recommended_tier": recommended_tier,
        "migration": migration_message,
    }
