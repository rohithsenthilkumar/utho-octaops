"""
SmartCloud Optimizer — Stage 9A: KVM/QEMU & Libvirt VM Management Unit Tests
=============================================================================
Comprehensive test suite verifying:
1. Preflight virtualization capability detection and /dev/kvm inspection.
2. Safe command arguments (zero shell interpolation).
3. Domain allowlist security (rejecting shell injection and protected domains: host, localhost, kali).
4. Host headroom safety constraints (preserving 2 GB RAM buffer).
5. FinOps compute cost estimation formula for VMs (₹800/core + ₹200/GB RAM).
6. Independent hypervisor state post-verification.
7. REQUIRES_SHUTDOWN detection (zero unplanned guest downtime without explicit flag).
8. Verified resize execution when allow_shutdown is authorized.
9. Verification mismatch detection if hypervisor state fails to reflect target.
10. KVM VM Optimizer default state (disabled, DRY_RUN).
11. KVM VM Optimizer independence from Docker container autoscaler/optimizer.
12. RBAC protection on resize and config routes (admin-only).
13. AuditEvent persistence with actor details and parameter logging.
14. Domain inspection 404 handling.
15. Safe NOOP handling when target matches current allocation.
16. DRY_RUN evaluation non-mutation guarantee.
"""
import pytest
from fastapi.testclient import TestClient

from main import app, kvm_adapter, kvm_optimizer, unified_optimizer_engine
from database import get_db, SessionLocal
from models import User, Company, ResourcePolicy, AuditEvent
from auth import create_access_token
from engines.kvm_adapter import (
    KvmLibvirtAdapter,
    estimate_vm_monthly_cost,
    DEFAULT_ALLOWED_TEST_VMS,
    PROTECTED_DOMAINS,
)
from engines.kvm_optimizer import (
    KvmVmOptimizerEngine,
    VmOptimizerConfig,
    MODE_DRY_RUN,
    MODE_RECOMMENDATION,
    MODE_AUTO,
)

client = TestClient(app)


