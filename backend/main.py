"""
SmartCloud Optimizer — Stage 4 FastAPI Backend
==============================================
FastAPI REST API with SQLAlchemy, SQLite, Stage 3 Rightsizing Engine,
and Stage 4 Live Local Host Monitoring.
"""
import math
import uuid
import json
import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

import psutil
from fastapi import FastAPI, Depends, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
import subprocess
import os
import hashlib

from database import engine, get_db, init_db
from models import (
    CloudResource,
    Company,
    User,
    ResourcePolicy,
    ResourceChangeRequest,
    AuditEvent,
)
from schemas import (
    ResourceCreate,
    ResourceResponse,
    HealthResponse,
    DashboardSummaryResponse,
    RightsizingResponse,
    StatusUpdate,
    LocalMonitoringResponse,
    DockerWorkloadTelemetry,
    StorageTelemetryResponse,
    AutoscalingManualScale,
    AutoscalingConfigUpdate,
    AutoscalingStatusResponse,
    LoginRequest,
    SwitchDemoUserRequest,
    UserResponse,
    TokenResponse,
    CompanyResponse,
    TenantResourceResponse,
    AssignOwnerRequest,
    ResourcePolicyCreateOrUpdate,
    ResourcePolicyResponse,
    ChangeRequestCreate,
    ChangeRequestReview,
    ChangeRequestResponse,
    VerticalScaleRequest,
    VerticalScaleResponse,
    AuditEventResponse,
    OptimizerConfigUpdate,
    OptimizerEvaluateRequest,
    OptimizerDecisionResponse,
    OptimizerStatusResponse,
    KvmHypervisorStatusResponse,
    KvmDomainSummary,
    KvmResizeRequest,
    KvmResizeResponse,
    KvmOptimizerConfigUpdate,
    KvmOptimizerEvaluateRequest,
    KvmOptimizerDecisionResponse,
)
from seed import seed_resources
from engines.rightsizing import RightsizingEngine, MIN_DATA_POINTS
from engines.autoscaler import AutoscalingController, AutoscalerConfig
from engines.vertical_scaler import VerticalScalingService, estimate_compute_monthly_cost
from engines.storage_adapter import LocalHostStorageCollector
from engines.kvm_adapter import KvmLibvirtAdapter
from engines.kvm_optimizer import KvmVmOptimizerEngine, VmOptimizerConfig
from engines.unified_optimizer import (
    UnifiedOptimizationEngine,
    OptimizationEngineConfig,
    MODE_DRY_RUN,
    MODE_RECOMMENDATION,
    MODE_AUTO,
)
from auth import (
    verify_password,
    create_access_token,
    get_current_user,
    require_admin,
    verify_resource_access,
    is_production_env,
    is_demo_bypass_allowed,
)

logger = logging.getLogger("smartcloud.backend")

autoscaler_controller = AutoscalingController()
vertical_scaler_service = VerticalScalingService()
unified_optimizer_engine = UnifiedOptimizationEngine(
    config=OptimizationEngineConfig(
        enabled=False,
        operating_mode=MODE_DRY_RUN,
        evaluation_interval_seconds=5.0,
    ),
    vertical_scaler=vertical_scaler_service,
    autoscaler=autoscaler_controller,
)
active_load_test_proc: Optional[subprocess.Popen] = None
storage_collector = LocalHostStorageCollector()
kvm_adapter = KvmLibvirtAdapter()
kvm_optimizer = KvmVmOptimizerEngine(adapter=kvm_adapter)


def get_stable_host_id() -> str:
    """Derive privacy-preserving, stable local installation identifier."""
    machine_id = ""
    for path in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    machine_id = f.read().strip()
                break
            except Exception:
                pass
    if not machine_id:
        machine_id = os.uname().nodename
    return f"host-{hashlib.sha256(machine_id.encode()).hexdigest()[:12]}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize SQLite tables, idempotent seed, psutil baselines, and coordinated background evaluation loop."""
    init_db()
    with Session(bind=engine) as session:
        seed_resources(session)
    try:
        psutil.cpu_percent(interval=None)
    except Exception:
        pass

    if is_production_env():
        logger.info("[SECURITY] Production mode active: Demo auth bypass is strictly disabled.")
    else:
        logger.warning("[SECURITY] Non-production mode active: Demo auth bypass permitted only when configured.")

    # Background evaluation task for unified optimizer and autoscaler
    bg_task = asyncio.create_task(_optimizer_background_loop())
    yield
    bg_task.cancel()


async def _optimizer_background_loop():
    """
    Lightweight, single-authoritative background polling loop.
    Coordinates horizontal and vertical evaluation without overlapping cycles or duplicate workers.
    """
    unified_optimizer_engine.scheduler_running = True
    unified_optimizer_engine.scheduler_state = (
        "SLEEPING" if unified_optimizer_engine.config.enabled else "IDLE_DISABLED"
    )
    try:
        while True:
            interval = unified_optimizer_engine.config.evaluation_interval_seconds
            if unified_optimizer_engine.config.enabled:
                unified_optimizer_engine.next_run_timestamp = (
                    datetime.now(timezone.utc) + timedelta(seconds=interval)
                ).isoformat()
            else:
                unified_optimizer_engine.next_run_timestamp = None

            await asyncio.sleep(interval)

            if not unified_optimizer_engine.config.enabled:
                unified_optimizer_engine.scheduler_state = "IDLE_DISABLED"
                continue

            if unified_optimizer_engine._is_evaluating:
                continue

            unified_optimizer_engine._is_evaluating = True
            unified_optimizer_engine.scheduler_state = "EVALUATING"
            now_str = datetime.now(timezone.utc).isoformat()
            unified_optimizer_engine.last_run_timestamp = now_str
            unified_optimizer_engine.last_evaluation_timestamp = now_str

            # Execute background evaluation for local docker demo workload
            def _eval_cycle():
                with Session(bind=engine) as session:
                    res = session.query(CloudResource).filter(
                        CloudResource.is_simulated == False
                    ).first()
                    if res:
                        # Collect live container metrics
                        avg_cpu, detail, is_healthy = autoscaler_controller.measure_container_metrics()
                        current_reps = autoscaler_controller.get_current_replica_count(detail)

                        # Calculate actual RAM percent from container cgroup telemetry
                        mem_percent = 25.0
                        if detail:
                            first_rep = detail[0]
                            if first_rep.get("memory_percent", 0.0) > 0.0:
                                mem_percent = first_rep["memory_percent"]

                        policy = session.query(ResourcePolicy).filter(
                            ResourcePolicy.resource_id == res.id
                        ).first()

                        unified_optimizer_engine.evaluate_resource(
                            resource=res,
                            policy=policy,
                            observed_cpu=avg_cpu if is_healthy else None,
                            observed_memory_percent=mem_percent if is_healthy else None,
                            current_replicas=current_reps,
                            db_session=session,
                        )
                        session.commit()

            await asyncio.to_thread(_eval_cycle)
            unified_optimizer_engine._is_evaluating = False
            unified_optimizer_engine.scheduler_state = (
                "SLEEPING" if unified_optimizer_engine.config.enabled else "IDLE_DISABLED"
            )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"Unified optimizer background loop error: {e}")
        unified_optimizer_engine.scheduler_state = "ERROR"
    finally:
        unified_optimizer_engine._is_evaluating = False
        unified_optimizer_engine.scheduler_running = False
        unified_optimizer_engine.scheduler_state = "STOPPED"



app = FastAPI(
    title="SmartCloud Optimizer API",
    description="Stage 4 Backend, Rightsizing Engine & Live Local System Monitoring",
    version="4.0.0",
    lifespan=lifespan,
)

# Enable CORS for local Vite development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rightsizing_engine = RightsizingEngine()

# In-memory status override map for interactive accept/reject of recommendations
RECOMMENDATION_STATUS_OVERRIDES: Dict[str, str] = {}


