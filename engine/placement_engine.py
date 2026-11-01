from config import HOT_THRESHOLD, SSD_DEMOTION_THRESHOLD
from engine.temperature_engine import get_temperature_label


def decide_placement(temperature, current_tier="SECONDARY"):
    """
    Choose a tier using asymmetric thresholds (hysteresis).

    SECONDARY -> SSD only when data becomes HOT.
    SSD -> SECONDARY only when data becomes genuinely COLD.
    WARM data keeps its current tier, preventing migration thrashing.
    """
    current_tier = current_tier.upper()

    if current_tier == "SECONDARY":
        return "SSD" if temperature >= HOT_THRESHOLD else "SECONDARY"

    if current_tier == "SSD":
        return "SECONDARY" if temperature <= SSD_DEMOTION_THRESHOLD else "SSD"

    return "SECONDARY"


def get_block_placement(block_id):
    from database import get_connection

    connection = get_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        SELECT temperature, current_tier, status
        FROM blocks
        WHERE block_id = ?
        """,
        (block_id,),
    )
    block = cursor.fetchone()
    connection.close()

    if block is None:
        return False, "Block not found."

    temperature, current_tier, status = block
    if status != "ACTIVE":
        return False, "Block is not active."

    recommended_tier = decide_placement(temperature, current_tier)
    return True, {
        "block_id": block_id,
        "current_tier": current_tier,
        "recommended_tier": recommended_tier,
        "temperature": temperature,
        "label": get_temperature_label(temperature),
    }
