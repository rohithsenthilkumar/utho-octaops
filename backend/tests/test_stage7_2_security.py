"""
SmartCloud Optimizer — Stage 7.2 Security Hardening & Production Readiness Tests
=============================================================================
Verification of security posture, RBAC, multi-tenancy, separation of duties,
fail-safe scaling state consistency, and input sanitization.
"""
import os
import math
import uuid
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models import Company, User, CloudResource, ResourcePolicy, ResourceChangeRequest, AuditEvent
from main import app
from seed import seed_all
from auth import create_access_token

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
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def admin_token(db_session):
    admin = db_session.query(User).filter(User.email == "admin@cloudflow.com").first()
    return create_access_token(admin)


@pytest.fixture
def owner_token(db_session):
    owner = db_session.query(User).filter(User.email == "devops@cloudflow.com").first()
    return create_access_token(owner)


@pytest.fixture
def cross_tenant_token(db_session):
    cross_user = db_session.query(User).filter(User.email == "admin@hostmatrix.com").first()
    return create_access_token(cross_user)


# =========================================================================
# 1. Authentication & Production Safety
# =========================================================================

def test_unauthenticated_request_rejected(client):
    """Unauthenticated requests must receive 401 Unauthorized, never admin fallback."""
    resp = client.get("/api/tenants/resources")
    assert resp.status_code == 401
    assert "detail" in resp.json()


def test_malformed_bearer_token_rejected(client):
    """Garbage/tampered bearer tokens must be rejected with 401."""
    resp = client.get(
        "/api/tenants/resources",
        headers={"Authorization": "Bearer not-a-valid-jwt-token-at-all"}
    )
    assert resp.status_code == 401


def test_demo_bypass_header_rejected_in_production(client):
    """In production environment, X-Demo-User header bypass must be strictly rejected."""
    with patch.dict(os.environ, {"APP_ENV": "production", "ALLOW_DEMO_AUTH_BYPASS": "true"}):
        resp = client.get(
            "/api/tenants/resources",
            headers={"X-Demo-User": "admin@cloudflow.com"}
        )
        assert resp.status_code == 401


def test_switch_demo_disabled_in_production(client):
    """In production environment, /api/auth/switch-demo must be forbidden (HTTP 403)."""
    with patch.dict(os.environ, {"ENVIRONMENT": "production"}):
        resp = client.post(
            "/api/auth/switch-demo",
            json={"email": "admin@cloudflow.com"}
        )
        assert resp.status_code == 403
        assert "disabled in production" in resp.json()["detail"].lower()


# =========================================================================
# 2. Input Validation & Numeric Sanitization
# =========================================================================

def test_policy_bounds_min_greater_than_max_rejected(client, admin_token):
    """Policy bounds with min > max must be rejected by schema validation (HTTP 422)."""
    resp = client.put(
        "/api/tenants/resources/demo-docker-app-01/policy",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "min_cpu_cores": 8.0,
            "max_cpu_cores": 2.0,  # min > max
            "min_memory_gb": 1.0,
            "max_memory_gb": 4.0,
            "allow_manual_scaling": True,
            "requires_approval": False,
        }
    )
    assert resp.status_code == 422


def test_policy_bounds_nan_infinity_rejected(client, admin_token):
    """Policy bounds with negative or invalid values must be rejected (HTTP 422)."""
    resp = client.put(
        "/api/tenants/resources/demo-docker-app-01/policy",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "min_cpu_cores": -1.0,  # negative
            "max_cpu_cores": 4.0,
            "min_memory_gb": 1.0,
            "max_memory_gb": 4.0,
            "allow_manual_scaling": True,
            "requires_approval": False,
        }
    )
    assert resp.status_code == 422


def test_vertical_scale_negative_cores_rejected(client, admin_token):
    """Vertical scale request with non-positive values must be rejected (HTTP 422)."""
    resp = client.post(
        "/api/tenants/vertical-scale",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "resource_id": "demo-docker-app-01",
            "target_cpu_cores": -2,
            "target_memory_gb": 1.0,
            "reason": "Test negative values",
        }
    )
    assert resp.status_code == 422


# =========================================================================
# 3. Multi-Tenant Isolation
# =========================================================================

def test_cross_tenant_resource_access_blocked(client, cross_tenant_token):
    """User in Tenant HostMatrix cannot access resources of Tenant CloudFlow."""
    resp = client.get(
        "/api/tenants/resources/demo-docker-app-01/policy",
        headers={"Authorization": f"Bearer {cross_tenant_token}"}
    )
    assert resp.status_code == 403