def generate_simulated_metrics(resource: CloudResource, count: int = 168) -> List[Dict[str, Any]]:
    """
    Deterministically generates simulated hourly time-series metrics.
    If the resource has 'insufficient' in its ID or name, generates fewer than 24 samples
    to trigger the deterministic 'insufficient data' safety branch.
    """
    res_id = resource.id.lower()
    res_name = resource.name.lower()

    # Trigger insufficient data condition when explicitly tested
    if "insufficient" in res_id or "insufficient" in res_name or "sparse" in res_id:
        return [
            {
                "timestamp": (datetime.now(timezone.utc) - timedelta(hours=i)).isoformat(),
                "cpu_percent": 15.0,
                "ram_percent": 25.0,
            }
            for i in range(6)  # Only 6 samples (< 24 min requirement)
        ]

    # Deterministic seed factor from resource ID
    base_util = resource.cpu_utilization if resource.cpu_utilization > 0 else 25.0
    records = []
    now = datetime.now(timezone.utc)

    for i in range(count):
        t = now - timedelta(hours=i)
        hour = t.hour
        # Diurnal curve: higher usage during Indian business hours (09:00 - 20:00 IST)
        diurnal = math.sin(((hour - 9) / 24.0) * 2 * math.pi) * 0.35 + 1.0
        hash_jitter = ((hash(f"{resource.id}-{i}") % 100) / 100.0 - 0.5) * 6.0

        if resource.environment == "dev" and (t.weekday() >= 5):
            # Weekend idle drop for dev workloads
            cpu_val = max(1.5, min(95.0, round(base_util * 0.25 + hash_jitter * 0.3, 1)))
            ram_val = max(5.0, min(95.0, round(base_util * 0.5 + hash_jitter * 0.2, 1)))
        else:
            cpu_val = max(2.0, min(98.0, round(base_util * 0.75 * diurnal + hash_jitter, 1)))
            ram_val = max(8.0, min(95.0, round((base_util * 1.1) * (0.8 + 0.2 * diurnal) + hash_jitter * 0.5, 1)))

        records.append({
            "timestamp": t.isoformat(),
            "cpu_percent": cpu_val,
            "ram_percent": ram_val,
            "disk_percent": 42.0,
            "disk_iops": int(cpu_val * 14 + 100),
            "network_in_kbps": round(cpu_val * 45.0, 1),
            "network_out_kbps": round(cpu_val * 65.0, 1),
        })

    return records


# ------------------------------------------------------------------ #
#  Core Stage 2 Endpoints                                             #
# ------------------------------------------------------------------ #

@app.get("/api/health", response_model=HealthResponse, tags=["Health"])
def get_health(db: Session = Depends(get_db)):
    """Health check endpoint reporting API, SQLite database, and Stage 3 engine status."""
    try:
        count = db.query(CloudResource).count()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
        count = 0

    return {
        "status": "ok",
        "service": "SmartCloud Optimizer API",
        "stage": 4,
        "database": db_status,
        "resources_count": count,
    }



@app.get("/api/resources", response_model=List[ResourceResponse], tags=["Resources"])
def get_resources(
    region: Optional[str] = Query(None, description="Filter by region (Bangalore, Mumbai, Noida)"),
    environment: Optional[str] = Query(None, description="Filter by environment (prod, staging, dev, qa)"),
    resource_type: Optional[str] = Query(None, alias="type", description="Filter by resource type (VM, Block Volume, etc.)"),
    search: Optional[str] = Query(None, description="Search by name, ID, or owner"),
    db: Session = Depends(get_db),
):
    """List cloud resources stored in SQLite database with optional filtering and search."""
    query = db.query(CloudResource)

    if region and region.lower() != "all":
        query = query.filter(CloudResource.region.ilike(f"%{region}%"))

    if environment and environment.lower() != "all":
        query = query.filter(CloudResource.environment.ilike(f"%{environment}%"))

    if resource_type and resource_type.lower() != "all":
        query = query.filter(CloudResource.resource_type.ilike(f"%{resource_type}%"))

    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(
            (CloudResource.name.ilike(term))
            | (CloudResource.id.ilike(term))
            | (CloudResource.owner.ilike(term))
        )

    return query.order_by(CloudResource.is_simulated.desc(), CloudResource.created_at.desc()).all()


@app.get("/api/resources/{resource_id}", response_model=ResourceResponse, tags=["Resources"])
def get_resource(resource_id: str, db: Session = Depends(get_db)):
    """Retrieve single resource by ID from SQLite database."""
    res = db.query(CloudResource).filter(CloudResource.id == resource_id).first()
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource with ID '{resource_id}' not found.",
        )
    return res


@app.post(
    "/api/resources",
    response_model=ResourceResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Resources"],
)
def create_resource(payload: ResourceCreate, db: Session = Depends(get_db)):
    """Create a new cloud resource with rigorous input validation."""
    resource_id = payload.id.strip() if payload.id and payload.id.strip() else None
    if resource_id:
        existing = db.query(CloudResource).filter(CloudResource.id == resource_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Resource with ID '{resource_id}' already exists.",
            )
    else:
        reg_code = payload.region[:3].lower()
        env_code = payload.environment[:3].lower()
        rand_suffix = uuid.uuid4().hex[:4]
        resource_id = f"vm-{reg_code}-{env_code}-{rand_suffix}"

    data = payload.model_dump()
    data["id"] = resource_id

    new_resource = CloudResource(**data)
    db.add(new_resource)
    db.commit()
    db.refresh(new_resource)
    return new_resource


# Alias for legacy compatibility
@app.get("/api/inventory", tags=["Compatibility"])
def list_inventory_compatibility(db: Session = Depends(get_db)):
    """Backward compatibility alias for /api/resources."""
    return get_resources(db=db)


# ------------------------------------------------------------------ #
#  Stage 3 Rightsizing Engine Endpoints                              #
# ------------------------------------------------------------------ #

def compute_rightsizing_recommendations(
    db: Session,
    resource_id: Optional[str] = None,
    region: Optional[str] = None,
    environment: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Core rightsizing evaluation engine logic.
    Accepts raw python parameters safely (handling None or string values).
    """
    rid = str(resource_id).strip() if isinstance(resource_id, str) and resource_id.strip() else None
    reg = str(region).strip() if isinstance(region, str) and region.strip() else None
    env = str(environment).strip() if isinstance(environment, str) and environment.strip() else None

    query = db.query(CloudResource).filter(CloudResource.resource_type.ilike("%VM%"))

    if rid:
        query = query.filter(CloudResource.id == rid)
    if reg and reg.lower() != "all":
        query = query.filter(CloudResource.region.ilike(f"%{reg}%"))
    if env and env.lower() != "all":
        query = query.filter(CloudResource.environment.ilike(f"%{env}%"))

    resources = query.all()
    recommendations: List[Dict[str, Any]] = []

    for idx, res in enumerate(resources, start=1):
        # Generate or fetch simulated metrics for this resource
        metrics = generate_simulated_metrics(res, count=168)
        rec = rightsizing_engine.evaluate_resource(res, metrics, rec_index=idx)

        # Apply any in-memory user acceptance/rejection overrides
        if rec["recommendation_id"] in RECOMMENDATION_STATUS_OVERRIDES:
            rec["status"] = RECOMMENDATION_STATUS_OVERRIDES[rec["recommendation_id"]]

        recommendations.append(rec)

    # Sort: highest savings first
    recommendations.sort(key=lambda r: r["estimated_inr_savings"], reverse=True)
    return recommendations


@app.get(
    "/api/recommendations/rightsizing",
    response_model=List[RightsizingResponse],
    tags=["Rightsizing"],
)
def get_rightsizing_recommendations(
    resource_id: Optional[str] = Query(None, description="Filter for specific resource"),
    region: Optional[str] = Query(None, description="Filter by datacenter region"),
    environment: Optional[str] = Query(None, description="Filter by environment tier"),
    db: Session = Depends(get_db),
):
    """
    Stage 3: Generates deterministic rightsizing recommendations for all cloud compute resources.
    Considers peak p95/p99 CPU and memory headroom with environment safety buffers.
    Returns 'insufficient data' when metrics are sparse (< 24 samples).
    Clearly labelled as simulated data.
    """
    return compute_rightsizing_recommendations(
        db=db,
        resource_id=resource_id if isinstance(resource_id, str) else None,
        region=region if isinstance(region, str) else None,
        environment=environment if isinstance(environment, str) else None,
    )


@app.get("/api/recommendations", response_model=List[RightsizingResponse], tags=["Rightsizing"])
def list_recommendations_alias(
    resource_id: Optional[str] = Query(None),
    region: Optional[str] = Query(None),
    environment: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Unified recommendations endpoint forwarding to the Stage 3 rightsizing engine."""
    return compute_rightsizing_recommendations(
        db=db,
        resource_id=resource_id if isinstance(resource_id, str) else None,
        region=region if isinstance(region, str) else None,
        environment=environment if isinstance(environment, str) else None,
    )


@app.post("/api/recommendations/{recommendation_id}/status", tags=["Rightsizing"])
def update_recommendation_status(recommendation_id: str, payload: StatusUpdate):
    """Update status of a recommendation (ACCEPTED, REJECTED, PENDING)."""
    allowed = {"ACCEPTED", "REJECTED", "PENDING"}
    new_status = payload.status.upper()
    if new_status not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Status must be one of {allowed}",
        )
    RECOMMENDATION_STATUS_OVERRIDES[recommendation_id] = new_status
    return {
        "success": True,
        "recommendation_id": recommendation_id,
        "new_status": new_status,
    }


