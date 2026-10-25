"""
SmartCloud Optimizer — Stage 6 Vertical Scaling Unit Tests
Tests:
1. Docker container whitelist enforcement (preventing modification of unauthorized containers).
2. Live container inspection (CPU cores, RAM GB).
3. Docker update execution and immediate limit verification.
4. Bound check rejections (too small / too large).
5. FinOps compute cost estimation formula accuracy.
6. Mock mode support for headless test environments.
"""
import pytest
from engines.vertical_scaler import VerticalScalingService, estimate_compute_monthly_cost


def test_cost_estimation_finops_formula():
    """Verify compute tier calculation: ₹800/core + ₹200/GB RAM."""
    # 2 cores, 4 GB RAM = (2 * 800) + (4 * 200) = 1600 + 800 = 2400
    assert estimate_compute_monthly_cost(2.0, 4.0) == 2400.0

    # 0.5 cores, 1.0 GB RAM = (0.5 * 800) + (1 * 200) = 400 + 200 = 600
    assert estimate_compute_monthly_cost(0.5, 1.0) == 600.0

    # 16 cores, 64 GB RAM = (16 * 800) + (64 * 200) = 12800 + 12800 = 25600
    assert estimate_compute_monthly_cost(16.0, 64.0) == 25600.0


def test_container_whitelist_security():
    scaler = VerticalScalingService()
    # Allowed containers
    assert scaler.is_allowed_container("autoscaling-lab-app-1") is True
    assert scaler.is_allowed_container("autoscaling-lab-app-2") is True
    assert scaler.is_allowed_container("smartcloud-autoscaling-app-1") is True

    # Blocked dangerous or host containers
    assert scaler.is_allowed_container("smartcloud-gateway") is False
    assert scaler.is_allowed_container("postgres") is False
    assert scaler.is_allowed_container("/etc/shadow") is False
    assert scaler.is_allowed_container("autoscaling-lab-app-1; rm -rf /") is False
    assert scaler.is_allowed_container("") is False


def test_vertical_scaler_mock_mode():
    scaler = VerticalScalingService()
    scaler._mock_mode = True

    # Inspect initial
    ok, limits, msg = scaler.inspect_container_limits("autoscaling-lab-app-1")
    assert ok is True
    assert limits["cpu_cores"] == 1.0
    assert limits["memory_gb"] == 0.5

    # Scale update
    ok, updated, msg = scaler.update_container_limits("autoscaling-lab-app-1", requested_cpu=2.5, requested_memory_gb=1.5)
    assert ok is True
    assert updated["cpu_cores"] == 2.5
    assert updated["memory_gb"] == 1.5
    assert updated["effective_limits_verified"] is True


def test_vertical_scaler_bounds_rejection():
    scaler = VerticalScalingService()
    scaler._mock_mode = True

    # Too small CPU (< 0.25)
    ok, _, msg = scaler.update_container_limits("autoscaling-lab-app-1", requested_cpu=0.1, requested_memory_gb=1.0)
    assert ok is False
    assert "Invalid CPU request" in msg

    # Too high CPU (> 32)
    ok, _, msg = scaler.update_container_limits("autoscaling-lab-app-1", requested_cpu=64.0, requested_memory_gb=1.0)
    assert ok is False
    assert "Invalid CPU request" in msg

    # Too small RAM (< 0.125)
    ok, _, msg = scaler.update_container_limits("autoscaling-lab-app-1", requested_cpu=1.0, requested_memory_gb=0.05)
    assert ok is False
    assert "Invalid Memory request" in msg


def test_unauthorized_container_rejection():
    scaler = VerticalScalingService()
    ok, _, msg = scaler.inspect_container_limits("unauthorized-container")
    assert ok is False
    assert "Security error" in msg

    ok, _, msg = scaler.update_container_limits("unauthorized-container", 2.0, 2.0)
    assert ok is False
    assert "Security error" in msg
