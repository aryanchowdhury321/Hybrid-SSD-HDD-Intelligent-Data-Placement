from datetime import datetime


class Block:
    """Logical file/block metadata used by the hybrid storage model."""

    def __init__(self, block_id, filename, size_kb, current_tier="SECONDARY"):
        self.block_id = block_id
        self.filename = filename
        self.size_kb = size_kb
        self.current_tier = current_tier
        self.access_count = 0
        self.read_count = 0
        self.write_count = 0
        self.last_access_time = None
        self.temperature = 0.0
        self.migration_count = 0
        self.status = "ACTIVE"

    def record_access(self, operation):
        operation = operation.upper()
        if operation not in {"READ", "WRITE"}:
            return False
        self.access_count += 1
        self.last_access_time = datetime.now()
        if operation == "READ":
            self.read_count += 1
        else:
            self.write_count += 1
        return True

    def update_temperature(self, temperature):
        self.temperature = float(temperature)

    def get_info(self):
        return {
            "block_id": self.block_id,
            "filename": self.filename,
            "size_kb": self.size_kb,
            "current_tier": self.current_tier,
            "access_count": self.access_count,
            "read_count": self.read_count,
            "write_count": self.write_count,
            "last_access_time": self.last_access_time,
            "temperature": self.temperature,
            "migration_count": self.migration_count,
            "status": self.status,
        }
