"""Command-line diagnostics for the Hybrid Storage Management System."""

import os

from config import LOCAL_SECONDARY_PATH, LOCAL_SSD_PATH
from database import get_system_statistics, initialize_database
from storage.device_manager import get_drive_info


def main():
    initialize_database()
    print("=" * 60)
    print("HYBRID STORAGE SYSTEM DIAGNOSTICS")
    print("=" * 60)

    for name, path in (("SSD", LOCAL_SSD_PATH), ("SECONDARY", LOCAL_SECONDARY_PATH)):
        info = get_drive_info(path)
        print(f"{name:10}: {path}")
        print(f"  Available : {'YES' if os.path.exists(path) else 'NO'}")
        if info:
            print(f"  Total GB  : {info['total_gb']}")
            print(f"  Free GB   : {info['free_gb']}")
            print(f"  Used      : {info['used_percentage']}%")

    stats = get_system_statistics()
    print("\nDATABASE")
    for key, value in stats.items():
        print(f"  {key:18}: {value}")

    print("\nPolicy: HOT >= 70, SSD demotion <= 25, heat half-life = 10 minutes")
    print("Automatic optimizer: every 10 seconds while the GUI is running.")


if __name__ == "__main__":
    main()