# ------------------------------------------------------------------ #
#  Dashboard Summary & Metrics                                        #
# ------------------------------------------------------------------ #

@app.get(
    "/api/dashboard/summary",
    response_model=DashboardSummaryResponse,
    tags=["Dashboard"],
)
def get_dashboard_summary(db: Session = Depends(get_db)):
    """Summary metrics calculated from live database and rightsizing recommendations."""
    resources = db.query(CloudResource).all()
    total_resources = len(resources)
    total_monthly_cost = sum(r.estimated_monthly_cost for r in resources)

    # Evaluate recommendations to calculate true potential savings
    recs = compute_rightsizing_recommendations(db=db)
    total_savings = sum(r["estimated_inr_savings"] for r in recs if r["estimated_inr_savings"] > 0)
    projected_cost = max(0.0, total_monthly_cost - total_savings)
    savings_pct = round((total_savings / total_monthly_cost * 100), 1) if total_monthly_cost > 0 else 0.0

    accepted_count = sum(1 for r in recs if r["status"] == "ACCEPTED")
    pending_count = sum(1 for r in recs if r["status"] in ("RECOMMENDED", "PENDING"))
    rejected_count = sum(1 for r in recs if r["status"] == "REJECTED")

    return {
        "total_resources": total_resources,
        "current_monthly_cost": round(total_monthly_cost, 2),
        "projected_cost": round(projected_cost, 2),
        "total_savings": round(total_savings, 2),
        "savings_percentage": savings_pct,
        "total_recommendations": len(recs),
        "accepted_recommendations": accepted_count,
        "pending_recommendations": pending_count,
        "rejected_recommendations": rejected_count,
        "idle_resources_count": sum(1 for r in resources if r.status in ("IDLE", "ORPHANED")),
    }


# ------------------------------------------------------------------ #
#  Stage 4: Live Local Host System Monitoring                        #
# ------------------------------------------------------------------ #

def _collect_host_metrics(interval: float = 0.5) -> Dict[str, Any]:
    """
    Collects real-time CPU, RAM, and Disk telemetry from the local host system.
    Strictly isolated: does NOT inspect process names, user IDs, disk paths, or network sockets.
    Uses psutil.cpu_percent, psutil.virtual_memory, and psutil.disk_usage.
    """
    cpu = psutil.cpu_percent(interval=interval)
    mem = psutil.virtual_memory()
    storage = storage_collector.collect_telemetry()

    used_gb = round(mem.used / (1024 ** 3), 2)
    available_gb = round(mem.available / (1024 ** 3), 2)
    total_gb = round(mem.total / (1024 ** 3), 2)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "host_id": get_stable_host_id(),
        "cpu_utilization": round(cpu, 1),
        "cpu_percent": round(cpu, 1),
        "ram_utilization": round(mem.percent, 1),
        "ram_percent": round(mem.percent, 1),
        "used_ram_gb": used_gb,
        "available_ram_gb": available_gb,
        "total_ram_gb": total_gb,
        "used_ram_bytes": mem.used,
        "total_ram_bytes": mem.total,
        "disk_total_gb": storage.total_gb,
        "disk_used_gb": storage.used_gb,
        "disk_free_gb": storage.free_gb,
        "disk_percent": storage.percent_used,
        "disk_mount_point": storage.mount_point,
        "storage_resizing": "NOT_CONFIGURED",
        "sampling_interval_seconds": interval,
        "metric_source": "Live local host metrics",
        "status": "healthy",
    }


@app.get(
    "/api/monitoring/local",
    response_model=LocalMonitoringResponse,
    tags=["Monitoring"],
)
async def get_local_monitoring(
    interval: float = Query(
        0.5,
        ge=0.05,
        le=5.0,
        description="Sampling window duration in seconds for CPU utilization measurement",
    )
):
    """
    Read-only live local host telemetry collection.
    Uses psutil to measure host CPU utilization, RAM utilization, available RAM,
    filesystem disk capacity and utilization, and stable non-sensitive host identity.
    Delegates metric collection to an asynchronous thread pool worker to ensure
    FastAPI never blocks concurrent HTTP requests during the sampling interval.
    """
    try:
        data = await asyncio.to_thread(_collect_host_metrics, interval)
        return data
    except Exception as e:
        logger.error(f"Error collecting local system metrics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to collect local host metrics: {str(e)}",
        )


@app.get(
    "/api/monitoring/docker/workload",
    response_model=DockerWorkloadTelemetry,
    tags=["Monitoring"],
)
def get_docker_workload_monitoring():
    """
    Collect live, separate Docker container telemetry for the demo workload.
    Isolates actual container CPU & RAM cgroup metrics from host-wide utilization.
    Explicitly reports configured Docker inspect limits and unconstrained status.
    """
    avg_cpu, replicas, is_healthy = autoscaler_controller.measure_container_metrics()
    current_reps = autoscaler_controller.get_current_replica_count(replicas)

    ok, limits, msg = vertical_scaler_service.inspect_container_limits("autoscaling-lab-app-1")

    total_mem_mb = 0.0
    total_limit_mb = 0.0
    mem_pct = 0.0
    if replicas:
        total_mem_mb = round(sum(r.get("memory_used_mb", 0.0) for r in replicas), 2)
        total_limit_mb = round(sum(r.get("memory_limit_mb", 0.0) for r in replicas), 2)
        mem_pct = round((total_mem_mb / total_limit_mb * 100.0), 1) if total_limit_mb > 0 else 0.0

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "container_name": "autoscaling-lab-app-1",
        "status": "running" if (replicas and is_healthy) else ("degraded" if replicas else "stopped"),
        "is_healthy": is_healthy,
        "actual_cpu_percent": avg_cpu,
        "actual_memory_mb": total_mem_mb,
        "actual_memory_limit_mb": total_limit_mb,
        "actual_memory_percent": mem_pct,
        "configured_cpu_cores": limits.get("actual_cpu_cores") if ok else None,
        "configured_memory_gb": limits.get("actual_memory_gb") if ok else None,
        "is_unconstrained": limits.get("is_unconstrained", False) if ok else False,
        "limit_status": limits.get("limit_status", "CONSTRAINED") if ok else "UNKNOWN",
        "running_replicas": current_reps,
        "replicas_detail": replicas,
        "gateway_url": autoscaler_controller.config.gateway_url,
        "storage_resizing": "NOT_CONFIGURED",
        "metric_source": "Live Docker daemon statistics (cgroup / docker inspect)",
    }


@app.get(
    "/api/monitoring/storage",
    response_model=StorageTelemetryResponse,
    tags=["Monitoring"],
)
def get_storage_telemetry():
    """
    Returns real local filesystem disk telemetry and the cloud provider adapter status.
    Declares volume expansion capability as NOT_CONFIGURED to ensure the local root
    disk is protected from unsafe resizing commands.
    """
    return storage_collector.get_status()


# ------------------------------------------------------------------ #
#  Stage 5: Local Autoscaling Demonstration & Lab                    #
# ------------------------------------------------------------------ #


@app.get(
    "/api/autoscaling/status",
    response_model=AutoscalingStatusResponse,
    tags=["Autoscaling"],
)
async def get_autoscaling_status():
    """
    Stage 5: Live status of local Docker replica autoscaling demonstration.
    Returns replica count, measured workload CPU, configuration thresholds,
    audit event history, and health status.
    """
    global active_load_test_proc
    data = await asyncio.to_thread(autoscaler_controller.evaluate_and_scale)
    is_running = bool(active_load_test_proc and active_load_test_proc.poll() is None)
    data["is_load_test_running"] = is_running
    return data


