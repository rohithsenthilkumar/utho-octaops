"""
SmartCloud Optimizer — Stage 6 Seed Data
Seeds Companies, Users, RBAC credentials, Resource Policies, and assigns VMs to owners.
Idempotent and safe to run multiple times without duplicates.
"""
from sqlalchemy.orm import Session
from models import Company, User, CloudResource, ResourcePolicy, AuditEvent
from auth import hash_password

COMPANIES_SEED = [
    {
        "id": "tenant-cloudflow",
        "name": "CloudFlow Hosting",
        "tier": "ENTERPRISE",
    },
    {
        "id": "tenant-hostmatrix",
        "name": "HostMatrix Ltd",
        "tier": "STANDARD",
    },
]

USERS_SEED = [
    {
        "id": "user-cf-admin",
        "email": "admin@cloudflow.com",
        "name": "Rohith (Company Administrator)",
        "password": "CloudFlowAdmin#2026",
        "role": "COMPANY_ADMIN",
        "tenant_id": "tenant-cloudflow",
    },
    {
        "id": "user-cf-owner-1",
        "email": "devops@cloudflow.com",
        "name": "Aarav Sharma (VM Owner - Orders)",
        "password": "DevOpsOwner#2026",
        "role": "VM_OWNER",
        "tenant_id": "tenant-cloudflow",
    },
    {
        "id": "user-cf-owner-2",
        "email": "owner2@cloudflow.com",
        "name": "Priya Nair (VM Owner - Payments)",
        "password": "Owner2Password#2026",
        "role": "VM_OWNER",
        "tenant_id": "tenant-cloudflow",
    },
    {
        "id": "user-hm-admin",
        "email": "admin@hostmatrix.com",
        "name": "Vikram Malhotra (HostMatrix Admin)",
        "password": "HostMatrixAdmin#2026",
        "role": "COMPANY_ADMIN",
        "tenant_id": "tenant-hostmatrix",
    },
    {
        "id": "user-hm-owner",
        "email": "owner@hostmatrix.com",
        "name": "Neha Patel (HostMatrix VM Owner)",
        "password": "HostOwner#2026",
        "role": "VM_OWNER",
        "tenant_id": "tenant-hostmatrix",
    },
]

SIMULATED_RESOURCES_SEED = [
    {
        "id": "vm-blr-prod-01",
        "name": "prod-order-service-01 [Simulated]",
        "resource_type": "VM",
        "environment": "prod",
        "region": "Bangalore",
        "cpu_cores": 16,
        "memory": 64.0,
        "cpu_utilization": 24.5,
        "estimated_monthly_cost": 54000.0,
        "status": "OVER_PROVISIONED",
        "owner": "devops@cloudflow.com",
        "owner_id": "user-cf-owner-1",
        "tenant_id": "tenant-cloudflow",
        "is_simulated": True,
    },
    {
        "id": "vm-bom-prod-02",
        "name": "prod-payment-worker-02 [Simulated]",
        "resource_type": "VM",
        "environment": "prod",
        "region": "Mumbai",
        "cpu_cores": 32,
        "memory": 128.0,
        "cpu_utilization": 48.7,
        "estimated_monthly_cost": 112000.0,
        "status": "OVER_PROVISIONED",
        "owner": "owner2@cloudflow.com",
        "owner_id": "user-cf-owner-2",
        "tenant_id": "tenant-cloudflow",
        "is_simulated": True,
    },
    {
        "id": "vm-del-dev-05",
        "name": "dev-analytics-spark-05 [Simulated]",
        "resource_type": "VM",
        "environment": "dev",
        "region": "Noida",
        "cpu_cores": 32,
        "memory": 128.0,
        "cpu_utilization": 12.3,
        "estimated_monthly_cost": 98000.0,
        "status": "IDLE",
        "owner": "devops@cloudflow.com",
        "owner_id": "user-cf-owner-1",
        "tenant_id": "tenant-cloudflow",
        "is_simulated": True,
    },
    {
        "id": "vm-blr-stg-03",
        "name": "staging-auth-gateway-01 [Simulated]",
        "resource_type": "VM",
        "environment": "staging",
        "region": "Bangalore",
        "cpu_cores": 8,
        "memory": 32.0,
        "cpu_utilization": 18.9,
        "estimated_monthly_cost": 28000.0,
        "status": "OVER_PROVISIONED",
        "owner": "Security Team (Unassigned)",
        "owner_id": None,
        "tenant_id": "tenant-cloudflow",
        "is_simulated": True,
    },
    {
        "id": "vm-bom-prod-09",
        "name": "prod-db-replica-bom-03 [Simulated]",
        "resource_type": "VM",
        "environment": "prod",
        "region": "Mumbai",
        "cpu_cores": 64,
        "memory": 256.0,
        "cpu_utilization": 78.4,
        "estimated_monthly_cost": 215000.0,
        "status": "ACTIVE",
        "owner": "Database Admins (Unassigned)",
        "owner_id": None,
        "tenant_id": "tenant-cloudflow",
        "is_simulated": True,
    },
    # Cross-tenant resource in HostMatrix Ltd
    {
        "id": "vm-hm-prod-01",
        "name": "hostmatrix-api-01 [Simulated]",
        "resource_type": "VM",
        "environment": "prod",
        "region": "Mumbai",
        "cpu_cores": 4,
        "memory": 16.0,
        "cpu_utilization": 35.0,
        "estimated_monthly_cost": 16000.0,
        "status": "ACTIVE",
        "owner": "owner@hostmatrix.com",
        "owner_id": "user-hm-owner",
        "tenant_id": "tenant-hostmatrix",
        "is_simulated": True,
    },
    # Docker demo workload mapped to CloudFlow
    {
        "id": "demo-docker-app-01",
        "name": "autoscaling-lab-app-1 [Docker Workload]",
        "resource_type": "Docker Container",
        "environment": "dev",
        "region": "Bangalore",
        "cpu_cores": 2,
        "memory": 1.0,
        "cpu_utilization": 0.5,
        "estimated_monthly_cost": 1800.0,
        "status": "ACTIVE",
        "owner": "devops@cloudflow.com",
        "owner_id": "user-cf-owner-1",
        "tenant_id": "tenant-cloudflow",
        "is_simulated": False,
        "can_scale_horizontally": True,
    },
]

