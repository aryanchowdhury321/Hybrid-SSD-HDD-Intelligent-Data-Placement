import os
import shutil
import psutil


def get_drive_info(path):
    try:
        usage = shutil.disk_usage(path)

        return {
            "path": path,
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_gb": round(usage.used / (1024 ** 3), 2),
            "free_gb": round(usage.free / (1024 ** 3), 2),
            "used_percentage": round((usage.used / usage.total) * 100, 1)
        }

    except Exception:
        return None


def get_external_drives():
    drives = []

    for partition in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(partition.mountpoint)

            if partition.fstype:
                drives.append({
                    "drive": partition.mountpoint,
                    "file_system": partition.fstype,
                    "total_gb": round(usage.total / (1024 ** 3), 2),
                    "used_gb": round(usage.used / (1024 ** 3), 2),
                    "free_gb": round(usage.free / (1024 ** 3), 2),
                    "used_percentage": round(usage.percent, 1)
                })

        except PermissionError:
            continue

    return drives


def is_drive_available(path):
    return os.path.exists(path)