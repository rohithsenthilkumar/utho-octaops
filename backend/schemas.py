"""
Pydantic Schemas with Input Validation for SmartCloud Optimizer
"""
from typing import Optional, Union, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict



class ResourceBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=120, description="Name of the cloud resource")
    resource_type: str = Field(..., min_length=2, max_length=50, description="Type: VM, Block Volume, Public IP, etc.")
    environment: str = Field(..., min_length=2, max_length=30, description="Deployment tier: prod, staging, dev, qa")
    region: str = Field(..., min_length=2, max_length=50, description="Datacenter region: Bangalore, Mumbai, Noida")
    cpu_cores: int = Field(..., ge=1, le=256, description="Allocated vCPU core count (1 to 256)")
    memory: float = Field(..., gt=0.0, le=2048.0, description="Allocated RAM in Gigabytes")
    cpu_utilization: float = Field(..., ge=0.0, le=100.0, description="Observed CPU utilization percentage (0 to 100)")
    estimated_monthly_cost: float = Field(..., ge=0.0, description="Estimated monthly runtime expenditure in INR")
    status: Optional[str] = Field("ACTIVE", description="Operational status: ACTIVE, OVER_PROVISIONED, IDLE, ORPHANED")
    owner: Optional[str] = Field("Platform Team", description="Team or engineer responsible for this resource")
    is_simulated: Optional[bool] = Field(True, description="Flag indicating simulated benchmark data")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        allowed = {"prod", "production", "staging", "dev", "development", "qa", "test"}
        if v.lower() not in allowed:
            raise ValueError(f"Environment must be one of {allowed}")
        return v.lower()

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str) -> str:
        allowed = {"bangalore", "mumbai", "noida", "blr", "bom", "del"}
        if v.lower() not in allowed:
            raise ValueError(f"Region must be one of Bangalore, Mumbai, or Noida (or BLR, BOM, DEL)")
        # Capitalize standard names
        mapping = {
            "bangalore": "Bangalore",
            "blr": "Bangalore",
            "mumbai": "Mumbai",
            "bom": "Mumbai",
            "noida": "Noida",
            "del": "Noida",
        }
        return mapping.get(v.lower(), v)


class ResourceCreate(ResourceBase):
    id: Optional[str] = Field(None, max_length=80, description="Optional unique identifier (e.g. vm-blr-prod-01)")


class ResourceResponse(ResourceBase):
    id: str
    created_at: Optional[Union[datetime, str]] = None
    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: str
    service: str
    stage: int
    database: str
    resources_count: int


class DashboardSummaryResponse(BaseModel):
    total_resources: int
    current_monthly_cost: float
    projected_cost: float
    total_savings: float
    savings_percentage: float
    total_recommendations: int
    accepted_recommendations: int
    pending_recommendations: int
    rejected_recommendations: int
    idle_resources_count: int


class RightsizingResponse(BaseModel):
    recommendation_id: str
    resource_id: str
    resource_name: str
    environment: str
    region: str
    action: str
    status: str
    risk_level: str
    current_configuration: dict
    proposed_configuration: Optional[dict] = None
    evidence: dict
    estimated_monthly_cost_before: float
    estimated_monthly_cost_after: float
    estimated_inr_savings: float
    savings_percentage: float
    justification: str
    is_simulated: bool = True


class StatusUpdate(BaseModel):
    status: str  # ACCEPTED | REJECTED | PENDING


