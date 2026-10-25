"""
Unit and integration tests for Stage 5 Autoscaler Controller and REST Endpoints.
Covers scale-out, scale-in, cooldown suppression, min/max limits, health checks, and API.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from main import app
from engines.autoscaler import AutoscalingController, AutoscalerConfig

client = TestClient(app)


@pytest.fixture
def test_controller():
    """Create an isolated AutoscalingController in mock mode for deterministic testing."""
    cfg = AutoscalerConfig(
        min_replicas=1,
        max_replicas=4,
        scale_out_threshold=50.0,
        scale_in_threshold=20.0,
        scale_out_cooldown=10.0,
        scale_in_cooldown=15.0,
        sustained_window_samples=2,
    )
    ctrl = AutoscalingController(cfg)
    ctrl._mock_mode = True
    ctrl._mock_replicas = 1
    ctrl._mock_cpu = 10.0
    return ctrl


def test_scale_out_requires_sustained_window(test_controller):
    """Verify scale-out does NOT trigger on a single spike; requires sustained samples."""
    # First high spike (sample 1)
    test_controller._mock_cpu = 75.0
    res1 = test_controller.evaluate_and_scale()
    assert res1["current_replicas"] == 1
    assert res1["last_action"] == "SUSTAINED_WINDOW_EVALUATING"
    assert "sample 1/2" in res1["latest_decision"]["reason"]

    # Second high sample (sample 2 of 2) -> should scale out!
    res2 = test_controller.evaluate_and_scale()
    assert res2["current_replicas"] == 2 or res2["current_replicas"] == 3
    assert res2["last_action"] == "SCALE_OUT"
    assert "Scaled out" in res2["latest_decision"]["reason"]


def test_scale_out_cooldown_prevents_oscillation(test_controller):
    """Verify that immediately following a scale event, cooldown suppresses further scaling."""
    # Trigger scale out
    test_controller._mock_cpu = 80.0
    test_controller.evaluate_and_scale()
    test_controller.evaluate_and_scale()
    assert test_controller.last_scale_action == "SCALE_OUT"
    initial_scaled = test_controller._mock_replicas

    # Immediately submit another high load evaluation
    test_controller.consecutive_high_samples = 2
    res_cooldown = test_controller.evaluate_and_scale()
    assert res_cooldown["last_action"] == "COOLDOWN_ACTIVE"
    assert res_cooldown["current_replicas"] == initial_scaled
    assert "cooldown is active" in res_cooldown["latest_decision"]["reason"]


def test_scale_in_requires_sustained_window_and_cooldown(test_controller):
    """Verify scale-in safely steps down after sustained low load and cooldown."""
    test_controller._mock_replicas = 3
    test_controller._mock_cpu = 8.0
    # Clear cooldown
    test_controller.last_scale_time = 0.0

    # Sample 1 of low load
    res1 = test_controller.evaluate_and_scale()
    assert res1["current_replicas"] == 3
    assert res1["last_action"] == "SUSTAINED_WINDOW_EVALUATING"

    # Sample 2 of low load -> scale in by 1
    res2 = test_controller.evaluate_and_scale()
    assert res2["current_replicas"] == 2
    assert res2["last_action"] == "SCALE_IN"
    assert "Scaled in from 3 to 2" in res2["latest_decision"]["reason"]


def test_min_and_max_replica_bounds(test_controller):
    """Verify replicas cannot scale below minimum or above maximum limits."""
    # Max bound test
    test_controller._mock_replicas = 4
    test_controller._mock_cpu = 95.0
    test_controller.last_scale_time = 0.0
    test_controller.consecutive_high_samples = 1  # Next will be sample 2
    res_max = test_controller.evaluate_and_scale()
    assert res_max["current_replicas"] == 4
    assert res_max["last_action"] == "MAX_REPLICAS_LIMIT"

    # Min bound test
    test_controller._mock_replicas = 1
    test_controller._mock_cpu = 5.0
    test_controller.last_scale_time = 0.0
    test_controller.consecutive_low_samples = 1  # Next will be sample 2
    res_min = test_controller.evaluate_and_scale()
    assert res_min["current_replicas"] == 1
    assert res_min["last_action"] == "MIN_REPLICAS_LIMIT"


def test_failed_health_check_handling(test_controller):
    """Verify degraded gateway health is reported in evaluation status."""
    with patch.object(test_controller, "check_gateway_health", return_value=False):
        test_controller._mock_cpu = 25.0
        res = test_controller.evaluate_and_scale()
        assert res["is_healthy"] is False
        assert "Gateway health check did not return 200 OK" in res["latest_decision"]["reason"]


def test_api_autoscaling_status_endpoint():
    """Verify GET /api/autoscaling/status response schema and fields."""
    response = client.get("/api/autoscaling/status")
    assert response.status_code == 200
    data = response.json()
    assert "current_replicas" in data
    assert "target_replicas" in data
    assert "min_replicas" in data
    assert "max_replicas" in data
    assert "average_cpu_percent" in data
    assert "scale_out_threshold" in data
    assert "scale_in_threshold" in data
    assert "recent_events" in data
    assert "is_healthy" in data


def test_api_autoscaling_config_endpoint():
    """Verify POST /api/autoscaling/config updates thresholds."""
    payload = {
        "scale_out_threshold": 55.0,
        "scale_in_threshold": 18.0,
        "min_replicas": 1,
        "max_replicas": 5,
        "scale_out_cooldown": 12.0,
    }
    response = client.post("/api/autoscaling/config", json=payload)
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["config"]["scale_out_threshold"] == 55.0
    assert response.json()["config"]["scale_in_threshold"] == 18.0


def test_api_manual_scale_endpoint():
    """Verify POST /api/autoscaling/scale endpoint."""
    with patch("main.autoscaler_controller.execute_docker_scale", return_value=True):
        response = client.post("/api/autoscaling/scale", json={"target_replicas": 2})
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["target_replicas"] == 2
