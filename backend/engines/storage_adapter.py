"""
SmartCloud Optimizer — Storage Monitoring and Provider Adapter Interface
========================================================================
Collects real local filesystem storage telemetry using psutil and defines
the abstract provider adapter contract for cloud block storage volume expansion
(AWS EBS, GCP Persistent Disk, Azure Managed Disks).

Safety Guarantees:
- Never shrinks a disk or volume automatically (cloud block storage volumes
  cannot be shrunk without severe filesystem corruption risk).
- Never modifies or expands host root filesystem/partitions on the local machine.
- When cloud provider credentials or safe test volumes are not configured,
  explicitly marks resizing capability as 'NOT CONFIGURED'.
"""
import os
import psutil
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict


@dataclass
class StorageTelemetry:
    mount_point: str
    filesystem_type: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent_used: float
    status: str
    timestamp: str
    collection_source: str = "Host psutil.disk_usage"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class StorageResizeAdapter:
    """
    Abstract contract for cloud infrastructure block volume storage expansion.
    Real-world implementations require:
    1. Provider credentials (AWS IAM role/keys, GCP service account, Azure SPN).
    2. Cloud Volume ID (e.g. vol-0a1b2c3d4e5f, pd-standard-01).
    3. Filesystem resize daemon / cloud-init support (e.g. growpart + resize2fs/xfs_growfs).
    4. Minimum step size (e.g. +10 GB or +20%) with rate-limiting (e.g. AWS 6h cooldown per volume).
    """

    def get_status(self) -> Dict[str, Any]:
        raise NotImplementedError

    def can_expand(self, volume_id: str) -> Tuple[bool, str]:
        raise NotImplementedError

    def request_expansion(self, volume_id: str, target_size_gb: float) -> Tuple[bool, Dict[str, Any], str]:
        raise NotImplementedError


class LocalHostStorageCollector(StorageResizeAdapter):
    """
    Collects real filesystem storage telemetry for the local host.
    Explicitly declares cloud resizing as NOT CONFIGURED to prevent any unsafe
    modifications to the local system partitions.
    """

    def __init__(self, mount_point: str = "/"):
        self.mount_point = mount_point

    def collect_telemetry(self) -> StorageTelemetry:
        """Collect live filesystem disk telemetry using psutil."""
        try:
            usage = psutil.disk_usage(self.mount_point)
            total_gb = round(usage.total / (1024 ** 3), 2)
            used_gb = round(usage.used / (1024 ** 3), 2)
            free_gb = round(usage.free / (1024 ** 3), 2)
            percent = round(usage.percent, 1)

            # Detect filesystem type if available
            fstype = "ext4"
            for part in psutil.disk_partitions(all=False):
                if part.mountpoint == self.mount_point:
                    fstype = part.fstype
                    break

            return StorageTelemetry(
                mount_point=self.mount_point,
                filesystem_type=fstype,
                total_gb=total_gb,
                used_gb=used_gb,
                free_gb=free_gb,
                percent_used=percent,
                status="healthy",
                timestamp=datetime.now(timezone.utc).isoformat(),
                collection_source="Live local filesystem metrics (psutil)",
            )
        except Exception as e:
            return StorageTelemetry(
                mount_point=self.mount_point,
                filesystem_type="unknown",
                total_gb=0.0,
                used_gb=0.0,
                free_gb=0.0,
                percent_used=0.0,
                status=f"error: {str(e)}",
                timestamp=datetime.now(timezone.utc).isoformat(),
                collection_source="Live local filesystem metrics (psutil)",
            )

    def get_status(self) -> Dict[str, Any]:
        """
        Returns real filesystem metrics accompanied by an honest declaration
        that storage autoscaling/expansion is NOT CONFIGURED for the local demo.
        """
        telemetry = self.collect_telemetry()
        return {
            "telemetry": telemetry.to_dict(),
            "resizing_capability": {
                "status": "NOT_CONFIGURED",
                "can_auto_expand": False,
                "can_shrink": False,
                "reason": (
                    "Storage resizing requires cloud provider block volume integration (AWS EBS, "
                    "GCP Persistent Disk, or Azure Managed Disks) with authorized cloud IAM credentials. "
                    "Local host disk expansion is deliberately disabled to prevent unsafe modification "
                    "or partition resizing of the host operating system."
                ),
                "supported_cloud_providers": ["AWS EBS (ModifyVolume)", "GCP PD (resize)", "Azure Managed Disk"],
                "safety_constraints": [
                    "Block volume shrinking is technically unsupported and dangerous",
                    "Expansion requires filesystem-level resize2fs or xfs_growfs invocation",
                    "Cooldown periods apply (e.g. AWS enforces 6-hour modification lock)",
                ],
            },
        }

    def can_expand(self, volume_id: str) -> Tuple[bool, str]:
        return False, "Storage expansion is NOT CONFIGURED: No cloud provider API connected."

    def request_expansion(self, volume_id: str, target_size_gb: float) -> Tuple[bool, Dict[str, Any], str]:
        return False, {}, "Refused: Storage expansion is NOT CONFIGURED in local demonstration mode."