class LocalMonitoringResponse(BaseModel):
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp of host telemetry collection")
    host_id: str = Field("host-local", description="Privacy-preserving stable local installation identifier")
    cpu_utilization: float = Field(..., ge=0.0, le=100.0, description="Host CPU utilization percentage over sampling window")
    cpu_percent: float = Field(..., ge=0.0, le=100.0, description="Alias for host CPU utilization percentage")
    ram_utilization: float = Field(..., ge=0.0, le=100.0, description="Host RAM memory utilization percentage")
    ram_percent: float = Field(..., ge=0.0, le=100.0, description="Alias for host RAM memory utilization percentage")
    used_ram_gb: float = Field(..., ge=0.0, description="Current used RAM in Gigabytes")
    available_ram_gb: float = Field(0.0, ge=0.0, description="Available RAM in Gigabytes")
    total_ram_gb: float = Field(..., ge=0.0, description="Total physical RAM in Gigabytes")
    used_ram_bytes: int = Field(..., ge=0, description="Current used RAM in bytes")
    total_ram_bytes: int = Field(..., ge=0, description="Total physical RAM in bytes")
    disk_total_gb: float = Field(0.0, ge=0.0, description="Total disk capacity in GB")
    disk_used_gb: float = Field(0.0, ge=0.0, description="Used disk space in GB")
    disk_free_gb: float = Field(0.0, ge=0.0, description="Free disk space in GB")
    disk_percent: float = Field(0.0, ge=0.0, le=100.0, description="Used disk percentage")
    disk_mount_point: str = Field("/", description="Filesystem mount point")
    storage_resizing: str = Field("NOT_CONFIGURED", description="Storage expansion capability status")
    sampling_interval_seconds: float = Field(..., ge=0.0, description="Duration in seconds used to sample CPU utilization")
    metric_source: str = Field("Live local host metrics", description="Label clearly isolating live host telemetry from simulated fleet data")
    status: str = Field("healthy", description="Collector health status")


class DockerWorkloadTelemetry(BaseModel):
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    container_name: str = Field("autoscaling-lab-app-1", description="Target container name")
    status: str = Field("running", description="Container status")
    is_healthy: bool = Field(True, description="Gateway health check status")
    actual_cpu_percent: float = Field(..., ge=0.0, description="Real CPU percentage from Docker stats")
    actual_memory_mb: float = Field(..., ge=0.0, description="Real memory used in MB from Docker stats")
    actual_memory_limit_mb: float = Field(..., ge=0.0, description="Memory limit in MB from Docker stats")
    actual_memory_percent: float = Field(..., ge=0.0, le=100.0, description="Memory utilization percentage")
    configured_cpu_cores: Optional[float] = Field(None, description="Configured vCPU limit from docker inspect (None if unconstrained)")
    configured_memory_gb: Optional[float] = Field(None, description="Configured RAM limit in GB from docker inspect (None if unconstrained)")
    is_unconstrained: bool = Field(False, description="True if container has no CPU or RAM quota set")
    limit_status: str = Field("CONSTRAINED", description="CONSTRAINED or UNCONSTRAINED")
    running_replicas: int = Field(1, description="Number of active running replicas")
    replicas_detail: List[Dict[str, Any]] = Field(default_factory=list, description="Per-replica live telemetry")
    gateway_url: str = Field("http://127.0.0.1:8080", description="Load balancer URL")
    storage_resizing: str = Field("NOT_CONFIGURED", description="Storage expansion status")
    metric_source: str = Field("Live Docker daemon statistics (cgroup / docker inspect)", description="Isolated Docker metrics label")


class StorageTelemetryResponse(BaseModel):
    telemetry: Dict[str, Any]
    resizing_capability: Dict[str, Any]


class AutoscalingManualScale(BaseModel):
    target_replicas: int = Field(..., ge=1, le=10, description="Target replica count")


class AutoscalingConfigUpdate(BaseModel):
    min_replicas: Optional[int] = Field(None, ge=1, le=10)
    max_replicas: Optional[int] = Field(None, ge=1, le=10)
    scale_out_threshold: Optional[float] = Field(None, ge=5.0, le=95.0)
    scale_in_threshold: Optional[float] = Field(None, ge=5.0, le=95.0)
    scale_out_cooldown: Optional[float] = Field(None, ge=0.0, le=120.0)
    scale_in_cooldown: Optional[float] = Field(None, ge=0.0, le=120.0)
    sustained_window_samples: Optional[int] = Field(None, ge=1, le=10)


class AutoscalingStatusResponse(BaseModel):
    status: str
    timestamp: str
    current_replicas: int
    target_replicas: int
    min_replicas: int
    max_replicas: int
    scale_out_threshold: float
    scale_in_threshold: float
    average_cpu_percent: float
    replicas_detail: List[dict]
    is_healthy: bool
    remaining_cooldown_seconds: float
    last_action: str
    latest_decision: dict
    recent_events: List[dict]
    metric_history: List[dict]
    load_balancer_url: str
    is_load_test_running: bool = False


# =========================================================================
# Stage 6: Multi-Tenant Hosting Platform & Vertical Scaling Schemas
# =========================================================================

class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class SwitchDemoUserRequest(BaseModel):
    email: str = Field(..., description="Email of the demo user to switch into")