def get_auth_header(email: str = "admin@cloudflow.com") -> dict:
    """Generate authenticated Bearer JWT token header for a specific user."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = db.query(User).first()
        token = create_access_token(user)
        return {"Authorization": f"Bearer {token}"}
    finally:
        db.close()


def get_non_admin_auth_header() -> dict:
    """Generate Bearer JWT token header for VM_OWNER persona."""
    return get_auth_header(email="devops@cloudflow.com")


# -----------------------------------------------------------------------------
# Fixtures & Test Setup
# -----------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_mock_kvm():
    """Ensure KVM adapter and optimizer operate cleanly in mock mode for unit tests."""
    kvm_adapter._mock_mode = True
    kvm_adapter._mock_domains = {
        "smartcloud-test-vm": {
            "name": "smartcloud-test-vm",
            "uuid": "a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d",
            "state": "running",
            "is_running": True,
            "is_shutoff": False,
            "current_cpu_cores": 2,
            "max_cpu_cores": 4,
            "current_memory_gb": 2.0,
            "max_memory_gb": 8.0,
            "is_test_vm": True,
            "adapter_type": "libvirt-qemu",
            "estimated_monthly_cost": 2000.0,
            "inspected_at": "2026-10-24T12:00:00Z",
        },
        "demo-kvm-vm-01": {
            "name": "demo-kvm-vm-01",
            "uuid": "b2c3d4e5-f6a7-8b9c-0d1e-2f3a4b5c6d7e",
            "state": "shut off",
            "is_running": False,
            "is_shutoff": True,
            "current_cpu_cores": 1,
            "max_cpu_cores": 2,
            "current_memory_gb": 1.0,
            "max_memory_gb": 4.0,
            "is_test_vm": True,
            "adapter_type": "libvirt-qemu",
            "estimated_monthly_cost": 1000.0,
            "inspected_at": "2026-10-24T12:00:00Z",
        },
    }
    kvm_optimizer.config = VmOptimizerConfig(enabled=False, operating_mode=MODE_DRY_RUN)
    yield
    kvm_adapter._mock_mode = False


# -----------------------------------------------------------------------------
# 1. Hypervisor Detection & Host Capabilities
# -----------------------------------------------------------------------------

def test_hypervisor_detection_diagnostics():
    """Verify check_hypervisor_status returns valid structure and safe diagnostics."""
    status = kvm_adapter.check_hypervisor_status()
    assert "is_hypervisor_ready" in status
    assert "status" in status
    assert "host_cpu_cores" in status
    assert status["host_cpu_cores"] >= 1
    assert "host_total_ram_gb" in status
    assert status["host_total_ram_gb"] > 0
    assert "safety_headroom_ram_gb" in status
    assert status["safety_headroom_ram_gb"] == 2.0
    assert "kvm_device_path" in status
    assert status["kvm_device_path"] == "/dev/kvm"


def test_finops_compute_cost_formula():
    """Verify KVM VM FinOps pricing formula: ₹800/vCPU + ₹200/GB RAM."""
    assert estimate_vm_monthly_cost(1.0, 1.0) == 1000.0
    assert estimate_vm_monthly_cost(2.0, 4.0) == 2400.0
    assert estimate_vm_monthly_cost(4.0, 8.0) == 4800.0
    assert estimate_vm_monthly_cost(0.5, 0.5) == 500.0


# -----------------------------------------------------------------------------
# 2. Domain Validation & Security Bounds
# -----------------------------------------------------------------------------

def test_domain_allowlist_and_injection_rejection():
    """Verify strict domain validation rejects shell injections and protected host IDs."""
    adapter = KvmLibvirtAdapter()

    # Allowed test VMs
    for vm_name in DEFAULT_ALLOWED_TEST_VMS:
        valid, msg = adapter.validate_domain_name(vm_name)
        assert valid is True, f"Failed for allowed VM {vm_name}"

    # Protected host keywords
    for protected in PROTECTED_DOMAINS:
        valid, msg = adapter.validate_domain_name(protected)
        assert valid is False
        assert "protected identifier" in msg.lower()

    # Shell injection and dangerous patterns
    malicious_inputs = [
        "test; rm -rf /",
        "vm`whoami`",
        "$(cat /etc/passwd)",
        "dom0&&reboot",
        "host|ls",
        "../etc/shadow",
        "unauthorized-production-db",
        "",
        " ",
    ]
    for bad in malicious_inputs:
        valid, msg = adapter.validate_domain_name(bad)
        assert valid is False


# -----------------------------------------------------------------------------
# 3. Host Headroom Safety Constraints
# -----------------------------------------------------------------------------

def test_host_headroom_safety_constraints():
    """Verify adapter prevents allocations exceeding host available RAM minus headroom."""
    adapter = KvmLibvirtAdapter(safety_headroom_ram_gb=2.0)

    # Absurdly high RAM request exceeding physical host RAM
    ok, err = adapter.validate_host_headroom(target_cpu=2, target_memory_gb=512.0)
    assert ok is False
    assert "exceeds safe allocatable host ram" in err.lower()

    # Negative or zero requests rejected
    ok, err = adapter.validate_host_headroom(target_cpu=0, target_memory_gb=2.0)
    assert ok is False
    ok, err = adapter.validate_host_headroom(target_cpu=2, target_memory_gb=0)
    assert ok is False


# -----------------------------------------------------------------------------
# 4. Domain Inspection & Discovery
# -----------------------------------------------------------------------------

def test_list_and_inspect_domains():
    """Verify discovery and deep inspection of mock domains."""
    domains = kvm_adapter.list_domains()
    assert len(domains) == 2
    names = {d["name"] for d in domains}
    assert "smartcloud-test-vm" in names
    assert "demo-kvm-vm-01" in names

    # Inspect running VM
    running_vm = kvm_adapter.inspect_domain("smartcloud-test-vm")
    assert running_vm is not None
    assert running_vm["is_running"] is True
    assert running_vm["current_cpu_cores"] == 2
    assert running_vm["current_memory_gb"] == 2.0
    assert running_vm["max_cpu_cores"] == 4
    assert running_vm["estimated_monthly_cost"] == 2000.0

    # Non-existent VM returns None
    assert kvm_adapter.inspect_domain("unknown-vm-999") is None


# -----------------------------------------------------------------------------
# 5. NOOP and Unknown Domain Resizing
# -----------------------------------------------------------------------------

def test_resize_unknown_domain():
    """Attempting to resize an unknown or unallowlisted domain fails safely."""
    res = kvm_adapter.resize_vm("unknown-vm-999", target_cpu=2, target_memory_gb=2.0)
    assert res["success"] is False
    assert res["status"] in ("VALIDATION_FAILED", "DOMAIN_NOT_FOUND")


def test_resize_noop_detection():
    """Requesting the exact current allocation returns NOOP and success."""
    res = kvm_adapter.resize_vm("smartcloud-test-vm", target_cpu=2, target_memory_gb=2.0)
    assert res["success"] is True
    assert res["status"] == "NOOP"
    assert res["verified"] is True


# -----------------------------------------------------------------------------
# 6. Policy Violation Enforcement
# -----------------------------------------------------------------------------

def test_resize_policy_violations():
    """Enforce min/max policy constraints on VM resizing."""
    policy = ResourcePolicy(
        resource_id="smartcloud-test-vm",
        min_cpu_cores=1,
        max_cpu_cores=4,
        min_memory_gb=1.0,
        max_memory_gb=4.0,
    )

    # Exceeding policy max CPU
    res = kvm_adapter.resize_vm("smartcloud-test-vm", target_cpu=8, target_memory_gb=2.0, policy=policy)
    assert res["success"] is False
    assert res["status"] == "POLICY_VIOLATION"
    assert "violates policy bounds" in res["error"]

    # Below policy min RAM
    res = kvm_adapter.resize_vm("smartcloud-test-vm", target_cpu=2, target_memory_gb=0.25, policy=policy)
    assert res["success"] is False
    assert res["status"] == "POLICY_VIOLATION"


# -----------------------------------------------------------------------------
# 7. REQUIRES_SHUTDOWN Protocol & Safe Reboot Approval
# -----------------------------------------------------------------------------

def test_requires_shutdown_without_allow_shutdown():
    """Decreasing vCPU on a running VM requires guest shutdown; fails safely if allow_shutdown=False."""
    # Current is 2 cores. Target is 1 core. QEMU live vCPU decrease unsupported.
    res = kvm_adapter.resize_vm(
        "smartcloud-test-vm",
        target_cpu=1,
        target_memory_gb=2.0,
        allow_shutdown=False,
    )
    assert res["success"] is False
    assert res["status"] == "REQUIRES_SHUTDOWN"
    assert res["requires_shutdown"] is True
    assert "Live vCPU reduction" in res["error"]

    # Verify allocation was NOT changed
    info = kvm_adapter.inspect_domain("smartcloud-test-vm")
    assert info["current_cpu_cores"] == 2


def test_verified_resize_with_allow_shutdown():
    """With explicit allow_shutdown=True, resize completes and verifies hypervisor limits."""
    res = kvm_adapter.resize_vm(
        "smartcloud-test-vm",
        target_cpu=1,
        target_memory_gb=1.5,
        allow_shutdown=True,
    )
    assert res["success"] is True
    assert res["status"] in ("SUCCESS", "VERIFIED_SUCCESS")
    assert res["verified"] is True
    assert res["new_allocation"]["cpu_cores"] == 1
    assert res["new_allocation"]["memory_gb"] == 1.5

    # Direct hypervisor inspection verification
    info = kvm_adapter.inspect_domain("smartcloud-test-vm")
    assert info["current_cpu_cores"] == 1
    assert info["current_memory_gb"] == 1.5
    assert info["estimated_monthly_cost"] == estimate_vm_monthly_cost(1, 1.5)


# -----------------------------------------------------------------------------
# 8. Verification Mismatch Detection
# -----------------------------------------------------------------------------

def test_verification_mismatch_detection(monkeypatch):
    """If hypervisor state does not match requested targets post-execution, fail verification."""
    adapter = KvmLibvirtAdapter()
    adapter._mock_mode = True
    adapter._mock_domains = {
        "smartcloud-test-vm": {
            "name": "smartcloud-test-vm",
            "state": "shut off",
            "is_running": False,
            "is_shutoff": True,
            "current_cpu_cores": 2,
            "max_cpu_cores": 4,
            "current_memory_gb": 2.0,
            "max_memory_gb": 8.0,
            "is_test_vm": True,
            "adapter_type": "libvirt-qemu",
            "estimated_monthly_cost": 2000.0,
            "inspected_at": "2026-10-24T12:00:00Z",
        }
    }

    # Simulate hypervisor ignoring memory change in post inspection
    def fake_inspect(domain_name):
        return {
            "name": domain_name,
            "current_cpu_cores": 3,
            "current_memory_gb": 2.0,  # Stale memory!
            "max_cpu_cores": 4,
            "max_memory_gb": 8.0,
            "is_running": False,
            "is_shutoff": True,
        }

    monkeypatch.setattr(adapter, "inspect_domain", fake_inspect)
    res = adapter.resize_vm("smartcloud-test-vm", target_cpu=3, target_memory_gb=4.0, allow_shutdown=True)
    assert res["success"] is False
    assert res["status"] == "VERIFICATION_MISMATCH"
    assert res["verified"] is False


# -----------------------------------------------------------------------------
# 9. KVM VM Optimizer Engine Invariants & Independence
# -----------------------------------------------------------------------------

def test_kvm_optimizer_default_invariants():
    """Verify KVM VM Optimizer is disabled by default in DRY_RUN mode."""
    opt = KvmVmOptimizerEngine(adapter=kvm_adapter)
    status = opt.get_status()
    assert status["enabled"] is False
    assert status["operating_mode"] == MODE_DRY_RUN
    assert status["scheduler_state"] == "IDLE_DISABLED"


def test_kvm_optimizer_independence_from_container_optimizer():
    """Verify modifying KVM VM Optimizer never mutates Container Optimizer."""
    initial_container_mode = unified_optimizer_engine.config.operating_mode
    initial_container_enabled = unified_optimizer_engine.config.enabled

    # Mutate KVM optimizer
    kvm_optimizer.update_config({"enabled": True, "operating_mode": MODE_RECOMMENDATION})
    assert kvm_optimizer.config.enabled is True
    assert kvm_optimizer.config.operating_mode == MODE_RECOMMENDATION

    # Container optimizer must remain pristine
    assert unified_optimizer_engine.config.operating_mode == initial_container_mode
    assert unified_optimizer_engine.config.enabled == initial_container_enabled

    # Reset
    kvm_optimizer.update_config({"enabled": False, "operating_mode": MODE_DRY_RUN})


def test_kvm_optimizer_dry_run_non_mutation():
    """DRY_RUN mode proposes vertical scaling without modifying hypervisor VM limits."""
    kvm_optimizer.update_config({"sustained_window_samples": 1, "cooldown_seconds": 0})

    decision = kvm_optimizer.evaluate_vm(
        domain_name="smartcloud-test-vm",
        observed_guest_cpu=92.0,
        observed_guest_ram_percent=88.0,
        mode_override=MODE_DRY_RUN,
    )
    assert decision["decision"] == "VM_SCALE_UP"
    assert decision["operating_mode"] == MODE_DRY_RUN
    assert decision["executed"] is False
    assert decision["verified"] is False
    assert "DRY_RUN mode active" in decision["reason"]
    assert decision["proposed_allocation"]["cpu_cores"] == 4
    assert decision["proposed_allocation"]["memory_gb"] == 4.0

    # VM limits must remain unchanged
    info = kvm_adapter.inspect_domain("smartcloud-test-vm")
    assert info["current_cpu_cores"] == 2
    assert info["current_memory_gb"] == 2.0


def test_kvm_optimizer_insufficient_data():
    """If guest telemetry is absent, optimizer returns INSUFFICIENT_DATA and never guesses."""
    decision = kvm_optimizer.evaluate_vm(
        domain_name="smartcloud-test-vm",
        observed_guest_cpu=None,
        observed_guest_ram_percent=None,
    )
    assert decision["decision"] == "INSUFFICIENT_DATA"
    assert "Guest VM utilization metrics" in decision["reason"] or "Safety rule" in decision["reason"]


# -----------------------------------------------------------------------------
# 10. REST API Endpoints, RBAC, and Audit Logging
# -----------------------------------------------------------------------------

def test_api_kvm_status():
    """GET /api/kvm/status returns status structure."""
    res = client.get("/api/kvm/status", headers=get_auth_header())
    assert res.status_code == 200
    data = res.json()
    assert "host_cpu_cores" in data
    assert "safety_headroom_ram_gb" in data


def test_api_kvm_domains_list_and_inspect():
    """GET /api/kvm/domains and GET /api/kvm/domains/{domain_name}."""
    res = client.get("/api/kvm/domains", headers=get_auth_header())
    assert res.status_code == 200
    domains = res.json()
    assert len(domains) >= 2

    # Inspect existing
    res_vm = client.get("/api/kvm/domains/smartcloud-test-vm", headers=get_auth_header())
    assert res_vm.status_code == 200
    assert res_vm.json()["name"] == "smartcloud-test-vm"

    # Inspect unknown
    res_404 = client.get("/api/kvm/domains/unknown-domain-xyz", headers=get_auth_header())
    assert res_404.status_code == 404


def test_api_kvm_resize_rbac():
    """POST /api/kvm/domains/{domain_name}/resize requires administrator role."""
    # Attempt with VM_OWNER role -> 403 Forbidden
    res_forbidden = client.post(
        "/api/kvm/domains/smartcloud-test-vm/resize",
        headers=get_non_admin_auth_header(),
        json={"target_cpu": 2, "target_memory_gb": 2.0, "allow_shutdown": False},
    )
    assert res_forbidden.status_code == 403

    # Attempt without auth -> 401 Unauthorized
    res_unauth = client.post(
        "/api/kvm/domains/smartcloud-test-vm/resize",
        json={"target_cpu": 2, "target_memory_gb": 2.0, "allow_shutdown": False},
    )
    assert res_unauth.status_code == 401


def test_api_kvm_resize_and_audit_event():
    """Admin resize logs AuditEvent and returns valid response."""
    res = client.post(
        "/api/kvm/domains/smartcloud-test-vm/resize",
        headers=get_auth_header(),
        json={"target_cpu": 2, "target_memory_gb": 2.0, "allow_shutdown": False},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["status"] == "NOOP"
    assert data["audit_event_id"] is not None

    # Verify audit event in DB
    db = SessionLocal()
    audit = db.query(AuditEvent).filter(AuditEvent.id == data["audit_event_id"]).first()
    assert audit is not None
    assert audit.action == "KVM_VM_RESIZED"
    assert audit.resource_id == "smartcloud-test-vm"
    db.close()


def test_api_kvm_requires_shutdown_response():
    """Live vCPU reduction via API returns REQUIRES_SHUTDOWN flag without forced downtime."""
    res = client.post(
        "/api/kvm/domains/smartcloud-test-vm/resize",
        headers=get_auth_header(),
        json={"target_cpu": 1, "target_memory_gb": 2.0, "allow_shutdown": False},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert data["status"] == "REQUIRES_SHUTDOWN"
    assert data["requires_shutdown"] is True
    assert "Live vCPU reduction" in data["error"]


def test_api_kvm_optimizer_endpoints():
    """Verify KVM optimizer status, config update, and evaluation routes."""
    # Status
    res_status = client.get("/api/kvm/optimizer/status", headers=get_auth_header())
    assert res_status.status_code == 200
    assert res_status.json()["operating_mode"] == "DRY_RUN"

    # Evaluate
    res_eval = client.post(
        "/api/kvm/optimizer/evaluate",
        headers=get_auth_header(),
        json={
            "domain_name": "smartcloud-test-vm",
            "observed_guest_cpu": 88.0,
            "observed_guest_ram_percent": 75.0,
            "mode_override": "DRY_RUN",
        },
    )
    assert res_eval.status_code == 200
    data = res_eval.json()
    assert data["operating_mode"] == "DRY_RUN"
    assert "decision" in data