POLICIES_SEED = [
    {
        "id": "policy-default-cloudflow",
        "tenant_id": "tenant-cloudflow",
        "resource_id": None,  # Tenant default
        "min_cpu_cores": 1.0,
        "max_cpu_cores": 32.0,
        "min_memory_gb": 1.0,
        "max_memory_gb": 128.0,
        "allow_manual_scaling": True,
        "requires_approval": False,
        "can_scale_horizontally": False,
    },
    {
        "id": "policy-vm-blr-prod-01",
        "tenant_id": "tenant-cloudflow",
        "resource_id": "vm-blr-prod-01",
        "min_cpu_cores": 4.0,
        "max_cpu_cores": 16.0,
        "min_memory_gb": 16.0,
        "max_memory_gb": 64.0,
        "allow_manual_scaling": True,
        "requires_approval": True,  # Production order service requires approval
        "can_scale_horizontally": False,
    },
    {
        "id": "policy-docker-demo",
        "tenant_id": "tenant-cloudflow",
        "resource_id": "demo-docker-app-01",
        "min_cpu_cores": 0.5,
        "max_cpu_cores": 4.0,
        "min_memory_gb": 0.25,
        "max_memory_gb": 4.0,
        "min_replicas": 1,
        "max_replicas": 5,
        "can_scale_horizontally": True,
        "allow_manual_scaling": True,
        "requires_approval": False,  # Immediate self-service scaling permitted for lab
    },
    {
        "id": "policy-default-hostmatrix",
        "tenant_id": "tenant-hostmatrix",
        "resource_id": None,
        "min_cpu_cores": 1.0,
        "max_cpu_cores": 16.0,
        "min_memory_gb": 1.0,
        "max_memory_gb": 32.0,
        "allow_manual_scaling": True,
        "requires_approval": True,
    },
]


def seed_all(db: Session) -> dict:
    """Idempotent seed for tenants, users, resources, and policies."""
    # 1. Seed Companies
    for item in COMPANIES_SEED:
        existing = db.query(Company).filter(Company.id == item["id"]).first()
        if not existing:
            db.add(Company(**item))
    db.commit()

    # 2. Seed Users
    for item in USERS_SEED:
        existing = db.query(User).filter(User.id == item["id"]).first()
        pwd_hash = hash_password(item["password"])
        if not existing:
            db.add(User(
                id=item["id"],
                email=item["email"],
                name=item["name"],
                password_hash=pwd_hash,
                role=item["role"],
                tenant_id=item["tenant_id"],
                is_active=True,
            ))
        else:
            existing.password_hash = pwd_hash
            existing.email = item["email"]
            existing.role = item["role"]
            existing.name = item["name"]
    db.commit()

    # 3. Seed Resources
    inserted = 0
    updated = 0
    for item in SIMULATED_RESOURCES_SEED:
        existing = db.query(CloudResource).filter(CloudResource.id == item["id"]).first()
        if not existing:
            db.add(CloudResource(**item))
            inserted += 1
        else:
            for k, v in item.items():
                setattr(existing, k, v)
            updated += 1
    db.commit()

    # 4. Seed Policies
    for item in POLICIES_SEED:
        existing = db.query(ResourcePolicy).filter(ResourcePolicy.id == item["id"]).first()
        if not existing:
            db.add(ResourcePolicy(**item))
        else:
            for k, v in item.items():
                setattr(existing, k, v)
    db.commit()

    total_resources = db.query(CloudResource).count()

    # Return summary with backward-compatible keys
    return {
        "inserted": inserted,
        "updated": updated,
        "total": total_resources,
        "companies": db.query(Company).count(),
        "users": db.query(User).count(),
        "resources": total_resources,
        "policies": db.query(ResourcePolicy).count(),
    }


def seed_resources(db: Session) -> dict:
    """Wrapper for backward compatibility."""
    return seed_all(db)


if __name__ == "__main__":
    from database import SessionLocal, init_db
    init_db()
    with SessionLocal() as session:
        res = seed_all(session)
        print(f"Stage 6 Multi-tenant seed executed successfully: {res}")
