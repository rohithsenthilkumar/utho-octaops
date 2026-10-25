"""
Comprehensive Pytest Suite for SmartCloud Optimizer Stage 2 Backend
Tests: Health, Resources List, Single Resource, Resource Creation, Input Validation, and Idempotent Seeding.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool
from database import Base, get_db
from main import app
from models import CloudResource
from seed import seed_resources

# Use an isolated in-memory SQLite database with StaticPool for test predictability
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
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


# ---- 1. Health Check Tests ----

def test_health_endpoint(client):
    """Verify GET /api/health reports Stage 2 status, database connectivity, and resource count."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "SmartCloud Optimizer API"
    assert data["stage"] >= 2
    assert data["database"] == "connected"
    assert data["resources_count"] >= 5


# ---- 2. Resources List & Detail Tests ----

def test_get_resources(client):
    """Verify GET /api/resources returns the seeded simulated resources with all required model fields."""
    response = client.get("/api/resources")
    assert response.status_code == 200
    resources = response.json()
    assert len(resources) >= 5

    # Check required model fields
    first = resources[0]
    required_fields = [
        "id", "name", "resource_type", "environment", "region",
        "cpu_cores", "memory", "cpu_utilization", "estimated_monthly_cost",
        "status", "is_simulated"
    ]
    for field in required_fields:
        assert field in first, f"Missing field {field} in resource response"

    assert first["is_simulated"] is True


def test_get_resource_by_id(client):
    """Verify GET /api/resources/{id} retrieves a specific resource."""
    response = client.get("/api/resources/vm-blr-prod-01")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "vm-blr-prod-01"
    assert data["region"] == "Bangalore"
    assert data["environment"] == "prod"
    assert data["cpu_cores"] == 16


