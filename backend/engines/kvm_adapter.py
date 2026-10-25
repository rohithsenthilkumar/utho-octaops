"""
SmartCloud Optimizer — Stage 9A: KVM/QEMU & Libvirt VM Management Adapter
========================================================================
Provides secure, bounded inspection and vertical capacity management of real local
libvirt virtual machines on the Kali Linux host.

Safety and Architectural Principles:
1. Fixed-argument command execution without shell interpolation (zero command injection risk).
2. Explicit domain allowlist: only authorized test VMs can be modified. Protected domains,
   hypervisor host, and Docker workloads are strictly rejected.
3. Host capacity safeguarding: refuses resizing if host RAM or CPU headroom is insufficient.
4. Independent verification: reads allocation directly from hypervisor state post-operation.
5. Zero unplanned downtime: never shuts down a running guest automatically; returns REQUIRES_SHUTDOWN
   with explicit downtime requirements when live hotplug is unsupported.
"""
import os
import re
import shutil
import subprocess
import json
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone
import psutil

# Safe domain identifier pattern (alphanumeric, dashes, underscores)
DOMAIN_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.]{1,64}$")
UUID_REGEX = re.compile(r"^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$")

# Authorized test domains allowlist for local management
DEFAULT_ALLOWED_TEST_VMS = {
    "smartcloud-test-vm",
    "smartcloud-kvm-test-01",
    "demo-kvm-vm-01",
    "test-kvm-guest",
    "sco-test-vm",
}

# Protected system identifiers that can never be modified
PROTECTED_DOMAINS = {
    "host",
    "localhost",
    "kali",
    "root",
    "dom0",
    "system",
    "template",
}

# Standard FinOps pricing baseline for real KVM VMs (INR/month)
# Consistent with rightsizing engine and Docker vertical scaler: ₹800/vCPU + ₹200/GB RAM
def estimate_vm_monthly_cost(vcpu: float, memory_gb: float) -> float:
    return round((vcpu * 800.0) + (memory_gb * 200.0), 2)


