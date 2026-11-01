import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# -----------------------------------------------------------------------------
# REAL STORAGE TIERS
# These folders must exist on the actual physical drives.
# -----------------------------------------------------------------------------
LOCAL_SSD_PATH = r"C:\HybridStorageSSD"
LOCAL_SECONDARY_PATH = r"E:\HybridStorageHDD"

# -----------------------------------------------------------------------------
# HEAT / TEMPERATURE POLICY
# Temperature is a logical DATA-HEAT score from 0 to 100, not Celsius.
# -----------------------------------------------------------------------------
HOT_THRESHOLD = 70
WARM_THRESHOLD = 40

# A lower threshold is used when demoting SSD data. This hysteresis prevents
# repeated SSD <-> HDD movement when a file sits around the HOT boundary.
SSD_DEMOTION_THRESHOLD = 25

# One access loses half of its heat contribution after this time.
HEAT_HALF_LIFE_SECONDS = 600       # 10 minutes
READ_HEAT_WEIGHT = 1.0
WRITE_HEAT_WEIGHT = 1.5
HEAT_SCALE = 15.0

# -----------------------------------------------------------------------------
# AUTOMATIC OPTIMIZATION
# -----------------------------------------------------------------------------
OPTIMIZATION_INTERVAL_SECONDS = 60
MIGRATION_GUARD_SECONDS = 8
FILE_STABILITY_SECONDS = 2.0

# Keep a safety reserve on the SSD instead of consuming its last free space.
SSD_MIN_FREE_MB = 512

# Do not migrate files above this size automatically unless the SSD has enough
# free capacity after the safety reserve. Set to None for no per-file limit.
MAX_AUTOMATIC_PROMOTION_MB = None

# -----------------------------------------------------------------------------
# OPTIONAL DISPLAY / MODEL LATENCIES
# These are illustrative tier characteristics for the project UI/model only;
# actual latency depends on the user's hardware and workload.
# -----------------------------------------------------------------------------
SSD_READ_LATENCY_MS = 1
SSD_WRITE_LATENCY_MS = 2
SECONDARY_READ_LATENCY_MS = 10
SECONDARY_WRITE_LATENCY_MS = 15

DATABASE_PATH = os.path.join(DATA_DIR, "hybrid_storage.db")
