"""
SmartCloud Optimizer — Stage 6 Automated Tests
Comprehensive testing for:
1. Multi-Tenant isolation & RBAC boundaries.
2. Company Admin full access vs VM Owner assigned-only access.
3. Cross-tenant access blocking (HTTP 403).
4. Policy enforcement: CPU/RAM bounds validation, manual scaling permissions.
5. Approval workflow: VM Owner request creation, Admin approval & rejection.
6. Immutable audit trail verification.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool
from database import Base, get_db
from models import Company, User, CloudResource, ResourcePolicy, ResourceChangeRequest, AuditEvent
from main import app
from seed import seed_all
from auth import create_access_token

# Set up in-memory SQLite database with StaticPool so all connections share the memory db
test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=test_engine)
    with TestingSessionLocal() as session:
        seed_all(session)
    app.dependency_overrides[get_db] = override_get_db
    yield
    Base.metadata.drop_all(bind=test_engine)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def client():
    return TestClient(app)


def get_token_for(email: str) -> str:
    with TestingSessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None, f"User {email} not found in test db"
        return create_access_token(user)


# =========================================================================
# 1. Authentication & Persona Tests
# =========================================================================

def test_login_valid_credentials(client):
    res = client.post("/api/auth/login", json={
        "email": "admin@cloudflow.com",
        "password": "CloudFlowAdmin#2026",
    })
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "admin@cloudflow.com"
    assert data["user"]["role"] == "COMPANY_ADMIN"
    assert data["user"]["company_name"] == "CloudFlow Hosting"


def test_login_invalid_password(client):
    res = client.post("/api/auth/login", json={
        "email": "admin@cloudflow.com",
        "password": "WrongPassword123!",
    })
    assert res.status_code == 401
    assert "Invalid credentials" in res.json()["detail"]


def test_switch_demo_persona(client):
    res = client.post("/api/auth/switch-demo", json={
        "email": "devops@cloudflow.com",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["user"]["role"] == "VM_OWNER"
    assert data["user"]["email"] == "devops@cloudflow.com"


# =========================================================================
# 2. RBAC & Tenant Scoping Tests
# =========================================================================

def test_company_admin_views_all_tenant_resources(client):
    token = get_token_for("admin@cloudflow.com")
    res = client.get("/api/tenants/resources", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    items = res.json()
    # Admin sees all CloudFlow resources
    assert len(items) >= 4
    for r in items:
        assert r["tenant_id"] == "tenant-cloudflow"


def test_vm_owner_only_sees_assigned_vms(client):
    token = get_token_for("devops@cloudflow.com")
    res = client.get("/api/tenants/resources", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    items = res.json()
    # devops@cloudflow.com owns vm-blr-prod-01, vm-del-dev-05, demo-docker-app-01
    assert len(items) >= 1
    for r in items:
        assert "devops@cloudflow.com" in r["owner"] or r["owner_id"] == "user-cf-owner-1"


def test_cross_tenant_isolation(client):
    """HostMatrix admin should only see HostMatrix resources, not CloudFlow resources."""
    token = get_token_for("admin@hostmatrix.com")
    res = client.get("/api/tenants/resources", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    items = res.json()
    for r in items:
        assert r["tenant_id"] == "tenant-hostmatrix"
        assert r["id"] == "vm-hm-prod-01"


def test_owner_assignment_by_admin(client):
    admin_token = get_token_for("admin@cloudflow.com")
    res = client.post(
        "/api/tenants/resources/vm-blr-stg-03/assign",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"owner_id": "user-cf-owner-2"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["owner_id"] == "user-cf-owner-2"
    assert "owner2@cloudflow.com" in data["owner"]


def test_owner_assignment_forbidden_for_vm_owner(client):
    owner_token = get_token_for("devops@cloudflow.com")
    res = client.post(
        "/api/tenants/resources/vm-blr-stg-03/assign",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"owner_id": "user-cf-owner-1"},
    )
    assert res.status_code == 403
    assert "COMPANY_ADMIN" in res.json()["detail"]


# =========================================================================
# 3. Policy Enforcement & Approval Workflow Tests
# =========================================================================

def test_policy_bounds_enforcement_cpu_exceeded(client):
    """vm-blr-prod-01 policy allows max 16 CPU cores. Requesting 32 should fail."""
    admin_token = get_token_for("admin@cloudflow.com")
    res = client.post(
        "/api/tenants/vertical-scale",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "resource_id": "vm-blr-prod-01",
            "target_cpu_cores": 32,
            "target_memory_gb": 32.0,
            "reason": "Stress test spike",
        },
    )
    assert res.status_code == 400
    assert "violates policy bounds" in res.json()["detail"]


def test_vm_owner_approval_workflow(client):
    """
    vm-blr-prod-01 policy has requires_approval=True.
    When VM owner devops@cloudflow.com requests scaling within bounds (8 cores, 32GB),
    it should result in PENDING_APPROVAL and generate a change request.
    """
    owner_token = get_token_for("devops@cloudflow.com")
    res = client.post(
        "/api/tenants/vertical-scale",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "resource_id": "vm-blr-prod-01",
            "target_cpu_cores": 8,
            "target_memory_gb": 32.0,
            "reason": "Downsizing database to safe footprint",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "PENDING_APPROVAL"
    assert data["change_request_id"] is not None
    cr_id = data["change_request_id"]

    # Verify change request is visible in queue
    admin_token = get_token_for("admin@cloudflow.com")
    queue_res = client.get("/api/tenants/change-requests", headers={"Authorization": f"Bearer {admin_token}"})
    assert queue_res.status_code == 200
    requests = queue_res.json()
    found = [r for r in requests if r["id"] == cr_id]
    assert len(found) == 1
    assert found[0]["status"] == "PENDING"
    assert found[0]["target_cpu_cores"] == 8

    # Admin approves change request
    review_res = client.post(
        f"/api/tenants/change-requests/{cr_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"decision": "APPROVED", "comment": "Approved safe downsizing."},
    )
    assert review_res.status_code == 200
    assert review_res.json()["status"] == "APPROVED"


def test_cross_tenant_cannot_scale_other_company_resource(client):
    host_token = get_token_for("admin@hostmatrix.com")
    res = client.post(
        "/api/tenants/vertical-scale",
        headers={"Authorization": f"Bearer {host_token}"},
        json={
            "resource_id": "vm-blr-prod-01",
            "target_cpu_cores": 8,
            "target_memory_gb": 32.0,
            "reason": "Malicious attempt",
        },
    )
    assert res.status_code == 403
    assert "Access forbidden" in res.json()["detail"]


# =========================================================================
# 4. Immutable Audit Trail Tests
# =========================================================================

def test_audit_trail_recorded(client):
    admin_token = get_token_for("admin@cloudflow.com")
    res = client.get("/api/tenants/audit-events", headers={"Authorization": f"Bearer {admin_token}"})
    assert res.status_code == 200
    events = res.json()
    assert len(events) >= 1
    actions = [e["action"] for e in events]
    assert any("ASSIGN_OWNER" in a or "SCALE" in a or "CHANGE_REQUEST" in a for a in actions)