class UserResponse(BaseModel):
    id: str
    tenant_id: str
    email: str
    full_name: str
    role: str
    company_name: Optional[str] = None
    created_at: Optional[Union[datetime, str]] = None
    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class CompanyResponse(BaseModel):
    id: str
    name: str
    slug: str
    created_at: Optional[Union[datetime, str]] = None
    resources_count: Optional[int] = 0
    users_count: Optional[int] = 0
    model_config = ConfigDict(from_attributes=True)


class TenantResourceResponse(ResourceResponse):
    tenant_id: Optional[str] = None
    owner_id: Optional[str] = None
    owner_email: Optional[str] = None
    owner_name: Optional[str] = None
    policy: Optional[Dict[str, Any]] = None
    docker_container_name: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class AssignOwnerRequest(BaseModel):
    owner_id: Optional[str] = Field(None, description="User ID to assign ownership, or None/empty to unassign")


class ResourcePolicyCreateOrUpdate(BaseModel):
    min_cpu_cores: float = Field(..., gt=0.0, le=128.0)
    max_cpu_cores: float = Field(..., gt=0.0, le=128.0)
    min_memory_gb: float = Field(..., gt=0.0, le=1024.0)
    max_memory_gb: float = Field(..., gt=0.0, le=1024.0)
    min_replicas: Optional[int] = Field(1, ge=1, le=20)
    max_replicas: Optional[int] = Field(5, ge=1, le=20)
    can_scale_horizontally: Optional[bool] = Field(False)
    allow_manual_scaling: bool = Field(True)
    requires_approval: bool = Field(False)

    @field_validator("min_memory_gb", "max_memory_gb")
    @classmethod
    def validate_finite_memory(cls, v: float) -> float:
        import math
        if math.isnan(v) or math.isinf(v) or v <= 0:
            raise ValueError("Memory values must be finite positive numbers")
        return round(v, 2)

    @field_validator("max_cpu_cores")
    @classmethod
    def validate_cpu_bounds(cls, v: float, info) -> float:
        if "min_cpu_cores" in info.data and v < info.data["min_cpu_cores"]:
            raise ValueError("max_cpu_cores must be greater than or equal to min_cpu_cores")
        return v

    @field_validator("max_memory_gb")
    @classmethod
    def validate_memory_bounds(cls, v: float, info) -> float:
        if "min_memory_gb" in info.data and v < info.data["min_memory_gb"]:
            raise ValueError("max_memory_gb must be greater than or equal to min_memory_gb")
        return v

    @field_validator("max_replicas")
    @classmethod
    def validate_replica_bounds(cls, v: Optional[int], info) -> Optional[int]:
        if v is not None and "min_replicas" in info.data and info.data["min_replicas"] is not None:
            if v < info.data["min_replicas"]:
                raise ValueError("max_replicas must be greater than or equal to min_replicas")
        return v


class ResourcePolicyResponse(BaseModel):
    id: str
    tenant_id: str
    resource_id: str
    min_cpu_cores: float
    max_cpu_cores: float
    min_memory_gb: float
    max_memory_gb: float
    min_replicas: Optional[int] = 1
    max_replicas: Optional[int] = 5
    can_scale_horizontally: Optional[bool] = False
    allow_manual_scaling: bool
    requires_approval: bool
    updated_at: Optional[Union[datetime, str]] = None
    model_config = ConfigDict(from_attributes=True)


class ChangeRequestCreate(BaseModel):
    resource_id: str
    target_cpu_cores: int = Field(..., ge=1, le=128)
    target_memory_gb: float = Field(..., gt=0.0, le=1024.0)
    reason: Optional[str] = Field("Workload optimization", max_length=250)

    @field_validator("target_memory_gb")
    @classmethod
    def validate_finite_mem(cls, v: float) -> float:
        import math
        if math.isnan(v) or math.isinf(v) or v <= 0:
            raise ValueError("target_memory_gb must be a finite positive number")
        return round(v, 2)


class ChangeRequestReview(BaseModel):
    decision: str = Field(..., description="APPROVED or REJECTED")
    comment: Optional[str] = Field(None, max_length=250)

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, v: str) -> str:
        if v.upper() not in {"APPROVED", "REJECTED"}:
            raise ValueError("Decision must be either APPROVED or REJECTED")
        return v.upper()