def test_get_resource_not_found(client):
    """Verify GET /api/resources/{id} returns 404 for non-existent resource."""
    response = client.get("/api/resources/non-existent-vm-999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# ---- 3. Filtering Tests ----

def test_filter_resources_by_region(client):
    """Verify filtering resources by region returns only matching records."""
    response = client.get("/api/resources?region=Bangalore")
    assert response.status_code == 200
    items = response.json()
    assert len(items) > 0
    assert all(item["region"] == "Bangalore" for item in items)


def test_filter_resources_by_environment(client):
    """Verify filtering resources by environment returns only matching records."""
    response = client.get("/api/resources?environment=dev")
    assert response.status_code == 200
    items = response.json()
    assert len(items) > 0
    assert all(item["environment"] == "dev" for item in items)


# ---- 4. Resource Creation (POST) & Input Validation Tests ----

def test_create_resource_valid(client):
    """Verify POST /api/resources successfully persists a valid resource and returns 201."""
    payload = {
        "id": "vm-bom-dev-test01",
        "name": "test-analytics-worker-01 [Simulated]",
        "resource_type": "VM",
        "environment": "dev",
        "region": "Mumbai",
        "cpu_cores": 8,
        "memory": 32.0,
        "cpu_utilization": 15.5,
        "estimated_monthly_cost": 24500.0,
        "status": "ACTIVE",
        "owner": "Test Team",
        "is_simulated": True,
    }
    response = client.post("/api/resources", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["id"] == "vm-bom-dev-test01"
    assert created["name"] == payload["name"]
    assert created["cpu_cores"] == 8
    assert created["memory"] == 32.0
    assert created["estimated_monthly_cost"] == 24500.0

    # Verify it can be retrieved
    get_res = client.get("/api/resources/vm-bom-dev-test01")
    assert get_res.status_code == 200


def test_create_resource_auto_id(client):
    """Verify POST /api/resources auto-generates an ID when none is provided."""
    payload = {
        "name": "auto-id-service [Simulated]",
        "resource_type": "VM",
        "environment": "staging",
        "region": "Noida",
        "cpu_cores": 4,
        "memory": 16.0,
        "cpu_utilization": 22.0,
        "estimated_monthly_cost": 14000.0,
    }
    response = client.post("/api/resources", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["id"] is not None
    assert "vm-noi-sta-" in created["id"]


def test_create_resource_duplicate_id_conflict(client):
    """Verify attempting to create a resource with an already existing ID returns 409 Conflict."""
    payload = {
        "id": "vm-blr-prod-01",  # already exists in seed
        "name": "duplicate-worker",
        "resource_type": "VM",
        "environment": "prod",
        "region": "Bangalore",
        "cpu_cores": 8,
        "memory": 32.0,
        "cpu_utilization": 20.0,
        "estimated_monthly_cost": 30000.0,
    }
    response = client.post("/api/resources", json=payload)
    assert response.status_code == 409
    assert "already exists" in response.json()["detail"].lower()


def test_validation_missing_name(client):
    """Verify validation error when resource name is missing."""
    payload = {
        "resource_type": "VM",
        "environment": "prod",
        "region": "Bangalore",
        "cpu_cores": 4,
        "memory": 16.0,
        "cpu_utilization": 10.0,
        "estimated_monthly_cost": 15000.0,
    }
    response = client.post("/api/resources", json=payload)
    assert response.status_code == 422


def test_validation_negative_cpu_cores(client):
    """Verify validation error when cpu_cores is zero or negative."""
    payload = {
        "name": "invalid-cpu-worker",
        "resource_type": "VM",
        "environment": "prod",
        "region": "Bangalore",
        "cpu_cores": 0,  # Invalid: min 1
        "memory": 16.0,
        "cpu_utilization": 10.0,
        "estimated_monthly_cost": 15000.0,
    }
    response = client.post("/api/resources", json=payload)
    assert response.status_code == 422


def test_validation_invalid_environment(client):
    """Verify validation error when environment is unrecognized."""
    payload = {
        "name": "invalid-env-worker",
        "resource_type": "VM",
        "environment": "invalid-env-name",
        "region": "Bangalore",
        "cpu_cores": 4,
        "memory": 16.0,
        "cpu_utilization": 10.0,
        "estimated_monthly_cost": 15000.0,
    }
    response = client.post("/api/resources", json=payload)
    assert response.status_code == 422


def test_validation_invalid_region(client):
    """Verify validation error when region is unrecognized."""
    payload = {
        "name": "invalid-region-worker",
        "resource_type": "VM",
        "environment": "prod",
        "region": "us-east-1",  # Invalid for Indian SaaS footprint
        "cpu_cores": 4,
        "memory": 16.0,
        "cpu_utilization": 10.0,
        "estimated_monthly_cost": 15000.0,
    }
    response = client.post("/api/resources", json=payload)
    assert response.status_code == 422


# ---- 5. Idempotent Seeding Test ----

def test_repeatable_seeding_no_duplicates():
    """Verify calling seed_resources multiple times maintains seeded resources without duplicates."""
    from seed import SIMULATED_RESOURCES_SEED
    expected_count = len(SIMULATED_RESOURCES_SEED)

    mem_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=mem_engine)
    MemSession = sessionmaker(autocommit=False, autoflush=False, bind=mem_engine)

    with MemSession() as session:
        # Run 1: Should insert all initial resources
        res1 = seed_resources(session)
        assert res1["inserted"] == expected_count
        assert res1["total"] == expected_count

        # Run 2: Should insert 0, update all, total remains expected_count
        res2 = seed_resources(session)
        assert res2["inserted"] == 0
        assert res2["updated"] == expected_count
        assert res2["total"] == expected_count

        # Run 3: Repeat again
        res3 = seed_resources(session)
        assert res3["inserted"] == 0
        assert res3["total"] == expected_count


# ---- 6. Dashboard Summary & Rightsizing Regression Tests ----

def test_dashboard_summary_endpoint(client):
    """Verify GET /api/dashboard/summary returns HTTP 200 and matches the expected schema."""
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    data = response.json()

    expected_keys = [
        "total_resources",
        "current_monthly_cost",
        "projected_cost",
        "total_savings",
        "savings_percentage",
        "total_recommendations",
        "accepted_recommendations",
        "pending_recommendations",
        "rejected_recommendations",
        "idle_resources_count",
    ]
    for key in expected_keys:
        assert key in data, f"Key '{key}' missing from dashboard summary"

    assert data["total_resources"] > 0
    assert data["current_monthly_cost"] > 0
    assert data["projected_cost"] <= data["current_monthly_cost"]
    assert 0 <= data["savings_percentage"] <= 100
    assert data["total_recommendations"] >= 0


def test_dashboard_summary_empty_database():
    """Verify dashboard summary safely handles an empty database without exceptions."""
    from main import get_dashboard_summary

    mem_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=mem_engine)
    MemSession = sessionmaker(autocommit=False, autoflush=False, bind=mem_engine)

    with MemSession() as session:
        data = get_dashboard_summary(db=session)
        assert data["total_resources"] == 0
        assert data["current_monthly_cost"] == 0.0
        assert data["projected_cost"] == 0.0
        assert data["total_savings"] == 0.0
        assert data["savings_percentage"] == 0.0
        assert data["total_recommendations"] == 0
        assert data["accepted_recommendations"] == 0
        assert data["pending_recommendations"] == 0
        assert data["rejected_recommendations"] == 0
        assert data["idle_resources_count"] == 0


def test_rightsizing_programmatic_call_without_query_params():
    """
    Regression test for root-cause bug:
    Calling get_rightsizing_recommendations directly in Python with only db=session
    must NOT fail with AttributeError: 'Query' object has no attribute 'lower'.
    """
    from main import get_rightsizing_recommendations

    with TestingSessionLocal() as session:
        # Direct Python call without query params
        recs = get_rightsizing_recommendations(db=session)
        assert isinstance(recs, list)
        assert len(recs) > 0
        for r in recs:
            assert "recommendation_id" in r
            assert "estimated_inr_savings" in r