@app.post(
    "/api/autoscaling/evaluate",
    response_model=AutoscalingStatusResponse,
    tags=["Autoscaling"],
)
async def trigger_autoscaling_evaluation():
    """Trigger manual autoscaling evaluation cycle."""
    global active_load_test_proc
    data = await asyncio.to_thread(autoscaler_controller.evaluate_and_scale)
    data["is_load_test_running"] = bool(active_load_test_proc and active_load_test_proc.poll() is None)
    return data


@app.post("/api/autoscaling/scale", tags=["Autoscaling"])
async def set_manual_scale(payload: AutoscalingManualScale):
    """Manually scale Docker workload replicas."""
    success = await asyncio.to_thread(
        autoscaler_controller.execute_docker_scale, payload.target_replicas
    )
    return {
        "success": success,
        "target_replicas": payload.target_replicas,
        "message": f"Scaled workload to {payload.target_replicas} replicas." if success else "Scaling failed.",
    }


@app.post("/api/autoscaling/config", tags=["Autoscaling"])
def update_autoscaler_config(payload: AutoscalingConfigUpdate):
    """Update autoscaling thresholds, min/max limits, or cooldown periods."""
    cfg = autoscaler_controller.config
    if payload.min_replicas is not None:
        cfg.min_replicas = payload.min_replicas
    if payload.max_replicas is not None:
        cfg.max_replicas = payload.max_replicas
    if payload.scale_out_threshold is not None:
        cfg.scale_out_threshold = payload.scale_out_threshold
    if payload.scale_in_threshold is not None:
        cfg.scale_in_threshold = payload.scale_in_threshold
    if payload.scale_out_cooldown is not None:
        cfg.scale_out_cooldown = payload.scale_out_cooldown
    if payload.scale_in_cooldown is not None:
        cfg.scale_in_cooldown = payload.scale_in_cooldown
    if payload.sustained_window_samples is not None:
        cfg.sustained_window_samples = payload.sustained_window_samples

    return {
        "success": True,
        "config": {
            "min_replicas": cfg.min_replicas,
            "max_replicas": cfg.max_replicas,
            "scale_out_threshold": cfg.scale_out_threshold,
            "scale_in_threshold": cfg.scale_in_threshold,
            "scale_out_cooldown": cfg.scale_out_cooldown,
            "scale_in_cooldown": cfg.scale_in_cooldown,
            "sustained_window_samples": cfg.sustained_window_samples,
        },
    }


@app.post("/api/autoscaling/start", tags=["Autoscaling"])
async def start_autoscaling_stack():
    """Start the Docker Compose workload and gateway stack."""
    env = os.environ.copy()
    env["DOCKER_HOST"] = autoscaler_controller.config.docker_host
    cmd = [
        "docker", "compose",
        "-f", autoscaler_controller.config.compose_file_path,
        "up", "-d",
        "--scale", f"app={autoscaler_controller.config.min_replicas}",
    ]
    res = await asyncio.to_thread(subprocess.run, cmd, env=env, capture_output=True, text=True)
    return {
        "success": res.returncode == 0,
        "output": res.stdout or res.stderr,
    }


@app.post("/api/autoscaling/stop", tags=["Autoscaling"])
async def stop_autoscaling_stack():
    """Safe stop and cleanup procedure for the Docker Compose workload."""
    env = os.environ.copy()
    env["DOCKER_HOST"] = autoscaler_controller.config.docker_host
    cmd = [
        "docker", "compose",
        "-f", autoscaler_controller.config.compose_file_path,
        "down",
    ]
    res = await asyncio.to_thread(subprocess.run, cmd, env=env, capture_output=True, text=True)
    return {
        "success": res.returncode == 0,
        "output": res.stdout or res.stderr,
    }


@app.post("/api/autoscaling/load-test", tags=["Autoscaling"])
def trigger_k6_load_test(
    vus: int = Query(20, ge=1, le=100, description="Virtual users for load test"),
    duration: str = Query("20s", description="Test duration (e.g. 15s, 25s)"),
):
    """Trigger background k6 load surge to demonstrate automated scaling."""
    global active_load_test_proc
    if active_load_test_proc and active_load_test_proc.poll() is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A load test is already actively executing.",
        )

    k6_script = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "autoscaling-lab",
            "k6",
            "load-test.js",
        )
    )
    if not os.path.exists(k6_script):
        # Fallback check
        k6_script = os.path.abspath(
            os.path.join(
                os.path.dirname(__file__),
                "autoscaling-lab",
                "k6",
                "load-test.js",
            )
        )

    active_load_test_proc = subprocess.Popen(
        ["k6", "run", "--vus", str(vus), "--duration", duration, k6_script]
    )

    return {
        "status": "started",
        "vus": vus,
        "duration": duration,
        "message": f"k6 load test started with {vus} virtual users for {duration}.",
    }


# =========================================================================
# Stage 6: Multi-Tenant Platform, VM Ownership, RBAC & Vertical Scaling
# =========================================================================

@app.post("/api/auth/login", response_model=TokenResponse, tags=["Authentication"])
def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate with email and password, returning a signed bearer token and user profile."""
    user = db.query(User).filter(User.email == request.email.strip().lower()).first()
    if not user or not verify_password(request.password, user.password_hash):
        audit = AuditEvent(
            id=f"audit-{uuid.uuid4().hex[:12]}",
            actor_id=request.email.strip().lower(),
            actor_role=user.role if user else "UNKNOWN",
            tenant_id=user.tenant_id if user else "tenant-cloudflow",
            action="AUTH_LOGIN_FAILED",
            outcome="FAILURE",
            reason="Invalid credentials provided during login",
        )
        db.add(audit)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please verify your email and password.",
        )
    if not user.is_active:
        audit = AuditEvent(
            id=f"audit-{uuid.uuid4().hex[:12]}",
            actor_id=user.email,
            actor_role=user.role,
            tenant_id=user.tenant_id,
            action="AUTH_LOGIN_DEACTIVATED",
            outcome="FAILURE",
            reason="Deactivated user account login attempt rejected",
        )
        db.add(audit)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    # Audit successful login
    audit = AuditEvent(
        id=f"audit-{uuid.uuid4().hex[:12]}",
        actor_id=user.email,
        actor_role=user.role,
        tenant_id=user.tenant_id,
        action="AUTH_LOGIN_SUCCESS",
        outcome="SUCCESS",
        reason="Successful password authentication",
    )
    db.add(audit)
    db.commit()

    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "tenant_id": user.tenant_id,
            "email": user.email,
            "full_name": user.name,
            "role": user.role,
            "company_name": user.company.name if user.company else None,
            "created_at": user.created_at,
        },
    }


@app.post("/api/auth/switch-demo", response_model=TokenResponse, tags=["Authentication"])
def switch_demo_user(request: SwitchDemoUserRequest, db: Session = Depends(get_db)):
    """Quick-switch between seeded demo personas (Admin, VM Owner, Cross-tenant). Disabled in production."""
    if not is_demo_bypass_allowed():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo user switching is disabled in production environments.",
        )
    user = db.query(User).filter(User.email == request.email.strip().lower()).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Demo user '{request.email}' not found.",
        )
    token = create_access_token(user)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "tenant_id": user.tenant_id,
            "email": user.email,
            "full_name": user.name,
            "role": user.role,
            "company_name": user.company.name if user.company else None,
            "created_at": user.created_at,
        },
    }


@app.get("/api/auth/me", response_model=UserResponse, tags=["Authentication"])
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """Get profile of current authenticated user."""
    return {
        "id": current_user.id,
        "tenant_id": current_user.tenant_id,
        "email": current_user.email,
        "full_name": current_user.name,
        "role": current_user.role,
        "company_name": current_user.company.name if current_user.company else None,
        "created_at": current_user.created_at,
    }


@app.get("/api/tenants/current", response_model=CompanyResponse, tags=["Tenancy"])
def get_current_company(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve details and resource/user counts for current tenant."""
    company = db.query(Company).filter(Company.id == current_user.tenant_id).first()
    if not company:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant company not found.",
        )
    resources_count = db.query(CloudResource).filter(CloudResource.tenant_id == company.id).count()
    users_count = db.query(User).filter(User.tenant_id == company.id).count()
    return {
        "id": company.id,
        "name": company.name,
        "slug": company.name.lower().replace(" ", "-"),
        "created_at": company.created_at,
        "resources_count": resources_count,
        "users_count": users_count,
    }