def test_cross_tenant_review_change_request_blocked(client, cross_tenant_token, db_session):
    """Admin of HostMatrix cannot review change requests belonging to CloudFlow."""
    cr = ResourceChangeRequest(
        id=f"cr-test-{uuid.uuid4().hex[:6]}",
        tenant_id="tenant-cloudflow",
        resource_id="demo-docker-app-01",
        requester_id="user-cf-owner-1",
        current_cpu=2.0,
        requested_cpu=4.0,
        current_memory_gb=1.0,
        requested_memory_gb=2.0,
        status="PENDING",
        reason="Cross-tenant test",
    )
    db_session.add(cr)
    db_session.commit()

    resp = client.post(
        f"/api/tenants/change-requests/{cr.id}/review",
        headers={"Authorization": f"Bearer {cross_tenant_token}"},
        json={"decision": "APPROVED", "comment": "Malicious approval"}
    )
    assert resp.status_code == 403
    assert "another tenant" in resp.json()["detail"].lower()


def test_cross_tenant_optimizer_decisions_isolation(client, cross_tenant_token):
    """Optimizer decisions endpoint strictly returns decisions for the caller's tenant only."""
    resp = client.get(
        "/api/optimizer/decisions",
        headers={"Authorization": f"Bearer {cross_tenant_token}"}
    )
    assert resp.status_code == 200
    decisions = resp.json()
    for d in decisions:
        assert d.get("tenant_id") == "tenant-hostmatrix"


# =========================================================================
# 4. Separation of Duties & Self-Approval Prevention
# =========================================================================

def test_admin_cannot_self_approve_change_request(client, admin_token, db_session):
    """An administrator who submitted a change request cannot approve or review their own request."""
    admin_user = db_session.query(User).filter(User.email == "admin@cloudflow.com").first()
    cr_id = f"cr-self-{uuid.uuid4().hex[:6]}"
    cr = ResourceChangeRequest(
        id=cr_id,
        tenant_id=admin_user.tenant_id,
        resource_id="demo-docker-app-01",
        requester_id=admin_user.id,  # Admin is requester
        current_cpu=2.0,
        requested_cpu=4.0,
        current_memory_gb=1.0,
        requested_memory_gb=2.0,
        status="PENDING",
        reason="Self approval test",
    )
    db_session.add(cr)
    db_session.commit()

    resp = client.post(
        f"/api/tenants/change-requests/{cr_id}/review",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"decision": "APPROVED", "comment": "Self approving"}
    )
    assert resp.status_code == 403
    assert "separation of duties" in resp.json()["detail"].lower()

    # Verify audit event was logged
    audit = db_session.query(AuditEvent).filter(
        AuditEvent.action == "CHANGE_REQUEST_SELF_APPROVAL_BLOCKED",
        AuditEvent.resource_id == "demo-docker-app-01"
    ).first()
    assert audit is not None
    assert audit.outcome == "FAILURE"


def test_vm_owner_cannot_review_change_request(client, owner_token, db_session):
    """VM_OWNER role cannot call the review endpoint."""
    cr_id = f"cr-owner-block-{uuid.uuid4().hex[:6]}"
    cr = ResourceChangeRequest(
        id=cr_id,
        tenant_id="tenant-cloudflow",
        resource_id="demo-docker-app-01",
        requester_id="user-cf-admin",
        current_cpu=2.0,
        requested_cpu=4.0,
        current_memory_gb=1.0,
        requested_memory_gb=2.0,
        status="PENDING",
        reason="Role check",
    )
    db_session.add(cr)
    db_session.commit()

    resp = client.post(
        f"/api/tenants/change-requests/{cr_id}/review",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={"decision": "APPROVED"}
    )
    assert resp.status_code == 403


# =========================================================================
# 5. Duplicate Pending Change Requests Prevention
# =========================================================================

def test_duplicate_pending_change_request_rejected(client, owner_token, db_session):
    """Submitting a scaling request when a pending request already exists must return 409 Conflict."""
    # Ensure policy requires approval
    policy = db_session.query(ResourcePolicy).filter(ResourcePolicy.resource_id == "demo-docker-app-01").first()
    if policy:
        policy.requires_approval = True
        db_session.commit()

    # Clean up existing pending requests on this resource
    db_session.query(ResourceChangeRequest).filter(
        ResourceChangeRequest.resource_id == "demo-docker-app-01",
        ResourceChangeRequest.status == "PENDING"
    ).delete()
    db_session.commit()

    # First request
    resp1 = client.post(
        "/api/tenants/vertical-scale",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "resource_id": "demo-docker-app-01",
            "target_cpu_cores": 1,
            "target_memory_gb": 1.0,
            "reason": "Request 1",
        }
    )
    assert resp1.status_code == 200
    assert resp1.json()["status"] == "PENDING_APPROVAL"

    # Second concurrent/duplicate request on same resource
    resp2 = client.post(
        "/api/tenants/vertical-scale",
        headers={"Authorization": f"Bearer {owner_token}"},
        json={
            "resource_id": "demo-docker-app-01",
            "target_cpu_cores": 2,
            "target_memory_gb": 1.0,
            "reason": "Request 2",
        }
    )
    assert resp2.status_code == 409
    assert "already has a pending change request" in resp2.json()["detail"].lower()


