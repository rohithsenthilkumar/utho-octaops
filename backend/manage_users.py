#!/usr/bin/env python3
"""
SmartCloud Optimizer — User & Administrator Account Management CLI
Provides explicit operator actions for account setup, verification, and password resets.
Does not invent credentials or hardcode passwords.
"""
import sys
import os
import uuid
from datetime import datetime, timezone

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal
from models import User, Company, AuditEvent
from auth import hash_password, verify_password


def print_usage():
    print("SmartCloud Optimizer User Management CLI")
    print("Usage:")
    print("  python3 manage_users.py list")
    print("  python3 manage_users.py reset-password <email> <new_password>")
    print("  python3 manage_users.py create-admin <email> <password> <full_name> [tenant_id]")
    print("  python3 manage_users.py verify <email> <password>")


def list_users():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        print(f"\nTotal Registered Users: {len(users)}")
        print("-" * 80)
        print(f"{'Email':<28} | {'Role':<16} | {'Tenant ID':<18} | {'Active':<6} | {'Name'}")
        print("-" * 80)
        for u in users:
            print(f"{u.email:<28} | {u.role:<16} | {u.tenant_id:<18} | {str(u.is_active):<6} | {u.name}")
        print("-" * 80)
    finally:
        db.close()


def reset_password(email: str, new_password: str):
    if not new_password or len(new_password) < 8:
        print("[ERROR] Password must be at least 8 characters long.")
        sys.exit(1)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email.strip().lower()).first()
        if not user:
            print(f"[ERROR] User with email '{email}' not found.")
            sys.exit(1)

        new_hash = hash_password(new_password)
        user.password_hash = new_hash

        audit = AuditEvent(
            id=f"audit-{uuid.uuid4().hex[:12]}",
            actor_id="operator-cli",
            actor_role="OPERATOR",
            tenant_id=user.tenant_id,
            action="USER_PASSWORD_RESET_CLI",
            outcome="SUCCESS",
            reason=f"Operator manually reset password for user '{user.email}' via CLI",
        )
        db.add(audit)
        db.commit()
        print(f"[SUCCESS] Password for '{user.email}' ({user.role}) has been securely reset.")
    finally:
        db.close()


def create_admin(email: str, password: str, full_name: str, tenant_id: str = "tenant-cloudflow"):
    if not password or len(password) < 8:
        print("[ERROR] Password must be at least 8 characters long.")
        sys.exit(1)

    db = SessionLocal()
    try:
        email_clean = email.strip().lower()
        existing = db.query(User).filter(User.email == email_clean).first()
        if existing:
            print(f"[ERROR] User with email '{email_clean}' already exists.")
            sys.exit(1)

        company = db.query(Company).filter(Company.id == tenant_id).first()
        if not company:
            print(f"[WARNING] Tenant '{tenant_id}' does not exist, creating standard company...")
            company = Company(id=tenant_id, name=f"Company {tenant_id}", tier="STANDARD")
            db.add(company)
            db.flush()

        user_id = f"user-{uuid.uuid4().hex[:8]}"
        user = User(
            id=user_id,
            email=email_clean,
            name=full_name,
            password_hash=hash_password(password),
            role="COMPANY_ADMIN",
            tenant_id=tenant_id,
            is_active=True,
        )
        db.add(user)

        audit = AuditEvent(
            id=f"audit-{uuid.uuid4().hex[:12]}",
            actor_id="operator-cli",
            actor_role="OPERATOR",
            tenant_id=tenant_id,
            action="ADMIN_USER_CREATED_CLI",
            outcome="SUCCESS",
            reason=f"Operator manually created administrator '{email_clean}' via CLI",
        )
        db.add(audit)
        db.commit()
        print(f"[SUCCESS] Administrator '{email_clean}' ({user_id}) created for tenant '{tenant_id}'.")
    finally:
        db.close()


def verify_user(email: str, password: str):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email.strip().lower()).first()
        if not user:
            print(f"[FAILURE] User '{email}' not found.")
            sys.exit(1)
        if not user.is_active:
            print(f"[FAILURE] User '{email}' is inactive.")
            sys.exit(1)
        if verify_password(password, user.password_hash):
            print(f"[SUCCESS] Authentication verified for '{user.email}' (Role: {user.role}, Tenant: {user.tenant_id}).")
        else:
            print(f"[FAILURE] Invalid password for '{user.email}'.")
            sys.exit(1)
    finally:
        db.close()


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    cmd = sys.argv[1].lower()
    if cmd == "list":
        list_users()
    elif cmd == "reset-password":
        if len(sys.argv) < 4:
            print("Usage: python3 manage_users.py reset-password <email> <new_password>")
            sys.exit(1)
        reset_password(sys.argv[2], sys.argv[3])
    elif cmd == "create-admin":
        if len(sys.argv) < 5:
            print("Usage: python3 manage_users.py create-admin <email> <password> <full_name> [tenant_id]")
            sys.exit(1)
        tenant = sys.argv[5] if len(sys.argv) >= 6 else "tenant-cloudflow"
        create_admin(sys.argv[2], sys.argv[3], sys.argv[4], tenant)
    elif cmd == "verify":
        if len(sys.argv) < 4:
            print("Usage: python3 manage_users.py verify <email> <password>")
            sys.exit(1)
        verify_user(sys.argv[2], sys.argv[3])
    else:
        print(f"Unknown command '{cmd}'")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