class KvmLibvirtAdapter:
    """
    Dedicated local KVM/QEMU libvirt adapter.
    Operates via virsh CLI with fixed argument lists and rigorous validation.
    Supports a mock mode for non-privileged test execution and environments without libvirtd.
    """

    def __init__(
        self,
        uri: str = "qemu:///system",
        virsh_path: Optional[str] = None,
        kvm_device_path: str = "/dev/kvm",
        safety_headroom_ram_gb: float = 2.0,
        allowed_test_vms: Optional[set] = None,
    ):
        self.uri = uri
        self.virsh_path = virsh_path or shutil.which("virsh")
        self.kvm_device_path = kvm_device_path
        self.safety_headroom_ram_gb = safety_headroom_ram_gb
        self.allowed_test_vms = set(allowed_test_vms) if allowed_test_vms else set(DEFAULT_ALLOWED_TEST_VMS)
        self._mock_mode = False
        self._mock_domains: Dict[str, Dict[str, Any]] = {}

    # -------------------------------------------------------------------------
    # Environment & Host Capability Checks
    # -------------------------------------------------------------------------

    def check_hypervisor_status(self) -> Dict[str, Any]:
        """
        Inspect local host virtualization capabilities, /dev/kvm presence,
        libvirt availability, and host CPU/RAM capacity.
        """
        kvm_exists = os.path.exists(self.kvm_device_path)
        kvm_readable = os.access(self.kvm_device_path, os.R_OK) if kvm_exists else False
        kvm_writable = os.access(self.kvm_device_path, os.W_OK) if kvm_exists else False

        # Check virsh binary
        virsh_available = bool(self.virsh_path and os.path.exists(self.virsh_path))

        # Check virsh connection if binary exists
        libvirt_connected = False
        virsh_version = None
        virsh_error = None

        if virsh_available:
            try:
                proc = subprocess.run(
                    [self.virsh_path, "-c", self.uri, "version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if proc.returncode == 0:
                    libvirt_connected = True
                    for line in proc.stdout.splitlines():
                        if "libvirt" in line.lower() or "compiled against" in line.lower():
                            virsh_version = line.strip()
                            break
                    if not virsh_version and proc.stdout:
                        virsh_version = proc.stdout.splitlines()[0].strip()
                else:
                    virsh_error = proc.stderr.strip() or "Connection refused by libvirt daemon"
            except Exception as e:
                virsh_error = str(e)

        # Host memory and CPU headroom
        vm_mem = psutil.virtual_memory()
        host_total_ram_gb = round(vm_mem.total / (1024 ** 3), 2)
        host_available_ram_gb = round(vm_mem.available / (1024 ** 3), 2)
        host_cpu_cores = psutil.cpu_count(logical=True) or 1

        # Calculate safe assignable VM headroom
        safe_allocatable_ram_gb = max(0.0, round(host_available_ram_gb - self.safety_headroom_ram_gb, 2))

        status_code = "READY"
        details_msg = "Hypervisor ready and active."
        if not kvm_exists:
            status_code = "KVM_DEVICE_MISSING"
            details_msg = f"KVM device node '{self.kvm_device_path}' is missing on host."
        elif not kvm_writable:
            status_code = "KVM_PERMISSION_DENIED"
            details_msg = f"Insufficient permissions to write to '{self.kvm_device_path}'. User must be in kvm group."
        elif not virsh_available:
            status_code = "VIRSH_NOT_INSTALLED"
            details_msg = "The 'virsh' binary is not installed on host. Run 'sudo apt install qemu-system-x86 libvirt-clients'."
        elif not libvirt_connected:
            status_code = "LIBVIRT_DAEMON_INACTIVE"
            details_msg = f"Cannot connect to libvirt daemon via '{self.uri}'. Virsh error: {virsh_error}"

        instructions = (
            "To enable local libvirt VM management on Kali Linux, install the virtualization stack:\n"
            "sudo apt update && sudo apt install -y qemu-system-x86 libvirt-daemon-system libvirt-clients virt-manager\n"
            "sudo usermod -aG kvm,libvirt $USER\n"
            "sudo systemctl enable --now libvirtd"
        ) if not (libvirt_connected and kvm_writable) else None

        return {
            "status": status_code,
            "details": details_msg,
            "is_hypervisor_ready": libvirt_connected and kvm_writable,
            "hypervisor_uri": self.uri,
            "virsh_path": self.virsh_path,
            "virsh_available": virsh_available,
            "virsh_version": virsh_version,
            "virsh_error": virsh_error,
            "kvm_device_path": self.kvm_device_path,
            "kvm_device_exists": kvm_exists,
            "kvm_device_readable": kvm_readable,
            "kvm_device_writable": kvm_writable,
            "host_cpu_cores": host_cpu_cores,
            "host_total_ram_gb": host_total_ram_gb,
            "host_available_ram_gb": host_available_ram_gb,
            "safety_headroom_ram_gb": self.safety_headroom_ram_gb,
            "max_safe_allocatable_ram_gb": safe_allocatable_ram_gb,
            "instructions": instructions,
            "kvm_device": {
                "path": self.kvm_device_path,
                "exists": kvm_exists,
                "readable": kvm_readable,
                "writable": kvm_writable,
            },
            "virsh": {
                "installed": virsh_available,
                "path": self.virsh_path,
                "connected": libvirt_connected,
                "version": virsh_version,
                "error": virsh_error,
            },
            "host_capacity": {
                "cpu_cores": host_cpu_cores,
                "total_ram_gb": host_total_ram_gb,
                "available_ram_gb": host_available_ram_gb,
                "safety_headroom_ram_gb": self.safety_headroom_ram_gb,
                "safe_allocatable_ram_gb": safe_allocatable_ram_gb,
            },
            "allowed_test_vms": sorted(list(self.allowed_test_vms)),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    # -------------------------------------------------------------------------
    # Domain Validation & Safety Guards
    # -------------------------------------------------------------------------

    def validate_domain_name(self, domain_name: str) -> Tuple[bool, str]:
        """Validate domain name format and assert it is an authorized test VM."""
        if not domain_name or not isinstance(domain_name, str):
            return False, "Domain name is required."

        clean_name = domain_name.strip()
        if not DOMAIN_NAME_REGEX.match(clean_name):
            return False, f"Invalid domain identifier '{domain_name}'. Must be alphanumeric with dashes or underscores."

        lower_name = clean_name.lower()
        if lower_name in PROTECTED_DOMAINS or any(p in lower_name for p in ("host", "root", "system")):
            return False, f"Domain '{domain_name}' is a protected identifier and cannot be modified."

        if lower_name not in [v.lower() for v in self.allowed_test_vms]:
            return False, (
                f"Domain '{domain_name}' is not in the authorized test VM allowlist. "
                f"Allowed test VMs: {sorted(list(self.allowed_test_vms))}"
            )

        return True, ""

    def validate_host_headroom(self, target_cpu: float, target_memory_gb: float) -> Tuple[bool, str]:
        """Verify that requested VM allocation leaves sufficient host safety headroom."""
        if target_cpu <= 0 or target_memory_gb <= 0:
            return False, "Requested CPU cores and memory must be positive numbers greater than zero."

        vm_mem = psutil.virtual_memory()
        host_available_gb = vm_mem.available / (1024 ** 3)
        host_total_cores = psutil.cpu_count(logical=True) or 1

        if target_cpu > host_total_cores:
            return False, f"Requested {target_cpu} vCPUs exceeds physical host core count ({host_total_cores} cores)."

        if target_memory_gb > (host_available_gb - self.safety_headroom_ram_gb):
            max_safe = max(0.5, round(host_available_gb - self.safety_headroom_ram_gb, 2))
            return False, (
                f"Requested {target_memory_gb} GB RAM exceeds safe allocatable host RAM "
                f"({max_safe} GB available after preserving {self.safety_headroom_ram_gb} GB host safety headroom)."
            )

        return True, ""

    # -------------------------------------------------------------------------
    # Domain Discovery & Inspection
    # -------------------------------------------------------------------------

    def list_domains(self) -> List[Dict[str, Any]]:
        """List all discovered libvirt domains with current state and allocations."""
        if self._mock_mode:
            return list(self._mock_domains.values())

        check = self.check_hypervisor_status()
        if not check["is_hypervisor_ready"]:
            return []

        domains: List[Dict[str, Any]] = []
        try:
            # Run virsh list --all
            proc = subprocess.run(
                [self.virsh_path, "-c", self.uri, "list", "--all", "--name"],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if proc.returncode != 0:
                return []

            names = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
            for name in names:
                info = self.inspect_domain(name)
                if info:
                    domains.append(info)
        except Exception:
            return []

        return domains

    def inspect_domain(self, domain_name: str) -> Optional[Dict[str, Any]]:
        """Inspect a specific libvirt domain's state, vCPU, and memory allocation."""
        if self._mock_mode:
            return self._mock_domains.get(domain_name)

        if not self.virsh_path:
            return None

        clean_name = domain_name.strip()
        if not DOMAIN_NAME_REGEX.match(clean_name):
            return None

        try:
            # 1. virsh dominfo <domain>
            proc_info = subprocess.run(
                [self.virsh_path, "-c", self.uri, "dominfo", clean_name],
                capture_output=True,
                text=True,
                timeout=8,
            )
            if proc_info.returncode != 0:
                return None

            info_dict = {}
            for line in proc_info.stdout.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    info_dict[k.strip().lower()] = v.strip()

            uuid = info_dict.get("uuid", "")
            state = info_dict.get("state", "unknown").lower()
            cpu_cores = int(info_dict.get("cpu(s)", "1"))

            # Memory parsing (virsh returns memory in KiB)
            max_mem_raw = info_dict.get("max memory", "0 KiB")
            used_mem_raw = info_dict.get("used memory", "0 KiB")

            max_mem_kib = int(max_mem_raw.split()[0]) if max_mem_raw.split() else 0
            used_mem_kib = int(used_mem_raw.split()[0]) if used_mem_raw.split() else 0

            max_memory_gb = round(max_mem_kib / (1024 ** 2), 2)
            current_memory_gb = round(used_mem_kib / (1024 ** 2), 2)

            # Determine live resize capabilities
            is_running = state == "running"
            is_shutoff = state in ("shut off", "shutoff")

            # Check max vcpu if available
            max_vcpus = cpu_cores
            try:
                proc_vcpu = subprocess.run(
                    [self.virsh_path, "-c", self.uri, "vcpumax", clean_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if proc_vcpu.returncode == 0 and proc_vcpu.stdout.strip().isdigit():
                    max_vcpus = int(proc_vcpu.stdout.strip())
            except Exception:
                pass

            is_test_vm = clean_name.lower() in [v.lower() for v in self.allowed_test_vms]

            return {
                "name": clean_name,
                "uuid": uuid,
                "state": state,
                "is_running": is_running,
                "is_shutoff": is_shutoff,
                "current_cpu_cores": cpu_cores,
                "max_cpu_cores": max(cpu_cores, max_vcpus),
                "current_memory_gb": current_memory_gb,
                "max_memory_gb": max_memory_gb,
                "is_test_vm": is_test_vm,
                "adapter_type": "libvirt-qemu",
                "estimated_monthly_cost": estimate_vm_monthly_cost(cpu_cores, current_memory_gb),
                "inspected_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Resource Resizing Execution & Verification
    # -------------------------------------------------------------------------

    def resize_vm(
        self,
        domain_name: str,
        target_cpu: float,
        target_memory_gb: float,
        policy: Optional[Any] = None,
        allow_shutdown: bool = False,
    ) -> Dict[str, Any]:
        """
        Resize a libvirt VM with bounds enforcement, capability checks, and post-verification.
        
        Guarantees:
        - Never shuts down a running VM automatically unless allow_shutdown=True is explicitly given.
        - Verifies resulting limits directly from virsh dominfo before returning SUCCESS.
        - Returns REQUIRES_SHUTDOWN if live adjustment is unsupported.
        """
        # 1. Domain allowlist validation
        valid_name, err = self.validate_domain_name(domain_name)
        if not valid_name:
            return {
                "success": False,
                "status": "VALIDATION_FAILED",
                "error": err,
                "requires_shutdown": False,
            }

        # 2. Inspect current domain state
        current = self.inspect_domain(domain_name)
        if not current:
            return {
                "success": False,
                "status": "DOMAIN_NOT_FOUND",
                "error": f"Domain '{domain_name}' not found on hypervisor.",
                "requires_shutdown": False,
            }

        curr_cpu = current["current_cpu_cores"]
        curr_mem = current["current_memory_gb"]
        max_cpu_allowed = current["max_cpu_cores"]
        max_mem_allowed = current["max_memory_gb"]

        # 3. Policy validation (if policy object provided)
        if policy:
            p_min_cpu = getattr(policy, "min_cpu_cores", 1.0)
            p_max_cpu = getattr(policy, "max_cpu_cores", 16.0)
            p_min_mem = getattr(policy, "min_memory_gb", 0.5)
            p_max_mem = getattr(policy, "max_memory_gb", 64.0)

            if target_cpu < p_min_cpu or target_cpu > p_max_cpu:
                return {
                    "success": False,
                    "status": "POLICY_VIOLATION",
                    "error": f"Requested CPU ({target_cpu} cores) violates policy bounds [{p_min_cpu} - {p_max_cpu}].",
                    "requires_shutdown": False,
                }
            if target_memory_gb < p_min_mem or target_memory_gb > p_max_mem:
                return {
                    "success": False,
                    "status": "POLICY_VIOLATION",
                    "error": f"Requested memory ({target_memory_gb} GB) violates policy bounds [{p_min_mem} - {p_max_mem} GB].",
                    "requires_shutdown": False,
                }

        # 4. Host headroom check
        headroom_ok, headroom_err = self.validate_host_headroom(target_cpu, target_memory_gb)
        if not headroom_ok:
            return {
                "success": False,
                "status": "INSUFFICIENT_HOST_CAPACITY",
                "error": headroom_err,
                "requires_shutdown": False,
            }

        # 5. Check if operation is a no-op
        if int(target_cpu) == int(curr_cpu) and abs(target_memory_gb - curr_mem) < 0.05:
            return {
                "success": True,
                "status": "NOOP",
                "message": f"VM '{domain_name}' already possesses requested allocation ({curr_cpu} vCPU, {curr_mem} GB RAM).",
                "current_allocation": {"cpu_cores": curr_cpu, "memory_gb": curr_mem},
                "verified": True,
                "requires_shutdown": False,
            }

        # 6. Check live vs shutdown requirements
        is_running = current["is_running"]
        is_shutoff = current["is_shutoff"]
        target_mem_kib = int(target_memory_gb * (1024 ** 2))

        # Check live limitations:
        # A. Live vCPU decrease (shrinking) is unsupported by QEMU/KVM without guest reboot/shutdown
        cpu_decrease = int(target_cpu) < int(curr_cpu)
        # B. Exceeding max configured vCPUs requires domain XML update and shutdown
        cpu_exceeds_max = int(target_cpu) > int(max_cpu_allowed)
        # C. Exceeding max configured memory requires domain XML update and shutdown
        mem_exceeds_max = target_memory_gb > max_mem_allowed

        needs_shutdown = is_running and (cpu_decrease or cpu_exceeds_max or mem_exceeds_max)

        if needs_shutdown and not allow_shutdown:
            reasons = []
            if cpu_decrease:
                reasons.append(f"Live vCPU reduction ({curr_cpu} -> {target_cpu} cores) is unsupported by KVM while running")
            if cpu_exceeds_max:
                reasons.append(f"Requested {target_cpu} vCPUs exceeds domain maximum ({max_cpu_allowed} cores)")
            if mem_exceeds_max:
                reasons.append(f"Requested {target_memory_gb} GB RAM exceeds domain maximum ({max_mem_allowed} GB)")

            return {
                "success": False,
                "status": "REQUIRES_SHUTDOWN",
                "error": (
                    f"Requested resize cannot be completed live without downtime: {'; '.join(reasons)}. "
                    "Safety protocol: SmartCloud Optimizer will never automatically shut down a guest VM. "
                    "Explicit administrator approval with allow_shutdown=true is required."
                ),
                "requires_shutdown": True,
                "current_allocation": {"cpu_cores": curr_cpu, "memory_gb": curr_mem},
                "requested_allocation": {"cpu_cores": target_cpu, "memory_gb": target_memory_gb},
            }

        # 7. Mock mode execution (for test suite)
        if self._mock_mode:
            current["current_cpu_cores"] = int(target_cpu)
            current["current_memory_gb"] = float(target_memory_gb)
            current["estimated_monthly_cost"] = estimate_vm_monthly_cost(int(target_cpu), float(target_memory_gb))

            # Perform independent post-verification check
            post_info = self.inspect_domain(domain_name)
            verified_cpu = post_info.get("current_cpu_cores", 0) if post_info else 0
            verified_mem = post_info.get("current_memory_gb", 0.0) if post_info else 0.0

            cpu_match = verified_cpu == int(target_cpu)
            mem_match = abs(verified_mem - target_memory_gb) < 0.1

            if not (cpu_match and mem_match):
                return {
                    "success": False,
                    "status": "VERIFICATION_MISMATCH",
                    "error": (
                        f"Target allocation ({target_cpu} vCPU, {target_memory_gb} GB) does not match "
                        f"hypervisor post-check ({verified_cpu} vCPU, {verified_mem} GB RAM)."
                    ),
                    "previous_allocation": {"cpu_cores": curr_cpu, "memory_gb": curr_mem},
                    "observed_allocation": {"cpu_cores": verified_cpu, "memory_gb": verified_mem},
                    "verified": False,
                    "requires_shutdown": False,
                }

            return {
                "success": True,
                "status": "VERIFIED_SUCCESS",
                "message": f"Successfully resized VM '{domain_name}' to {int(target_cpu)} vCPU and {target_memory_gb} GB RAM (mock).",
                "previous_allocation": {"cpu_cores": curr_cpu, "memory_gb": curr_mem},
                "applied_allocation": {"cpu_cores": int(target_cpu), "memory_gb": float(target_memory_gb)},
                "new_allocation": {"cpu_cores": int(target_cpu), "memory_gb": float(target_memory_gb)},
                "cost_impact": {
                    "monthly_cost_before_inr": estimate_vm_monthly_cost(curr_cpu, curr_mem),
                    "monthly_cost_after_inr": estimate_vm_monthly_cost(int(target_cpu), float(target_memory_gb)),
                },
                "verified": True,
                "requires_shutdown": False,
            }

        # 8. Real Execution via virsh
        try:
            # Memory resize command
            # If running and memory within max: live adjustment using setmem
            mem_flag = "--config" if is_shutoff else "--live"
            proc_mem = subprocess.run(
                [self.virsh_path, "-c", self.uri, "setmem", domain_name, str(target_mem_kib), mem_flag],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc_mem.returncode != 0:
                # Also try persistent config if live failed
                subprocess.run(
                    [self.virsh_path, "-c", self.uri, "setmem", domain_name, str(target_mem_kib), "--config"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

            # vCPU resize command
            vcpu_flag = "--config" if is_shutoff else "--live"
            proc_cpu = subprocess.run(
                [self.virsh_path, "-c", self.uri, "setvcpus", domain_name, str(int(target_cpu)), vcpu_flag],
                capture_output=True,
                text=True,
                timeout=10,
            )

            # 9. Independent post-change inspection & verification
            post_inspect = self.inspect_domain(domain_name)
            if not post_inspect:
                return {
                    "success": False,
                    "status": "VERIFICATION_FAILED",
                    "error": "Failed to re-inspect VM state after resize execution.",
                    "requires_shutdown": False,
                }

            verified_cpu = post_inspect["current_cpu_cores"]
            verified_mem = post_inspect["current_memory_gb"]

            cpu_match = verified_cpu == int(target_cpu)
            mem_match = abs(verified_mem - target_memory_gb) < 0.1

            if not (cpu_match and mem_match):
                return {
                    "success": False,
                    "status": "VERIFICATION_MISMATCH",
                    "error": (
                        f"Target allocation ({target_cpu} vCPU, {target_memory_gb} GB) does not match "
                        f"hypervisor post-check ({verified_cpu} vCPU, {verified_mem} GB RAM)."
                    ),
                    "previous_allocation": {"cpu_cores": curr_cpu, "memory_gb": curr_mem},
                    "observed_allocation": {"cpu_cores": verified_cpu, "memory_gb": verified_mem},
                    "verified": False,
                    "requires_shutdown": False,
                }

            return {
                "success": True,
                "status": "VERIFIED_SUCCESS",
                "message": f"Successfully resized and verified VM '{domain_name}' to {verified_cpu} vCPU and {verified_mem} GB RAM.",
                "previous_allocation": {"cpu_cores": curr_cpu, "memory_gb": curr_mem},
                "applied_allocation": {"cpu_cores": verified_cpu, "memory_gb": verified_mem},
                "cost_impact": {
                    "monthly_cost_before_inr": estimate_vm_monthly_cost(curr_cpu, curr_mem),
                    "monthly_cost_after_inr": estimate_vm_monthly_cost(verified_cpu, verified_mem),
                },
                "verified": True,
                "requires_shutdown": False,
            }
        except Exception as e:
            return {
                "success": False,
                "status": "EXECUTION_ERROR",
                "error": f"Error executing virsh resize: {str(e)}",
                "requires_shutdown": False,
            }