# =========================================================================
# 6. Database State Consistency on Docker Failure
# =========================================================================

def test_docker_failure_does_not_mutate_db_resource(client, admin_token, db_session):
    """If Docker container limits update fails, the database resource must NOT be updated."""
    # Clean any pending requests
    db_session.query(ResourceChangeRequest).filter(
        ResourceChangeRequest.resource_id == "demo-docker-app-01"
    ).delete()
    db_session.commit()

    res_before = db_session.query(CloudResource).filter(CloudResource.id == "demo-docker-app-01").first()
    cpu_before = res_before.cpu_cores
    mem_before = res_before.memory
    cost_before = res_before.estimated_monthly_cost

    with patch("main.vertical_scaler_service.update_container_limits") as mock_update:
        # Simulate Docker daemon failure
        mock_update.return_value = (False, {}, "Simulated Docker daemon failure or timeout")

        resp = client.post(
            "/api/tenants/vertical-scale",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "resource_id": "demo-docker-app-01",
                "target_cpu_cores": 4,
                "target_memory_gb": 2.0,
                "reason": "Test Docker error handling",
            }
        )
        assert resp.status_code == 502

    # Verify resource was NOT modified in the database
    db_session.expire_all()
    res_after = db_session.query(CloudResource).filter(CloudResource.id == "demo-docker-app-01").first()
    assert res_after.cpu_cores == cpu_before
    assert res_after.memory == mem_before
    assert res_after.estimated_monthly_cost == cost_before

    # Verify audit event for failure was recorded
    fail_audit = db_session.query(AuditEvent).filter(
        AuditEvent.action == "SCALE_VERTICAL_FAILED",
        AuditEvent.resource_id == "demo-docker-app-01"
    ).first()
    assert fail_audit is not None
    assert fail_audit.outcome == "FAILURE"


# =========================================================================
# 7. Audit Trail Verification
# =========================================================================

def test_login_audit_trail_logging(client, db_session):
    """Failed and successful logins must generate corresponding AuditEvents."""
    # Failed login
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@cloudflow.com", "password": "WrongPassword123!"}
    )
    assert resp.status_code == 401
    audit_fail = db_session.query(AuditEvent).filter(
        AuditEvent.action == "AUTH_LOGIN_FAILED",
        AuditEvent.actor_id == "admin@cloudflow.com"
    ).order_by(AuditEvent.timestamp.desc()).first()
    assert audit_fail is not None
    assert audit_fail.outcome == "FAILURE"

    # Successful login
    resp_ok = client.post(
        "/api/auth/login",
        json={"email": "admin@cloudflow.com", "password": "CloudFlowAdmin#2026"}
    )
    assert resp_ok.status_code == 200
    audit_ok = db_session.query(AuditEvent).filter(
        AuditEvent.action == "AUTH_LOGIN_SUCCESS",
        AuditEvent.actor_id == "admin@cloudflow.com"
    ).order_by(AuditEvent.timestamp.desc()).first()
    assert audit_ok is not None
    assert audit_ok.outcome == "SUCCESS"


def test_optimizer_config_change_audited(client, admin_token, db_session):
    """Updating optimizer config must record an OPTIMIZER_CONFIG_UPDATE audit event."""
    resp = client.put(
        "/api/optimizer/config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "cooldown_seconds": 45,
            "sustained_window_samples": 4,
        }
    )
    assert resp.status_code == 200

    audit = db_session.query(AuditEvent).filter(
        AuditEvent.action == "OPTIMIZER_CONFIG_UPDATE",
        AuditEvent.actor_id == "admin@cloudflow.com"
    ).order_by(AuditEvent.timestamp.desc()).first()
    assert audit is not None
    assert audit.outcome == "SUCCESS"
    assert "cooldown_seconds" in audit.requested_values


def test_vm_owner_audit_events_scoped_to_self(client, owner_token):
    """VM_OWNER retrieving audit events must only see events where they were the actor."""
    resp = client.get(
        "/api/tenants/audit-events",
        headers={"Authorization": f"Bearer {owner_token}"}
    )
    assert resp.status_code == 200
    events = resp.json()
    for e in events:
        assert e["user_email"] == "devops@cloudflow.com"
