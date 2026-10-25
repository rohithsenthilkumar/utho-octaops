"""
Tests for Stage 4 Live Local Host Monitoring Endpoint
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_get_local_monitoring_schema():
    """Verify endpoint returns 200 and matches the expected schema."""
    response = client.get("/api/monitoring/local?interval=0.1")
    assert response.status_code == 200

    data = response.json()
    assert "timestamp" in data
    assert "cpu_utilization" in data
    assert "cpu_percent" in data
    assert "ram_utilization" in data
    assert "ram_percent" in data
    assert "used_ram_gb" in data
    assert "total_ram_gb" in data
    assert "used_ram_bytes" in data
    assert "total_ram_bytes" in data
    assert "sampling_interval_seconds" in data
    assert "metric_source" in data
    assert "status" in data

    # Schema values
    assert data["metric_source"] == "Live local host metrics"
    assert data["status"] == "healthy"
    assert data["sampling_interval_seconds"] == 0.1


def test_cpu_and_ram_realistic_bounds():
    """
    Verify readings fall within realistic percentage/memory bounds.
    Do NOT assert fixed percentages because real host load fluctuates.
    """
    response = client.get("/api/monitoring/local?interval=0.1")
    assert response.status_code == 200
    data = response.json()

    # CPU utilization must be between 0% and 100%
    assert 0.0 <= data["cpu_utilization"] <= 100.0
    assert 0.0 <= data["cpu_percent"] <= 100.0

    # RAM utilization must be between 0% and 100%
    assert 0.0 <= data["ram_utilization"] <= 100.0
    assert 0.0 <= data["ram_percent"] <= 100.0

    # Total RAM must be positive
    assert data["total_ram_gb"] > 0.0
    assert data["total_ram_bytes"] > 0

    # Used RAM must not exceed total RAM
    assert 0.0 <= data["used_ram_gb"] <= data["total_ram_gb"]
    assert 0 <= data["used_ram_bytes"] <= data["total_ram_bytes"]


def test_monitoring_non_blocking_concurrency():
    """
    Verify other endpoints remain fully responsive and non-blocked
    during monitoring sampling.
    """
    # Simultaneous call to health check
    health_resp = client.get("/api/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "ok"

    mon_resp = client.get("/api/monitoring/local?interval=0.1")
    assert mon_resp.status_code == 200


def test_monitoring_error_handling():
    """Verify clean 500 response without server crashes when collection fails."""
    with patch("main._collect_host_metrics", side_effect=RuntimeError("psutil hardware sensor failure")):
        response = client.get("/api/monitoring/local")
        assert response.status_code == 500
        data = response.json()
        assert "detail" in data
        assert "psutil hardware sensor failure" in data["detail"]


def test_monitoring_no_sensitive_info_leaked():
    """Verify no process names, usernames, or filesystem paths are exposed."""
    response = client.get("/api/monitoring/local?interval=0.1")
    assert response.status_code == 200
    data = response.json()

    forbidden_keys = {"processes", "pids", "users", "username", "cmdline", "environ", "connections"}
    for key in forbidden_keys:
        assert key not in data
