"""
Unit Tests for Stage 3 Deterministic Rightsizing Engine
Tests: Safe Downsizing, High Utilization, Insufficient Metrics, Savings Calculations, and API Endpoint.
"""
from datetime import datetime, timezone, timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import CloudResource
from seed import seed_resources
from engines.rightsizing import RightsizingEngine, analyze_metrics, MIN_DATA_POINTS

# In-memory test database with StaticPool
TEST_DB_URL = "sqlite:///:memory:"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def init_test_db():
    Base.metadata.create_all(bind=test_engine)
    with TestingSessionLocal() as session:
        seed_resources(session)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client():
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def make_synthetic_metrics(count: int, avg_cpu: float, p95_cpu: float, avg_ram: float, p95_ram: float):
    """Generates synthetic hourly metrics for unit tests."""
    records = []
    now = datetime.now(timezone.utc)
    for i in range(count):
        # 5% of hours spike up to p95
        is_peak = (i % 20 == 0)
        cpu_val = p95_cpu if is_peak else avg_cpu
        ram_val = p95_ram if is_peak else avg_ram
        records.append({
            "timestamp": (now - timedelta(hours=i)).isoformat(),
            "cpu_percent": cpu_val,
            "ram_percent": ram_val,
            "disk_percent": 30.0,
            "disk_iops": 150,
            "network_in_kbps": 200.0,
            "network_out_kbps": 300.0,
        })
    return records


# ------------------------------------------------------------------ #
#  1. Safe Downsizing Tests                                          #
# ------------------------------------------------------------------ #

def test_safe_downsizing():
    """
    When CPU and memory metrics show low utilization with sufficient headroom,
    engine recommends a smaller, cheaper instance configuration.
    """
    engine = RightsizingEngine()
    resource = {
        "id": "vm-test-overprovisioned",
        "name": "checkout-service-01 [Simulated]",
        "environment": "prod",
        "region": "Bangalore",
        "cpu_cores": 16,
        "memory": 64.0,
        "estimated_monthly_cost": 54000.0,
    }

    # Low usage: p95 CPU 20%, p95 RAM 30% over 168 hours (7 days)
    metrics = make_synthetic_metrics(168, avg_cpu=12.0, p95_cpu=20.0, avg_ram=22.0, p95_ram=30.0)
    rec = engine.evaluate_resource(resource, metrics)

    assert rec["action"] == "DOWNSIZE"
    assert rec["status"] == "RECOMMENDED"
    assert rec["proposed_configuration"] is not None

    # Target configuration must be smaller in cores/RAM and cheaper
    proposed = rec["proposed_configuration"]
    assert proposed["vcpu"] < resource["cpu_cores"]
    assert proposed["ram_gb"] <= resource["memory"]
    assert proposed["monthly_cost_inr"] < resource["estimated_monthly_cost"]

    # Cost before vs after and savings
    assert rec["estimated_monthly_cost_before"] == 54000.0
    assert rec["estimated_monthly_cost_after"] < 54000.0
    assert rec["estimated_inr_savings"] > 0.0
    assert rec["savings_percentage"] > 0.0

    # Evidence details
    assert "p95_cpu" in rec["evidence"]
    assert "safety_buffer_pct" in rec["evidence"]
    assert rec["evidence"]["safety_buffer_pct"] == 25  # 25% for prod
    assert rec["is_simulated"] is True


# ------------------------------------------------------------------ #
#  2. High Utilization / Headroom Protection Tests                   #
# ------------------------------------------------------------------ #

def test_high_utilization_prevents_downsizing():
    """
    When p95 or peak utilization is high, the engine refuses to downsize,
    protecting production stability.
    """
    engine = RightsizingEngine()
    resource = {
        "id": "vm-test-high-load",
        "name": "database-replica-01 [Simulated]",
        "environment": "prod",
        "region": "Mumbai",
        "cpu_cores": 32,
        "memory": 128.0,
        "estimated_monthly_cost": 110000.0,
    }

    # High load: p95 CPU is 82%, p95 RAM is 88%
    metrics = make_synthetic_metrics(168, avg_cpu=65.0, p95_cpu=82.0, avg_ram=75.0, p95_ram=88.0)
    rec = engine.evaluate_resource(resource, metrics)

    assert rec["action"] == "KEEP_CURRENT"
    assert rec["status"] == "HIGH_UTILIZATION"
    assert rec["risk_level"] == "HIGH"
    assert rec["estimated_inr_savings"] == 0.0
    assert rec["savings_percentage"] == 0.0
    assert "High utilization detected" in rec["justification"]


# ------------------------------------------------------------------ #
#  3. Insufficient Metrics Tests                                     #
# ------------------------------------------------------------------ #