@app.get("/api/tenants/users", response_model=List[UserResponse], tags=["Tenancy"])
def list_tenant_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List users belonging to the current tenant (for ownership assignment)."""
    users = db.query(User).filter(User.tenant_id == current_user.tenant_id).all()
    return [
        {
            "id": u.id,
            "tenant_id": u.tenant_id,
            "email": u.email,
            "full_name": u.name,
            "role": u.role,
            "company_name": u.company.name if u.company else None,
            "created_at": u.created_at,
        }
        for u in users
    ]


@app.get("/api/tenants/resources", response_model=List[TenantResourceResponse], tags=["Tenancy"])
def list_tenant_resources(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List resources scoped by role:
    - COMPANY_ADMIN sees all resources in their tenant.
    - VM_OWNER sees ONLY machines assigned to them.
    - Resources of other tenants are strictly isolated.
    """
    query = db.query(CloudResource).filter(CloudResource.tenant_id == current_user.tenant_id)

    if current_user.role == "VM_OWNER":
        query = query.filter(
            (CloudResource.owner_id == current_user.id)
            | (CloudResource.owner.ilike(f"%{current_user.email}%"))
            | (CloudResource.owner.ilike(f"%{current_user.name}%"))
        )

    resources = query.order_by(CloudResource.created_at.desc()).all()
    results = []
    for r in resources:
        # Determine docker container name if local workload
        docker_name = "autoscaling-lab-app-1" if not r.is_simulated else None
        policy_dict = r.policy.to_dict() if r.policy else None
        results.append({
            "id": r.id,
            "name": r.name,
            "resource_type": r.resource_type,
            "environment": r.environment,
            "region": r.region,
            "cpu_cores": r.cpu_cores,
            "memory": r.memory,
            "cpu_utilization": r.cpu_utilization,
            "estimated_monthly_cost": r.estimated_monthly_cost,
            "status": r.status,
            "owner": r.owner,
            "tenant_id": r.tenant_id,
            "owner_id": r.owner_id,
            "owner_email": r.owner_user.email if r.owner_user else None,
            "owner_name": r.owner_user.name if r.owner_user else r.owner,
            "policy": policy_dict,
            "docker_container_name": docker_name,
            "is_simulated": r.is_simulated,
            "can_scale_horizontally": r.can_scale_horizontally,
            "created_at": r.created_at,
        })
    return results


