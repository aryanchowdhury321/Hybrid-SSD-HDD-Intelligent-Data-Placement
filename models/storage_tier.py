class StorageTier:
    """Describes a storage tier; capacity is informational when real paths are used."""

    def __init__(self, name, path, capacity_mb=None, read_latency_ms=None, write_latency_ms=None):
        self.name = name
        self.path = path
        self.capacity_mb = capacity_mb
        self.read_latency_ms = read_latency_ms
        self.write_latency_ms = write_latency_ms

    def get_info(self):
        return {
            "name": self.name,
            "path": self.path,
            "capacity_mb": self.capacity_mb,
            "read_latency_ms": self.read_latency_ms,
            "write_latency_ms": self.write_latency_ms,
        }
