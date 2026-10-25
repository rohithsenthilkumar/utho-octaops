"""
SQLAlchemy Models for SmartCloud Optimizer (Stage 6)
Multi-Tenant Architecture, VM Ownership, RBAC, Policies, Change Requests, and Audit Trail.
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import relationship
from database import Base


class Company(Base):
    """
    Hosting Company / Tenant entity.
    """
    __tablename__ = "companies"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    tier = Column(String, nullable=False, default="ENTERPRISE")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    users = relationship("User", back_populates="company", cascade="all, delete-orphan")
    resources = relationship("CloudResource", back_populates="company", cascade="all, delete-orphan")
    policies = relationship("ResourcePolicy", back_populates="company", cascade="all, delete-orphan")
    change_requests = relationship("ResourceChangeRequest", back_populates="company", cascade="all, delete-orphan")
    audit_events = relationship("AuditEvent", back_populates="company", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "tier": self.tier,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class User(Base):
    """
    Platform User with tenant association and Role-Based Access Control (RBAC).
    Roles:
      - COMPANY_ADMIN: Full tenant infrastructure management
      - VM_OWNER: Restricted to assigned virtual machines
      - OPTIMIZER_SERVICE: Autonomous optimization engine service account
    """
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="VM_OWNER")  # COMPANY_ADMIN | VM_OWNER | OPTIMIZER_SERVICE
    tenant_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    company = relationship("Company", back_populates="users")
    assigned_resources = relationship("CloudResource", back_populates="owner_user")
    change_requests = relationship("ResourceChangeRequest", back_populates="requester", foreign_keys="ResourceChangeRequest.requester_id")

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "name": self.name,
            "role": self.role,
            "tenant_id": self.tenant_id,
            "company_name": self.company.name if self.company else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class CloudResource(Base):
    """
    Cloud resource model representing compute instances, storage, and networking assets.
    Now extended with tenant isolation and owner association.
    """
    __tablename__ = "cloud_resources"

    id = Column(String, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    resource_type = Column(String, nullable=False, default="VM")
    environment = Column(String, nullable=False, default="prod")
    region = Column(String, nullable=False, default="Bangalore")
    cpu_cores = Column(Integer, nullable=False, default=1)
    memory = Column(Float, nullable=False, default=1.0)  # in GB
    cpu_utilization = Column(Float, nullable=False, default=0.0)  # percentage (0.0 to 100.0)
    estimated_monthly_cost = Column(Float, nullable=False, default=0.0)  # in INR
    status = Column(String, nullable=False, default="ACTIVE")
    owner = Column(String, nullable=True, default="Platform Team")  # Display name / legacy
    is_simulated = Column(Boolean, nullable=False, default=True)
    can_scale_horizontally = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Stage 6: Tenant and Owner foreign keys
    tenant_id = Column(String, ForeignKey("companies.id"), nullable=True, default="tenant-cloudflow", index=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True, index=True)

    # Relationships
    company = relationship("Company", back_populates="resources")
    owner_user = relationship("User", back_populates="assigned_resources")
    policy = relationship("ResourcePolicy", back_populates="resource", uselist=False)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "resource_type": self.resource_type,
            "environment": self.environment,
            "region": self.region,
            "cpu_cores": self.cpu_cores,
            "memory": self.memory,
            "cpu_utilization": self.cpu_utilization,
            "estimated_monthly_cost": self.estimated_monthly_cost,
            "status": self.status,
            "owner": self.owner,
            "owner_id": self.owner_id,
            "tenant_id": self.tenant_id,
            "is_simulated": self.is_simulated,
            "can_scale_horizontally": self.can_scale_horizontally,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ResourcePolicy(Base):
    """
    Defines permitted CPU and Memory bounds, allowed actions, and approval gates.
    Can be defined per-resource or per-tenant.
    """
    __tablename__ = "resource_policies"

    id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    resource_id = Column(String, ForeignKey("cloud_resources.id"), nullable=True, index=True)

    min_cpu_cores = Column(Float, nullable=False, default=1.0)
    max_cpu_cores = Column(Float, nullable=False, default=16.0)
    min_memory_gb = Column(Float, nullable=False, default=1.0)
    max_memory_gb = Column(Float, nullable=False, default=64.0)

    # Replica bounds for horizontally scalable workloads
    min_replicas = Column(Integer, nullable=False, default=1)
    max_replicas = Column(Integer, nullable=False, default=5)
    can_scale_horizontally = Column(Boolean, nullable=False, default=False)

    allow_manual_scaling = Column(Boolean, nullable=False, default=True)
    allow_auto_scaling = Column(Boolean, nullable=False, default=True)
    requires_approval = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    company = relationship("Company", back_populates="policies")
    resource = relationship("CloudResource", back_populates="policy")

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "resource_id": self.resource_id,
            "min_cpu_cores": self.min_cpu_cores,
            "max_cpu_cores": self.max_cpu_cores,
            "min_memory_gb": self.min_memory_gb,
            "max_memory_gb": self.max_memory_gb,
            "min_replicas": self.min_replicas,
            "max_replicas": self.max_replicas,
            "can_scale_horizontally": self.can_scale_horizontally,
            "allow_manual_scaling": self.allow_manual_scaling,
            "allow_auto_scaling": self.allow_auto_scaling,
            "requires_approval": self.requires_approval,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ResourceChangeRequest(Base):
    """
    Change request submitted by a VM Owner when policy requires administrator approval.
    """
    __tablename__ = "resource_change_requests"

    id = Column(String, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    resource_id = Column(String, ForeignKey("cloud_resources.id"), nullable=False, index=True)
    requester_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)

    current_cpu = Column(Float, nullable=False)
    requested_cpu = Column(Float, nullable=False)
    current_memory_gb = Column(Float, nullable=False)
    requested_memory_gb = Column(Float, nullable=False)

    estimated_cost_before = Column(Float, nullable=False, default=0.0)
    estimated_cost_after = Column(Float, nullable=False, default=0.0)
    monthly_cost_diff = Column(Float, nullable=False, default=0.0)

    status = Column(String, nullable=False, default="PENDING")  # PENDING | APPROVED | REJECTED | APPLIED | FAILED
    reason = Column(String, nullable=False)
    reviewer_comment = Column(String, nullable=True)
    reviewed_by = Column(String, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    company = relationship("Company", back_populates="change_requests")
    requester = relationship("User", foreign_keys=[requester_id])
    reviewer = relationship("User", foreign_keys=[reviewed_by])

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "resource_id": self.resource_id,
            "requester_id": self.requester_id,
            "requester_email": self.requester.email if self.requester else None,
            "current_cpu": self.current_cpu,
            "requested_cpu": self.requested_cpu,
            "current_memory_gb": self.current_memory_gb,
            "requested_memory_gb": self.requested_memory_gb,
            "estimated_cost_before": self.estimated_cost_before,
            "estimated_cost_after": self.estimated_cost_after,
            "monthly_cost_diff": self.monthly_cost_diff,
            "status": self.status,
            "reason": self.reason,
            "reviewer_comment": self.reviewer_comment,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditEvent(Base):
    """
    Immutable audit trail for all governance, ownership, policy, and scaling operations.
    """
    __tablename__ = "audit_events"

    id = Column(String, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    actor_id = Column(String, nullable=False)  # User email or system identifier
    actor_role = Column(String, nullable=False)
    tenant_id = Column(String, ForeignKey("companies.id"), nullable=False, index=True)
    resource_id = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False)  # SCALE_VERTICAL | ASSIGN_OWNER | POLICY_UPDATE | CHANGE_REQUEST_APPROVE etc.

    previous_values = Column(Text, nullable=True)  # JSON string
    requested_values = Column(Text, nullable=True)  # JSON string
    resulting_values = Column(Text, nullable=True)  # JSON string

    outcome = Column(String, nullable=False)  # SUCCESS | FAILURE | REJECTED | PENDING_APPROVAL
    reason = Column(Text, nullable=False)

    # Relationships
    company = relationship("Company", back_populates="audit_events")

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "tenant_id": self.tenant_id,
            "resource_id": self.resource_id,
            "action": self.action,
            "previous_values": json.loads(self.previous_values) if self.previous_values else None,
            "requested_values": json.loads(self.requested_values) if self.requested_values else None,
            "resulting_values": json.loads(self.resulting_values) if self.resulting_values else None,
            "outcome": self.outcome,
            "reason": self.reason,
        }