def test_insufficient_metrics_empty():
    """When metrics list is empty, engine returns 'insufficient data' rather than guessing."""
    engine = RightsizingEngine()
    resource = {
        "id": "vm-test-empty",
        "name": "new-microservice-01 [Simulated]",
        "environment": "dev",
        "region": "Noida",
        "cpu_cores": 8,
        "memory": 32.0,
        "estimated_monthly_cost": 25000.0,
    }

    rec = engine.evaluate_resource(resource, [])
    assert rec["action"] == "INSUFFICIENT_DATA"
    assert rec["status"] == "INSUFFICIENT_DATA"
    assert rec["proposed_configuration"] is None
    assert rec["estimated_inr_savings"] == 0.0
    assert "insufficient data" in rec["evidence"]["status"].lower()
    assert rec["evidence"]["min_required_samples"] == MIN_DATA_POINTS


def test_insufficient_metrics_sparse_samples():
    """When metrics have fewer than 24 samples (e.g. only 6 hours), engine returns 'insufficient data'."""
    engine = RightsizingEngine()
    resource = {
        "id": "vm-test-sparse",
        "name": "fresh-vm-01 [Simulated]",
        "environment": "staging",
        "region": "Bangalore",
        "cpu_cores": 4,
        "memory": 16.0,
        "estimated_monthly_cost": 12000.0,
    }

    # Only 8 samples (< 24 required)
    sparse_metrics = make_synthetic_metrics(8, avg_cpu=10.0, p95_cpu=15.0, avg_ram=20.0, p95_ram=25.0)
    rec = engine.evaluate_resource(resource, sparse_metrics)

    assert rec["action"] == "INSUFFICIENT_DATA"
    assert rec["status"] == "INSUFFICIENT_DATA"
    assert rec["proposed_configuration"] is None
    assert rec["evidence"]["sample_count"] == 8
    assert "refuse" in rec["justification"].lower() or "insufficient" in rec["justification"].lower()


# ------------------------------------------------------------------ #
#  4. Savings Calculation Accuracy Tests                            #
# ------------------------------------------------------------------ #

def test_savings_calculation_accuracy():
    """
    Verifies that cost before - cost after strictly equals estimated_inr_savings
    and savings_percentage is calculated accurately.
    """
    engine = RightsizingEngine()
    resource = {
        "id": "vm-calc-test",
        "name": "calc-verifier-01 [Simulated]",
        "environment": "dev",
        "region": "Noida",
        "cpu_cores": 32,
        "memory": 128.0,
        "estimated_monthly_cost": 98000.0,
    }

    # Dev environment with 10% load -> large downsizing candidate
    metrics = make_synthetic_metrics(168, avg_cpu=5.0, p95_cpu=9.5, avg_ram=12.0, p95_ram=18.0)
    rec = engine.evaluate_resource(resource, metrics)

    assert rec["action"] == "DOWNSIZE"

    cost_before = rec["estimated_monthly_cost_before"]
    cost_after = rec["estimated_monthly_cost_after"]
    savings = rec["estimated_inr_savings"]
    pct = rec["savings_percentage"]

    # Exact arithmetic checks
    assert round(cost_before - cost_after, 2) == round(savings, 2)
    expected_pct = round((savings / cost_before) * 100, 1)
    assert pct == expected_pct
    assert cost_after < cost_before
    assert savings > 0.0


# ------------------------------------------------------------------ #
#  5. API Endpoint Tests (GET /api/recommendations/rightsizing)      #
# ------------------------------------------------------------------ #

def test_api_rightsizing_endpoint(client):
    """
    Verifies GET /api/recommendations/rightsizing returns valid recommendation objects
    with all required fields clearly labelled as simulated.
    """
    response = client.get("/api/recommendations/rightsizing")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1

    first = data[0]
    required_keys = [
        "recommendation_id",
        "resource_id",
        "resource_name",
        "action",
        "status",
        "risk_level",
        "current_configuration",
        "evidence",
        "estimated_monthly_cost_before",
        "estimated_monthly_cost_after",
        "estimated_inr_savings",
        "savings_percentage",
        "justification",
        "is_simulated",
    ]
    for key in required_keys:
        assert key in first, f"Missing key {key} in recommendation output"

    assert first["is_simulated"] is True
    assert first["current_configuration"]["vcpu"] > 0
    assert first["current_configuration"]["ram_gb"] > 0


def test_api_rightsizing_insufficient_resource(client):
    """
    Verifies that a resource marked as insufficient returns the 'insufficient data' recommendation.
    """
    # Create a resource with 'insufficient' in the name
    client.post("/api/resources", json={
        "id": "vm-insufficient-data-test",
        "name": "sparse-metrics-instance [Simulated]",
        "resource_type": "VM",
        "environment": "staging",
        "region": "Bangalore",
        "cpu_cores": 8,
        "memory": 32.0,
        "cpu_utilization": 20.0,
        "estimated_monthly_cost": 25000.0,
    })

    response = client.get("/api/recommendations/rightsizing?resource_id=vm-insufficient-data-test")
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    rec = results[0]
    assert rec["action"] == "INSUFFICIENT_DATA"
    assert rec["status"] == "INSUFFICIENT_DATA"
    assert rec["proposed_configuration"] is None