class ChangeRequestResponse(BaseModel):
    id: str
    tenant_id: str
    resource_id: str
    resource_name: Optional[str] = None
    requester_id: str
    requester_email: Optional[str] = None
    current_cpu_cores: int
    current_memory_gb: float
    target_cpu_cores: int
    target_memory_gb: float
    status: str
    reason: Optional[str] = None
    approver_id: Optional[str] = None
    approver_email: Optional[str] = None
    cost_difference_inr: float
    created_at: Optional[Union[datetime, str]] = None
    reviewed_at: Optional[Union[datetime, str]] = None
    model_config = ConfigDict(from_attributes=True)


class VerticalScaleRequest(BaseModel):
    resource_id: str
    target_cpu_cores: int = Field(..., ge=1, le=128)
    target_memory_gb: float = Field(..., gt=0.0, le=1024.0)
    reason: Optional[str] = Field("Manual vertical scaling", max_length=250)

    @field_validator("target_memory_gb")
    @classmethod
    def validate_finite_mem(cls, v: float) -> float:
        import math
        if math.isnan(v) or math.isinf(v) or v <= 0:
            raise ValueError("target_memory_gb must be a finite positive number")
        return round(v, 2)


class VerticalScaleResponse(BaseModel):
    status: str  # APPLIED or PENDING_APPROVAL
    message: str
    resource_id: str
    resource_name: str
    applied_limits: Dict[str, Any]
    previous_limits: Dict[str, Any]
    cost_impact: Dict[str, Any]
    change_request_id: Optional[str] = None
    is_live_container: bool
    container_name: Optional[str] = None


class AuditEventResponse(BaseModel):
    id: str
    tenant_id: str
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    resource_id: Optional[str] = None
    details: Dict[str, Any]
    timestamp: Optional[Union[datetime, str]] = None
    model_config = ConfigDict(from_attributes=True)


# =========================================================================
# Stage 7: Unified Optimization Engine Schemas
# =========================================================================

class OptimizerConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    operating_mode: Optional[str] = Field(None, description="DRY_RUN, RECOMMENDATION, or AUTO")
    evaluation_interval_seconds: Optional[float] = Field(None, ge=1.0, le=300.0)
    scale_up_cpu_threshold: Optional[float] = Field(None, ge=10.0, le=95.0)
    scale_down_cpu_threshold: Optional[float] = Field(None, ge=5.0, le=90.0)
    scale_up_memory_threshold: Optional[float] = Field(None, ge=10.0, le=95.0)
    scale_down_memory_threshold: Optional[float] = Field(None, ge=5.0, le=90.0)
    sustained_window_samples: Optional[int] = Field(None, ge=1, le=10)
    cooldown_seconds: Optional[float] = Field(None, ge=0.0, le=600.0)
    max_sample_gap_seconds: Optional[float] = Field(None, ge=1.0, le=600.0)

    @field_validator("operating_mode")
    @classmethod
    def validate_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.upper() not in {"DRY_RUN", "RECOMMENDATION", "AUTO"}:
            raise ValueError("operating_mode must be one of: DRY_RUN, RECOMMENDATION, AUTO")
        return v.upper() if v else None


class OptimizerEvaluateRequest(BaseModel):
    resource_id: str = Field(..., description="Target resource ID to evaluate")
    mode_override: Optional[str] = Field(None, description="Temporary operating mode override (e.g. DRY_RUN)")


class OptimizerDecisionResponse(BaseModel):
    correlation_id: str
    timestamp: str
    resource_id: str
    resource_name: str
    tenant_id: Optional[str] = None
    operating_mode: str
    observed_metrics: Dict[str, Any]
    current_allocation: Dict[str, Any]
    proposed_allocation: Dict[str, Any]
    decision: str
    reason: str
    estimated_cost_before_inr: float
    estimated_cost_after_inr: float
    estimated_monthly_savings_inr: float
    requires_approval: bool
    executed: bool
    verified: bool
    execution_error: Optional[str] = None
    change_request_id: Optional[str] = None


class OptimizerStatusResponse(BaseModel):
    status: str
    enabled: bool
    scheduler_running: bool = True
    scheduler_state: Optional[str] = "INITIALIZING"
    operating_mode: str
    evaluation_interval_seconds: float
    max_sample_gap_seconds: Optional[float] = None
    config: Dict[str, Any]
    last_run_timestamp: Optional[str] = None
    last_evaluation_timestamp: Optional[str] = None
    next_run_timestamp: Optional[str] = None
    recent_decisions_count: int
    recent_errors_count: int
    recent_decisions: List[Dict[str, Any]]
    recent_errors: List[Dict[str, Any]]


