import pytest
from fastapi.testclient import TestClient
from main import app
from engines.storage_adapter import LocalHostStorageCollector, StorageResizeAdapter
from engines.vertical_scaler import VerticalScalingService

client = TestClient(app)

def test_local_storage_collector():
    collector = LocalHostStorageCollector()
    telemetry = collector.collect_telemetry()
    assert telemetry.mount_point == "/"
    assert telemetry.total_gb > 0
    assert telemetry.free_gb >= 0
    assert 0 <= telemetry.percent_used <= 100
    assert telemetry.status in ("healthy", "warning", "critical")
    assert "psutil" in telemetry.collection_source.lower()

def test_storage_resize_adapter_contract():
    collector = LocalHostStorageCollector()
    status = collector.get_status()
    resizing = status["resizing_capability"]
    assert resizing["status"] == "NOT_CONFIGURED"
    assert resizing["can_auto_expand"] is False
    assert resizing["can_shrink"] is False
    assert "AWS EBS" in str(resizing["supported_cloud_providers"])

def test_api_storage_telemetry_endpoint():
    res = client.get("/api/monitoring/storage")
    assert res.status_code == 200
    data = res.json()
    assert "telemetry" in data
    assert "resizing_capability" in data
    assert data["resizing_capability"]["status"] == "NOT_CONFIGURED"
    assert data["telemetry"]["mount_point"] == "/"

def test_api_docker_workload_telemetry_endpoint():
    res = client.get("/api/monitoring/docker/workload")
    assert res.status_code == 200
    data = res.json()
    assert "container_name" in data
    assert "status" in data
    assert "storage_resizing" in data
    assert data["storage_resizing"] == "NOT_CONFIGURED"
    assert "metric_source" in data
    assert "cgroups" in data["metric_source"] or "docker" in data["metric_source"].lower()

def test_local_monitoring_includes_storage_and_host_id():
    res = client.get("/api/monitoring/local?interval=0.1")
    assert res.status_code == 200
    data = res.json()
    assert "host_id" in data
    assert len(data["host_id"]) >= 8
    assert "disk_total_gb" in data
    assert "disk_used_gb" in data
    assert "disk_free_gb" in data
    assert "storage_resizing" in data
    assert data["storage_resizing"] == "NOT_CONFIGURED"

def test_inspect_container_limits_unconstrained_handling(monkeypatch):
    """Verify that unconstrained containers (NanoCpus=0, Memory=0) are not falsely reported as 2 CPU / 1 GB."""
    import subprocess
    fake_inspect = '{"HostConfig": {"NanoCpus": 0, "Memory": 0}, "State": {"Status": "running"}}'
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: type("CP", (), {"returncode": 0, "stdout": fake_inspect, "stderr": ""})())
    
    service = VerticalScalingService()
    ok, limits, msg = service.inspect_container_limits("autoscaling-lab-app-1")
    assert ok is True
    assert limits["is_unconstrained"] is True
    assert limits["actual_cpu_cores"] is None
    assert limits["actual_memory_gb"] is None
    assert limits["limit_status"] == "UNCONSTRAINED"
