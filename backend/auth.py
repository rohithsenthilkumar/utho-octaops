"""
SmartCloud Optimizer — Stage 6 Authentication and Authorization (RBAC)
Secure password hashing, signed bearer tokens, and server-side RBAC dependencies.
"""
import os
import hmac
import hashlib
import secrets
import time
import json
import base64
from typing import Optional, Dict, Any, Tuple
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from database import get_db
from models import User, CloudResource

# Secret key for HMAC token signing (configurable via environment, falls back to stable dev key)
_env_secret = os.getenv("SECRET_KEY", "smartcloud-optimizer-sec-stage6-default-key-dev")
SECRET_KEY: bytes = _env_secret.encode("utf-8")
TOKEN_EXPIRY_SECONDS = 86400  # 24 hours

bearer_scheme = HTTPBearer(auto_error=False)


def is_production_env() -> bool:
    """Return True if running in production mode."""
    env = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).strip().lower()
    return env in ("production", "prod")


def is_demo_bypass_allowed() -> bool:
    """
    Demo authentication bypass (X-Demo-User) is strictly prohibited in production.
    In development/testing, it requires ALLOW_DEMO_AUTH_BYPASS to be explicitly enabled (default: true).
    """
    if is_production_env():
        return False
    return os.getenv("ALLOW_DEMO_AUTH_BYPASS", "true").lower() in ("true", "1", "yes")


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with a cryptographically secure 16-byte salt."""
    salt = secrets.token_hex(16)
    iterations = 100_000
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    )
    return f"pbkdf2:sha256:{iterations}${salt}${derived.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against stored PBKDF2-HMAC-SHA256 hash."""
    try:
        prefix, salt, key_hex = hashed_password.split("$")
        parts = prefix.split(":")
        iterations = int(parts[2])
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        )
        return secrets.compare_digest(derived.hex(), key_hex)
    except Exception:
        return False


def create_access_token(user: User) -> str:
    """Create a signed, tamper-proof bearer token containing user identity and tenant scope."""
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "exp": int(time.time()) + TOKEN_EXPIRY_SECONDS,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
    sig = hmac.new(SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Validate HMAC signature, expiration, and unpack payload."""
    try:
        parts = token.strip().split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig = parts[0], parts[1]
        expected_sig = hmac.new(SECRET_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not secrets.compare_digest(sig, expected_sig):
            return None

        # Re-pad base64
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        payload = json.loads(payload_bytes.decode("utf-8"))

        if payload.get("exp", 0) < time.time():
            return None  # Expired

        return payload
    except Exception:
        return None


def get_current_user(
    auth_header: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_demo_user: Optional[str] = Header(None, alias="X-Demo-User"),
    x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token"),
    db: Session = Depends(get_db),
) -> User:
    """
    Authenticate request via:
      1. Bearer Token in Authorization header
      2. X-Auth-Token header
      3. X-Demo-User header (demo/testing fast-path email, ONLY in dev/test mode)
    """
    token = None
    if auth_header and auth_header.credentials:
        token = auth_header.credentials
    elif x_auth_token:
        token = x_auth_token

    if token:
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid, expired, or malformed authentication token.",
            )
        user = db.query(User).filter(User.id == payload.get("sub")).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account associated with this token does not exist or is inactive.",
            )
        return user

    # Support testing and seamless demo switching by email ONLY in explicitly permitted dev/test mode
    # Production environments strictly reject this bypass regardless of headers
    if is_demo_bypass_allowed() and x_demo_user:
        user = db.query(User).filter(User.email == x_demo_user.strip().lower()).first()
        if user and user.is_active:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Demo user '{x_demo_user}' not found or inactive.",
        )

    # Strictly reject unauthenticated requests (no default admin fallback)
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide a valid Bearer token or sign in.",
    )


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Enforce that the requesting actor has the COMPANY_ADMIN role."""
    if current_user.role != "COMPANY_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Action requires COMPANY_ADMIN role. Current role is '{current_user.role}'.",
        )
    return current_user


def verify_resource_access(
    resource: CloudResource,
    current_user: User,
) -> None:
    """
    Strict server-side validation:
      1. Cross-tenant rejection: Actor must belong to the resource's tenant.
      2. Owner rejection: VM_OWNER can only access VMs explicitly assigned to them.
    """
    # 1. Tenant boundary
    if resource.tenant_id and resource.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: You cannot access or modify resources belonging to another company.",
        )

    # 2. Ownership boundary for VM Owners
    if current_user.role == "VM_OWNER":
        is_assigned = (
            resource.owner_id == current_user.id
            or (resource.owner and current_user.email.lower() in resource.owner.lower())
            or (resource.owner and current_user.name.lower() in resource.owner.lower())
        )
        if not is_assigned:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: Virtual Machine '{resource.id}' is not assigned to user '{current_user.email}'.",
            )