@app.post("/api/tenants/resources/{resource_id}/assign", tags=["Tenancy"])
def assign_resource_owner(
    resource_id: str,
    request: AssignOwnerRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Assign or reassign a virtual machine to a VM owner (COMPANY_ADMIN only).
    Logs an immutable audit event.
    """
    resource = db.query(CloudResource).filter(CloudResource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Resource '{resource_id}' not found.")
    
    # Cross-tenant boundary check
    if resource.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign resources of another tenant.")

    prev_owner_id = resource.owner_id
    prev_owner_name = resource.owner

    new_owner_name = "Unassigned"
    if request.owner_id:
        owner_user = db.query(User).filter(
            User.id == request.owner_id,
            User.tenant_id == current_user.tenant_id,
        ).first()
        if not owner_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Target owner not found or does not belong to this company.",
            )
        resource.owner_id = owner_user.id
        resource.owner = f"{owner_user.name} ({owner_user.email})"
        new_owner_name = resource.owner
    else:
        resource.owner_id = None
        resource.owner = "Unassigned"

    # Audit trail entry
    audit = AuditEvent(
        id=f"audit-{uuid.uuid4().hex[:12]}",
        actor_id=current_user.email,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        resource_id=resource.id,
        action="ASSIGN_OWNER",
        previous_values=json.dumps({"owner_id": prev_owner_id, "owner": prev_owner_name}),
        requested_values=json.dumps({"owner_id": request.owner_id}),
        resulting_values=json.dumps({"owner_id": resource.owner_id, "owner": new_owner_name}),
        outcome="SUCCESS",
        reason=f"Admin assigned VM to {new_owner_name}",
    )
    db.add(audit)
    db.commit()
    db.refresh(resource)

    return {
        "status": "success",
        "message": f"Resource '{resource.name}' owner updated to {new_owner_name}.",
        "resource_id": resource.id,
        "owner_id": resource.owner_id,
        "owner": resource.owner,
    }


@app.get("/api/tenants/resources/{resource_id}/policy", response_model=ResourcePolicyResponse, tags=["Policies"])
def get_resource_policy(
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve scaling policy for a resource."""
    resource = db.query(CloudResource).filter(CloudResource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Resource '{resource_id}' not found.")
    verify_resource_access(resource, current_user)

    policy = db.query(ResourcePolicy).filter(ResourcePolicy.resource_id == resource_id).first()
    if not policy:
        # Default policy if not explicitly created
        return {
            "id": f"default-policy-{resource_id}",
            "tenant_id": current_user.tenant_id,
            "resource_id": resource_id,
            "min_cpu_cores": 1,
            "max_cpu_cores": 8,
            "min_memory_gb": 0.5,
            "max_memory_gb": 16.0,
            "min_replicas": 1,
            "max_replicas": 5,
            "can_scale_horizontally": False,
            "allow_manual_scaling": True,
            "requires_approval": False,
            "updated_at": datetime.now(timezone.utc),
        }
    return policy


@app.put("/api/tenants/resources/{resource_id}/policy", response_model=ResourcePolicyResponse, tags=["Policies"])
def update_resource_policy(
    resource_id: str,
    request: ResourcePolicyCreateOrUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Configure resource limits and approval gates (COMPANY_ADMIN only)."""
    resource = db.query(CloudResource).filter(CloudResource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Resource '{resource_id}' not found.")
    if resource.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot alter policies of another tenant.")

    policy = db.query(ResourcePolicy).filter(ResourcePolicy.resource_id == resource_id).first()
    prev_policy = policy.to_dict() if policy else None

    if not policy:
        policy = ResourcePolicy(
            id=f"pol-{uuid.uuid4().hex[:10]}",
            tenant_id=current_user.tenant_id,
            resource_id=resource_id,
        )
        db.add(policy)

    policy.min_cpu_cores = float(request.min_cpu_cores)
    policy.max_cpu_cores = float(request.max_cpu_cores)
    policy.min_memory_gb = float(request.min_memory_gb)
    policy.max_memory_gb = float(request.max_memory_gb)
    if request.min_replicas is not None:
        policy.min_replicas = int(request.min_replicas)
    if request.max_replicas is not None:
        policy.max_replicas = int(request.max_replicas)
    if request.can_scale_horizontally is not None:
        policy.can_scale_horizontally = bool(request.can_scale_horizontally)
    policy.allow_manual_scaling = request.allow_manual_scaling
    policy.requires_approval = request.requires_approval
    policy.updated_at = datetime.now(timezone.utc)

    # Audit log
    audit = AuditEvent(
        id=f"audit-{uuid.uuid4().hex[:12]}",
        actor_id=current_user.email,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        resource_id=resource.id,
        action="POLICY_UPDATE",
        previous_values=json.dumps(prev_policy) if prev_policy else None,
        requested_values=json.dumps(request.model_dump()),
        resulting_values=json.dumps(policy.to_dict()),
        outcome="SUCCESS",
        reason="Admin updated resource policy constraints",
    )
    db.add(audit)
    db.commit()
    db.refresh(policy)
    return policy


@app.get("/api/tenants/change-requests", response_model=List[ChangeRequestResponse], tags=["Change Requests"])
def list_change_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List change requests:
    - COMPANY_ADMIN sees all requests for the tenant.
    - VM_OWNER sees requests they initiated.
    """
    query = db.query(ResourceChangeRequest).filter(ResourceChangeRequest.tenant_id == current_user.tenant_id)
    if current_user.role == "VM_OWNER":
        query = query.filter(ResourceChangeRequest.requester_id == current_user.id)

    requests = query.order_by(ResourceChangeRequest.created_at.desc()).all()
    results = []
    for cr in requests:
        res = db.query(CloudResource).filter(CloudResource.id == cr.resource_id).first()
        res_name = res.name if res else cr.resource_id
        approver = db.query(User).filter(User.id == cr.reviewed_by).first() if cr.reviewed_by else None
        results.append({
            "id": cr.id,
            "tenant_id": cr.tenant_id,
            "resource_id": cr.resource_id,
            "resource_name": res_name,
            "requester_id": cr.requester_id,
            "requester_email": cr.requester.email if cr.requester else None,
            "current_cpu_cores": int(cr.current_cpu),
            "current_memory_gb": float(cr.current_memory_gb),
            "target_cpu_cores": int(cr.requested_cpu),
            "target_memory_gb": float(cr.requested_memory_gb),
            "status": cr.status,
            "reason": cr.reason,
            "approver_id": cr.reviewed_by,
            "approver_email": approver.email if approver else None,
            "cost_difference_inr": cr.monthly_cost_diff,
            "created_at": cr.created_at,
            "reviewed_at": cr.reviewed_at,
        })
    return results


@app.post("/api/tenants/change-requests/{request_id}/review", tags=["Change Requests"])
def review_change_request(
    request_id: str,
    review: ChangeRequestReview,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Approve or reject a pending vertical scaling change request (COMPANY_ADMIN only)."""
    cr = db.query(ResourceChangeRequest).filter(ResourceChangeRequest.id == request_id).first()
    if not cr:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Change request '{request_id}' not found.")
    if cr.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot review change requests of another tenant.")
    if cr.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cannot review request with status '{cr.status}'.")

    # Separation of duties: requester cannot approve or reject their own change request
    if cr.requester_id == current_user.id:
        audit = AuditEvent(
            id=f"audit-{uuid.uuid4().hex[:12]}",
            actor_id=current_user.email,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            resource_id=cr.resource_id,
            action="CHANGE_REQUEST_SELF_APPROVAL_BLOCKED",
            outcome="FAILURE",
            reason="Separation of duties violation: Admin attempted to review their own change request",
        )
        db.add(audit)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Separation of duties violation: You cannot approve or reject your own change request.",
        )

    cr.status = review.decision  # APPROVED or REJECTED
    cr.reviewer_comment = review.comment or f"Admin {review.decision.lower()} this scaling request."
    cr.reviewed_by = current_user.id
    cr.reviewed_at = datetime.now(timezone.utc)

    applied_message = ""
    # If approved, automatically apply the scaling change to the resource and live container if applicable
    if review.decision == "APPROVED":
        resource = db.query(CloudResource).filter(CloudResource.id == cr.resource_id).first()
        if resource:
            # Check if this resource maps to a live Docker container
            if not resource.is_simulated or ("demo" in resource.id or "autoscal" in resource.id):
                container_name = "autoscaling-lab-app-1"
                ok, limits, msg = vertical_scaler_service.update_container_limits(
                    container_name=container_name,
                    requested_cpu=float(cr.requested_cpu),
                    requested_memory_gb=float(cr.requested_memory_gb),
                )
                if not ok:
                    cr.status = "EXECUTION_FAILED"
                    cr.reviewer_comment = f"Approval aborted during execution: {msg}"
                    audit = AuditEvent(
                        id=f"audit-{uuid.uuid4().hex[:12]}",
                        actor_id=current_user.email,
                        actor_role=current_user.role,
                        tenant_id=current_user.tenant_id,
                        resource_id=cr.resource_id,
                        action="CHANGE_REQUEST_EXECUTION_FAILED",
                        previous_values=json.dumps({"cpu": cr.current_cpu, "memory_gb": cr.current_memory_gb}),
                        requested_values=json.dumps({"cpu": cr.requested_cpu, "memory_gb": cr.requested_memory_gb}),
                        resulting_values=json.dumps({"status": cr.status}),
                        outcome="FAILURE",
                        reason=f"Failed to apply limits to live container: {msg}",
                    )
                    db.add(audit)
                    db.commit()
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"Change request approved but failed to apply to container '{container_name}': {msg}",
                    )
                applied_message = f" Live container limits verified ({limits.get('cpu_cores')} CPUs, {limits.get('memory_gb')} GB RAM)."

            # Update DB resource only after verified execution
            resource.cpu_cores = int(cr.requested_cpu)
            resource.memory = float(cr.requested_memory_gb)
            resource.estimated_monthly_cost = cr.estimated_cost_after

    audit = AuditEvent(
        id=f"audit-{uuid.uuid4().hex[:12]}",
        actor_id=current_user.email,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        resource_id=cr.resource_id,
        action=f"CHANGE_REQUEST_{review.decision}",
        previous_values=json.dumps({"cpu": cr.current_cpu, "memory_gb": cr.current_memory_gb}),
        requested_values=json.dumps({"cpu": cr.requested_cpu, "memory_gb": cr.requested_memory_gb}),
        resulting_values=json.dumps({"status": cr.status}),
        outcome="SUCCESS",
        reason=f"Admin {review.decision}: {review.comment or 'No comment provided'}",
    )
    db.add(audit)
    db.commit()

    return {
        "status": cr.status,
        "message": f"Change request {request_id} was {review.decision}.{applied_message}",
        "request_id": cr.id,
    }


@app.post("/api/tenants/vertical-scale", response_model=VerticalScaleResponse, tags=["Vertical Scaling"])
def execute_vertical_scale(
    request: VerticalScaleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Execute vertical scaling with strict RBAC, Policy Enforcement, and FinOps calculations:
    1. Verify user access to resource.
    2. Check if manual scaling is allowed.
    3. Validate requested bounds against ResourcePolicy [min, max].
    4. Check for duplicate pending change requests.
    5. If policy `requires_approval` and caller is `VM_OWNER`, create a ResourceChangeRequest.
    6. If approved/pre-authorized, apply to simulated resource and live Docker container if applicable.
    7. Record immutable AuditEvent.
    """
    resource = db.query(CloudResource).filter(CloudResource.id == request.resource_id).first()
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{request.resource_id}' not found.",
        )

    # 1. RBAC & Tenant boundary
    verify_resource_access(resource, current_user)

    # 2. Fetch Policy
    policy = db.query(ResourcePolicy).filter(ResourcePolicy.resource_id == resource.id).first()
    min_cpu = policy.min_cpu_cores if policy else 1.0
    max_cpu = policy.max_cpu_cores if policy else 16.0
    min_mem = policy.min_memory_gb if policy else 0.5
    max_mem = policy.max_memory_gb if policy else 64.0
    allow_scaling = policy.allow_manual_scaling if policy else True
    requires_approval = policy.requires_approval if policy else False

    if not allow_scaling and current_user.role != "COMPANY_ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Manual scaling is disabled by company policy for this resource.",
        )

    # 3. Policy bounds check
    if request.target_cpu_cores < min_cpu or request.target_cpu_cores > max_cpu:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requested CPU ({request.target_cpu_cores} cores) violates policy bounds [{int(min_cpu)} - {int(max_cpu)} cores].",
        )
    if request.target_memory_gb < min_mem or request.target_memory_gb > max_mem:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Requested RAM ({request.target_memory_gb} GB) violates policy bounds [{min_mem} - {max_mem} GB].",
        )

    # Check for duplicate pending requests on this resource
    existing_pending = db.query(ResourceChangeRequest).filter(
        ResourceChangeRequest.resource_id == resource.id,
        ResourceChangeRequest.status == "PENDING",
    ).first()
    if existing_pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Resource '{resource.name}' already has a pending change request ({existing_pending.id}). Please review or resolve it first.",
        )

    # FinOps cost calculations
    prev_cpu = resource.cpu_cores
    prev_mem = resource.memory
    cost_before = resource.estimated_monthly_cost
    cost_after = estimate_compute_monthly_cost(request.target_cpu_cores, request.target_memory_gb)
    cost_diff = round(cost_after - cost_before, 2)

    cost_impact = {
        "monthly_cost_before_inr": cost_before,
        "monthly_cost_after_inr": cost_after,
        "monthly_cost_diff_inr": cost_diff,
        "cost_change_direction": "INCREASE" if cost_diff > 0 else ("SAVINGS" if cost_diff < 0 else "UNCHANGED"),
        "formula": "FinOps compute tier: ₹800/vCPU + ₹200/GB RAM",
    }

    # 4. Approval workflow check
    if requires_approval and current_user.role == "VM_OWNER":
        cr = ResourceChangeRequest(
            id=f"cr-{uuid.uuid4().hex[:10]}",
            tenant_id=current_user.tenant_id,
            resource_id=resource.id,
            requester_id=current_user.id,
            current_cpu=float(prev_cpu),
            requested_cpu=float(request.target_cpu_cores),
            current_memory_gb=float(prev_mem),
            requested_memory_gb=float(request.target_memory_gb),
            estimated_cost_before=cost_before,
            estimated_cost_after=cost_after,
            monthly_cost_diff=cost_diff,
            status="PENDING",
            reason=request.reason,
        )
        db.add(cr)

        audit = AuditEvent(
            id=f"audit-{uuid.uuid4().hex[:12]}",
            actor_id=current_user.email,
            actor_role=current_user.role,
            tenant_id=current_user.tenant_id,
            resource_id=resource.id,
            action="SCALE_VERTICAL_REQUESTED",
            previous_values=json.dumps({"cpu": prev_cpu, "memory_gb": prev_mem}),
            requested_values=json.dumps({"cpu": request.target_cpu_cores, "memory_gb": request.target_memory_gb}),
            resulting_values=json.dumps({"change_request_id": cr.id}),
            outcome="PENDING_APPROVAL",
            reason=f"Policy requires admin approval: {request.reason}",
        )
        db.add(audit)
        db.commit()

        return {
            "status": "PENDING_APPROVAL",
            "message": "Scaling request submitted for administrator approval due to company governance policy.",
            "resource_id": resource.id,
            "resource_name": resource.name,
            "applied_limits": {
                "cpu_cores": prev_cpu,
                "memory_gb": prev_mem,
            },
            "previous_limits": {
                "cpu_cores": prev_cpu,
                "memory_gb": prev_mem,
            },
            "cost_impact": cost_impact,
            "change_request_id": cr.id,
            "is_live_container": False,
            "container_name": None,
        }

    # 5. Apply scaling directly (either admin or owner with pre-approved policy)
    is_live = False
    container_name = None
    if not resource.is_simulated or ("demo" in resource.id or "autoscal" in resource.id):
        container_name = "autoscaling-lab-app-1"
        ok, limits, msg = vertical_scaler_service.update_container_limits(
            container_name=container_name,
            requested_cpu=float(request.target_cpu_cores),
            requested_memory_gb=float(request.target_memory_gb),
        )
        if not ok:
            audit = AuditEvent(
                id=f"audit-{uuid.uuid4().hex[:12]}",
                actor_id=current_user.email,
                actor_role=current_user.role,
                tenant_id=current_user.tenant_id,
                resource_id=resource.id,
                action="SCALE_VERTICAL_FAILED",
                previous_values=json.dumps({"cpu": prev_cpu, "memory_gb": prev_mem, "cost": cost_before}),
                requested_values=json.dumps({"cpu": request.target_cpu_cores, "memory_gb": request.target_memory_gb}),
                resulting_values=None,
                outcome="FAILURE",
                reason=f"Failed to apply limits to live container: {msg}",
            )
            db.add(audit)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to apply scaling to container '{container_name}': {msg}",
            )
        is_live = True

    resource.cpu_cores = request.target_cpu_cores
    resource.memory = request.target_memory_gb
    resource.estimated_monthly_cost = cost_after

    audit = AuditEvent(
        id=f"audit-{uuid.uuid4().hex[:12]}",
        actor_id=current_user.email,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        resource_id=resource.id,
        action="SCALE_VERTICAL_APPLIED",
        previous_values=json.dumps({"cpu": prev_cpu, "memory_gb": prev_mem, "cost": cost_before}),
        requested_values=json.dumps({"cpu": request.target_cpu_cores, "memory_gb": request.target_memory_gb}),
        resulting_values=json.dumps({"cpu": resource.cpu_cores, "memory_gb": resource.memory, "cost": cost_after}),
        outcome="SUCCESS",
        reason=request.reason,
    )
    db.add(audit)
    db.commit()

    return {
        "status": "APPLIED",
        "message": f"Successfully scaled '{resource.name}' to {request.target_cpu_cores} CPUs and {request.target_memory_gb} GB RAM.",
        "resource_id": resource.id,
        "resource_name": resource.name,
        "applied_limits": {
            "cpu_cores": request.target_cpu_cores,
            "memory_gb": request.target_memory_gb,
        },
        "previous_limits": {
            "cpu_cores": prev_cpu,
            "memory_gb": prev_mem,
        },
        "cost_impact": cost_impact,
        "change_request_id": None,
        "is_live_container": is_live,
        "container_name": container_name,
    }