# =============================================================================
# Stage 9A: KVM / Libvirt Schemas
# =============================================================================

class KvmHypervisorStatusResponse(BaseModel):
    is_hypervisor_ready: bool
    status: str
    details: str
    virsh_path: Optional[str] = None
    virsh_available: bool
    virsh_version: Optional[str] = None
    kvm_device_path: str
    kvm_device_exists: bool
    kvm_device_readable: bool
    kvm_device_writable: bool
    host_cpu_cores: int
    host_total_ram_gb: float
    host_available_ram_gb: float
    safety_headroom_ram_gb: float
    max_safe_allocatable_ram_gb: float
    instructions: Optional[str] = None


class KvmDomainSummary(BaseModel):
    name: str
    uuid: str
    state: str
    is_running: bool
    is_shutoff: bool
    current_cpu_cores: int
    max_cpu_cores: int
    current_memory_gb: float
    max_memory_gb: float
    is_test_vm: bool
    adapter_type: str = "libvirt-qemu"
    estimated_monthly_cost: float
    inspected_at: str


class KvmResizeRequest(BaseModel):
    target_cpu: float = Field(..., ge=1.0, le=128.0, description="Target vCPU cores (1 to 128)")
    target_memory_gb: float = Field(..., gt=0.0, le=512.0, description="Target RAM in GB")
    allow_shutdown: bool = Field(False, description="Explicit approval if resize requires guest reboot/shutdown")


class KvmResizeResponse(BaseModel):
    success: bool
    status: str
    message: Optional[str] = None
    error: Optional[str] = None
    requires_shutdown: bool = False
    current_allocation: Optional[Dict[str, Any]] = None
    requested_allocation: Optional[Dict[str, Any]] = None
    new_allocation: Optional[Dict[str, Any]] = None
    verified: Optional[bool] = None
    audit_event_id: Optional[str] = None


class KvmOptimizerConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    operating_mode: Optional[str] = Field(None, description="DRY_RUN, RECOMMENDATION, or AUTO")
    evaluation_interval_seconds: Optional[float] = Field(None, ge=1.0, le=300.0)
    scale_up_cpu_threshold: Optional[float] = Field(None, ge=10.0, le=95.0)
    scale_down_cpu_threshold: Optional[float] = Field(None, ge=5.0, le=90.0)
    scale_up_memory_threshold: Optional[float] = Field(None, ge=10.0, le=95.0)
    scale_down_memory_threshold: Optional[float] = Field(None, ge=5.0, le=90.0)
    sustained_window_samples: Optional[int] = Field(None, ge=1, le=10)
    cooldown_seconds: Optional[float] = Field(None, ge=0.0, le=600.0)
    max_sample_gap_seconds: Optional[float] = Field(None, ge=1.0, le=600.0)

    @field_validator("operating_mode")
    @classmethod
    def validate_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v.upper() not in {"DRY_RUN", "RECOMMENDATION", "AUTO"}:
            raise ValueError("operating_mode must be one of: DRY_RUN, RECOMMENDATION, AUTO")
        return v.upper() if v else None


class KvmOptimizerEvaluateRequest(BaseModel):
    domain_name: str = Field(..., description="Target libvirt domain name")
    observed_guest_cpu: Optional[float] = Field(None, ge=0.0, le=100.0, description="Observed guest CPU %")
    observed_guest_ram_percent: Optional[float] = Field(None, ge=0.0, le=100.0, description="Observed guest RAM %")
    mode_override: Optional[str] = Field(None, description="Temporary operating mode override (DRY_RUN, RECOMMENDATION, AUTO)")
    allow_shutdown: bool = Field(False, description="Explicit approval if action requires shutdown")


class KvmOptimizerDecisionResponse(BaseModel):
    correlation_id: str
    timestamp: str
    domain_name: str
    operating_mode: str
    observed_metrics: Dict[str, Any]
    current_allocation: Dict[str, Any]
    proposed_allocation: Dict[str, Any]
    decision: str
    reason: str
    estimated_cost_before_inr: float
    estimated_cost_after_inr: float
    estimated_monthly_savings_inr: float
    requires_approval: bool = False
    executed: bool = False
    verified: bool = False
    execution_error: Optional[str] = None
    requires_shutdown: bool = False