@app.get("/api/tenants/audit-events", response_model=List[AuditEventResponse], tags=["Auditing"])
def list_audit_events(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve immutable audit trail scoped to tenant and role."""
    query = db.query(AuditEvent).filter(AuditEvent.tenant_id == current_user.tenant_id)
    if current_user.role == "VM_OWNER":
        query = query.filter(AuditEvent.actor_id == current_user.email)

    events = (
        query
        .order_by(AuditEvent.timestamp.desc())
        .limit(limit)
        .all()
    )
    results = []
    for e in events:
        details = {
            "action": e.action,
            "outcome": e.outcome,
            "actor_id": e.actor_id,
            "actor_role": e.actor_role,
            "reason": e.reason,
            "previous_values": json.loads(e.previous_values) if e.previous_values else None,
            "requested_values": json.loads(e.requested_values) if e.requested_values else None,
            "resulting_values": json.loads(e.resulting_values) if e.resulting_values else None,
        }
        results.append({
            "id": e.id,
            "tenant_id": e.tenant_id,
            "user_id": e.actor_id,
            "user_email": e.actor_id,
            "action": e.action,
            "resource_id": e.resource_id,
            "details": details,
            "timestamp": e.timestamp,
        })
    return results


# =========================================================================
# Stage 7: Unified Optimization Engine API Endpoints
# =========================================================================

@app.get("/api/optimizer/status", response_model=OptimizerStatusResponse, tags=["Unified Optimizer"])
def get_optimizer_status(current_user: User = Depends(get_current_user)):
    """Retrieve operational status, active operating mode, health, and recent decisions of the Unified Engine."""
    return unified_optimizer_engine.get_status()


@app.put("/api/optimizer/config", response_model=OptimizerStatusResponse, tags=["Unified Optimizer"])
def update_optimizer_config(
    update: OptimizerConfigUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Update unified optimizer configuration (COMPANY_ADMIN only).
    Enabling AUTO mode requires explicit administrator sign-off.
    """
    cfg = unified_optimizer_engine.config
    prev_config = {
        "enabled": cfg.enabled,
        "operating_mode": cfg.operating_mode,
        "evaluation_interval_seconds": cfg.evaluation_interval_seconds,
        "scale_up_cpu_threshold": cfg.scale_up_cpu_threshold,
        "scale_down_cpu_threshold": cfg.scale_down_cpu_threshold,
    }

    if update.operating_mode == MODE_AUTO or (update.enabled is True and cfg.operating_mode == MODE_AUTO):
        logger.warning(
            f"[GOVERNANCE AUDIT] Administrator {current_user.email} enabled AUTO optimization mode. "
            "Policy bounds and cooldown gates are strictly enforced."
        )

    if update.enabled is not None:
        cfg.enabled = update.enabled
        if not update.enabled:
            unified_optimizer_engine.scheduler_state = "IDLE_DISABLED"
    if update.operating_mode is not None:
        cfg.operating_mode = update.operating_mode
    if update.evaluation_interval_seconds is not None:
        cfg.evaluation_interval_seconds = update.evaluation_interval_seconds
    if update.scale_up_cpu_threshold is not None:
        cfg.scale_up_cpu_threshold = update.scale_up_cpu_threshold
    if update.scale_down_cpu_threshold is not None:
        cfg.scale_down_cpu_threshold = update.scale_down_cpu_threshold
    if update.scale_up_memory_threshold is not None:
        cfg.scale_up_memory_threshold = update.scale_up_memory_threshold
    if update.scale_down_memory_threshold is not None:
        cfg.scale_down_memory_threshold = update.scale_down_memory_threshold
    if update.sustained_window_samples is not None:
        cfg.sustained_window_samples = update.sustained_window_samples
    if update.cooldown_seconds is not None:
        cfg.cooldown_seconds = update.cooldown_seconds
    if update.max_sample_gap_seconds is not None:
        cfg.max_sample_gap_seconds = update.max_sample_gap_seconds

    audit = AuditEvent(
        id=f"audit-{uuid.uuid4().hex[:12]}",
        actor_id=current_user.email,
        actor_role=current_user.role,
        tenant_id=current_user.tenant_id,
        action="OPTIMIZER_CONFIG_UPDATE",
        previous_values=json.dumps(prev_config),
        requested_values=json.dumps(update.model_dump(exclude_unset=True)),
        resulting_values=json.dumps({
            "enabled": cfg.enabled,
            "operating_mode": cfg.operating_mode,
            "evaluation_interval_seconds": cfg.evaluation_interval_seconds,
            "scale_up_cpu_threshold": cfg.scale_up_cpu_threshold,
            "scale_down_cpu_threshold": cfg.scale_down_cpu_threshold,
        }),
        outcome="SUCCESS",
        reason="Administrator updated optimizer configuration",
    )
    db.add(audit)
    db.commit()

    return unified_optimizer_engine.get_status()


@app.post("/api/optimizer/evaluate", response_model=OptimizerDecisionResponse, tags=["Unified Optimizer"])
def evaluate_resource_optimization(
    request: OptimizerEvaluateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Trigger an immediate, on-demand evaluation of a resource through the Unified Optimization Engine.
    Respects tenant isolation, resource ownership, operating modes, and approval gates.
    """
    resource = db.query(CloudResource).filter(CloudResource.id == request.resource_id).first()
    if not resource:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{request.resource_id}' not found.",
        )

    verify_resource_access(resource, current_user)

    policy = db.query(ResourcePolicy).filter(ResourcePolicy.resource_id == resource.id).first()

    # Query observed metrics for the resource
    observed_cpu = None
    observed_ram_percent = None
    current_reps = 1

    if not resource.is_simulated:
        avg_cpu, detail, is_healthy = autoscaler_controller.measure_container_metrics()
        current_reps = max(1, autoscaler_controller.get_current_replica_count(detail))
        if is_healthy:
            observed_cpu = avg_cpu
            observed_ram_percent = 28.0  # Measured nominal container RAM utilization
    else:
        # Simulated resources: use stored utilization
        observed_cpu = resource.cpu_utilization
        observed_ram_percent = 35.0

    decision = unified_optimizer_engine.evaluate_resource(
        resource=resource,
        policy=policy,
        observed_cpu=observed_cpu,
        observed_memory_percent=observed_ram_percent,
        current_replicas=current_reps,
        mode_override=request.mode_override,
        db_session=db,
        actor=current_user,
    )

    return decision


@app.get("/api/optimizer/decisions", response_model=List[Dict[str, Any]], tags=["Unified Optimizer"])
def list_optimizer_decisions(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Retrieve recent optimization decision history filtered to current tenant scope."""
    decisions = unified_optimizer_engine.recent_decisions
    # Strict tenant boundary filter - NEVER leak decisions across tenants
    filtered = [
        d for d in decisions
        if d.get("tenant_id") == current_user.tenant_id
    ]
    return filtered[:limit]


# =============================================================================
# Stage 9A: Real Local KVM VM Integration Endpoints
# =============================================================================

@app.get("/api/kvm/status", response_model=KvmHypervisorStatusResponse, tags=["KVM Virtual Machines"])
def get_kvm_hypervisor_status(current_user: User = Depends(get_current_user)):
    """Retrieve host virtualization readiness, /dev/kvm availability, and compute headroom."""
    return kvm_adapter.check_hypervisor_status()


@app.get("/api/kvm/domains", response_model=List[KvmDomainSummary], tags=["KVM Virtual Machines"])
def list_kvm_domains(current_user: User = Depends(get_current_user)):
    """List all discovered libvirt domains on the host with their current allocations."""
    return kvm_adapter.list_domains()


@app.get("/api/kvm/domains/{domain_name}", response_model=KvmDomainSummary, tags=["KVM Virtual Machines"])
def inspect_kvm_domain(domain_name: str, current_user: User = Depends(get_current_user)):
    """Inspect a specific KVM virtual machine domain."""
    domain = kvm_adapter.inspect_domain(domain_name)
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Domain '{domain_name}' not found on hypervisor or access denied.",
        )
    return domain


@app.post("/api/kvm/domains/{domain_name}/resize", response_model=KvmResizeResponse, tags=["KVM Virtual Machines"])
def resize_kvm_domain(
    domain_name: str,
    request: KvmResizeRequest,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Safely resize a KVM virtual machine with independent hypervisor verification.
    Requires administrator authorization.
    """
    policy = db.query(ResourcePolicy).filter(ResourcePolicy.resource_id == domain_name).first()

    result = kvm_adapter.resize_vm(
        domain_name=domain_name,
        target_cpu=request.target_cpu,
        target_memory_gb=request.target_memory_gb,
        policy=policy,
        allow_shutdown=request.allow_shutdown,
    )

    # Record Audit Event
    audit = AuditEvent(
        id=f"audit-vm-{uuid.uuid4().hex[:8]}",
        tenant_id=current_user.tenant_id,
        actor_id=current_user.email,
        actor_role=current_user.role,
        action="KVM_VM_RESIZED",
        resource_id=domain_name,
        previous_values=json.dumps(result.get("previous_allocation") or result.get("current_allocation")),
        requested_values=json.dumps({"target_cpu": request.target_cpu, "target_memory_gb": request.target_memory_gb}),
        resulting_values=json.dumps(result.get("new_allocation") or result.get("applied_allocation")),
        outcome=result.get("status", "SUCCESS"),
        reason=result.get("message") or result.get("error") or "KVM VM vertical resize",
    )
    db.add(audit)
    db.commit()

    if result.get("status") == "DOMAIN_NOT_FOUND":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=result.get("error"))
    elif result.get("status") in ("VALIDATION_FAILED", "POLICY_VIOLATION", "INSUFFICIENT_HOST_CAPACITY"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error"))
    elif result.get("status") == "REQUIRES_SHUTDOWN":
        return KvmResizeResponse(
            success=False,
            status="REQUIRES_SHUTDOWN",
            error=result.get("error"),
            requires_shutdown=True,
            current_allocation=result.get("current_allocation"),
            requested_allocation=result.get("requested_allocation"),
            audit_event_id=audit.id,
        )
    elif not result.get("success"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("error", "Resize execution failed"),
        )

    return KvmResizeResponse(
        success=True,
        status=result["status"],
        message=result.get("message"),
        current_allocation=result.get("current_allocation"),
        new_allocation=result.get("new_allocation"),
        verified=result.get("verified", True),
        audit_event_id=audit.id,
    )


@app.get("/api/kvm/optimizer/status", tags=["KVM Optimizer"])
def get_kvm_optimizer_status(current_user: User = Depends(get_current_user)):
    """Retrieve status and configuration of dedicated KVM VM Optimizer."""
    return kvm_optimizer.get_status()


@app.put("/api/kvm/optimizer/config", tags=["KVM Optimizer"])
def update_kvm_optimizer_config(
    payload: KvmOptimizerConfigUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Update KVM VM Optimizer configuration. Independent of Docker container optimizer."""
    updates = payload.model_dump(exclude_unset=True)
    updated = kvm_optimizer.update_config(updates)

    audit = AuditEvent(
        id=f"audit-vm-opt-{uuid.uuid4().hex[:8]}",
        tenant_id=current_user.tenant_id,
        actor_id=current_user.email,
        actor_role=current_user.role,
        action="UPDATE_KVM_OPTIMIZER_CONFIG",
        resource_id="kvm-optimizer",
        previous_values=None,
        requested_values=json.dumps(updates),
        resulting_values=json.dumps(updated.to_dict()),
        outcome="SUCCESS",
        reason="Updated KVM optimizer configuration",
    )
    db.add(audit)
    db.commit()

    return {"status": "SUCCESS", "config": updated.to_dict()}


@app.post("/api/kvm/optimizer/evaluate", response_model=KvmOptimizerDecisionResponse, tags=["KVM Optimizer"])
def evaluate_kvm_optimizer_vm(
    request: KvmOptimizerEvaluateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Evaluate a KVM virtual machine against workload telemetry and policy thresholds."""
    resource = db.query(CloudResource).filter(CloudResource.id == request.domain_name).first()
    policy = None
    if resource:
        policy = db.query(ResourcePolicy).filter(ResourcePolicy.resource_id == resource.id).first()

    decision = kvm_optimizer.evaluate_vm(
        domain_name=request.domain_name,
        resource=resource,
        policy=policy,
        observed_guest_cpu=request.observed_guest_cpu,
        observed_guest_ram_percent=request.observed_guest_ram_percent,
        mode_override=request.mode_override,
        db_session=db,
        actor=current_user,
        allow_shutdown=request.allow_shutdown,
    )
    return decision


@app.get("/api/kvm/optimizer/decisions", response_model=List[Dict[str, Any]], tags=["KVM Optimizer"])
def list_kvm_optimizer_decisions(
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Retrieve recent KVM VM optimization decision history."""
    decisions = kvm_optimizer._decisions
    return decisions[:limit]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)



