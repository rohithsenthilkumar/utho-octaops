"""
SmartCloud Optimizer — Stage 7 Unified Optimization Engine Unit Tests
======================================================================
Comprehensive test suite verifying:
1. High sustained CPU triggers scale-up decision.
2. Low sustained CPU triggers scale-down decision.
3. Memory thresholds trigger resource scaling.
4. Insufficient consecutive samples result in NO_ACTION (sustained window enforcement).
5. Missing metrics result in safe NO_ACTION (never assumes zero).
6. Active cooldown prevents rapid oscillation.
7. Policy boundaries [min, max] strictly respected.
8. Operating modes: DRY_RUN and RECOMMENDATION do not alter container limits.
9. AUTO mode executes and verifies authorized scaling action.
10. Execution errors / post-action verification mismatches are reported accurately.
11. Approval-required policies generate change requests without execution.
12. Multi-replica horizontal scaling cost calculations.
"""
import pytest
from models import CloudResource, ResourcePolicy, User
from engines.unified_optimizer import (
    UnifiedOptimizationEngine,
    OptimizationEngineConfig,
    DECISION_NO_ACTION,
    DECISION_SCALE_UP_VERTICAL,
    DECISION_SCALE_DOWN_VERTICAL,
    DECISION_SCALE_OUT_HORIZONTAL,
    DECISION_SCALE_IN_HORIZONTAL,
    DECISION_RECOMMENDATION_ONLY,
    DECISION_APPROVAL_REQUIRED,
    DECISION_BLOCKED_BY_POLICY,
    MODE_DRY_RUN,
    MODE_RECOMMENDATION,
    MODE_AUTO,
)
from engines.vertical_scaler import VerticalScalingService
from engines.autoscaler import AutoscalingController


@pytest.fixture
def mock_engine():
    """Build isolated UnifiedOptimizationEngine instance in mock mode."""
    v_scaler = VerticalScalingService()
    v_scaler._mock_mode = True
    v_scaler._mock_containers["autoscaling-lab-app-1"] = {
        "cpu_cores": 2.0,
        "memory_gb": 1.0,
        "status": "running",
    }

    h_scaler = AutoscalingController()
    h_scaler._mock_mode = True
    h_scaler._mock_replicas = 1

    config = OptimizationEngineConfig(
        enabled=True,
        operating_mode=MODE_DRY_RUN,
        scale_up_cpu_threshold=75.0,
        scale_down_cpu_threshold=25.0,
        scale_up_memory_threshold=80.0,
        scale_down_memory_threshold=40.0,
        sustained_window_samples=3,
        cooldown_seconds=60.0,
    )
    return UnifiedOptimizationEngine(config=config, vertical_scaler=v_scaler, autoscaler=h_scaler)


@pytest.fixture
def sample_resource():
    return CloudResource(
        id="demo-docker-app-01",
        name="autoscaling-lab-app-1 [Docker Workload]",
        resource_type="Docker Container",
        environment="dev",
        region="Bangalore",
        cpu_cores=2,
        memory=1.0,
        cpu_utilization=50.0,
        estimated_monthly_cost=1800.0,
        status="ACTIVE",
        tenant_id="tenant-cloudflow",
        owner="devops@cloudflow.com",
    )


@pytest.fixture
def sample_policy():
    return ResourcePolicy(
        id="policy-docker-demo",
        tenant_id="tenant-cloudflow",
        resource_id="demo-docker-app-01",
        min_cpu_cores=1.0,
        max_cpu_cores=8.0,
        min_memory_gb=0.5,
        max_memory_gb=16.0,
        min_replicas=1,
        max_replicas=5,
        allow_manual_scaling=True,
        allow_auto_scaling=True,
        requires_approval=False,
    )


def test_missing_metrics_safe_no_action(mock_engine, sample_resource, sample_policy):
    """Missing or None metrics must result in safe NO_ACTION without assuming 0% load."""
    dec = mock_engine.evaluate_resource(
        resource=sample_resource,
        policy=sample_policy,
        observed_cpu=None,
        observed_memory_percent=None,
    )
    assert dec["decision"] == DECISION_NO_ACTION
    assert "missing or unavailable" in dec["reason"]
    assert dec["executed"] is False


def test_sustained_window_enforcement_high_cpu(mock_engine, sample_resource, sample_policy):
    """Single or double spikes must NOT trigger scale up until sustained samples equal 3."""
    # Sample 1: 90% CPU -> Evaluating sustained window
    dec1 = mock_engine.evaluate_resource(
        resource=sample_resource,
        policy=sample_policy,
        observed_cpu=90.0,
        observed_memory_percent=30.0,
    )
    assert dec1["decision"] == DECISION_NO_ACTION
    assert "sample 1 of 3" in dec1["reason"]

    # Sample 2: 85% CPU -> Evaluating sustained window
    dec2 = mock_engine.evaluate_resource(
        resource=sample_resource,
        policy=sample_policy,
        observed_cpu=85.0,
        observed_memory_percent=30.0,
    )
    assert dec2["decision"] == DECISION_NO_ACTION
    assert "sample 2 of 3" in dec2["reason"]

    # Sample 3: 88% CPU -> Sustained window met!
    dec3 = mock_engine.evaluate_resource(
        resource=sample_resource,
        policy=sample_policy,
        observed_cpu=88.0,
        observed_memory_percent=30.0,
    )
    # Since current_replicas=1 and max_replicas=5, horizontal scale-out is preferred
    assert dec3["decision"] in (DECISION_SCALE_OUT_HORIZONTAL, DECISION_SCALE_UP_VERTICAL)
    assert dec3["proposed_allocation"]["replicas"] == 2
    assert "DRY_RUN mode active" in dec3["reason"]
    assert dec3["executed"] is False


def test_memory_threshold_scale_up(mock_engine, sample_resource, sample_policy):
    """Memory exceeding 80% threshold sustained for 3 samples triggers scale-up."""
    for _ in range(2):
        mock_engine.evaluate_resource(
            resource=sample_resource,
            policy=sample_policy,
            observed_cpu=40.0,
            observed_memory_percent=85.0,
        )
    dec = mock_engine.evaluate_resource(
        resource=sample_resource,
        policy=sample_policy,
        observed_cpu=40.0,
        observed_memory_percent=85.0,
    )
    assert dec["decision"] in (DECISION_SCALE_OUT_HORIZONTAL, DECISION_SCALE_UP_VERTICAL)


def test_low_sustained_cpu_scale_down(mock_engine, sample_resource, sample_policy):
    """Low CPU (10%) and Low RAM (20%) sustained for 3 samples triggers scale-in / scale-down."""
    # When already at min_replicas=1, vertical scale down should be proposed
    for _ in range(2):
        mock_engine.evaluate_resource(
            resource=sample_resource,
            policy=sample_policy,
            observed_cpu=10.0,
            observed_memory_percent=20.0,
            current_replicas=1,
        )
    dec = mock_engine.evaluate_resource(
        resource=sample_resource,
        policy=sample_policy,
        observed_cpu=10.0,
        observed_memory_percent=20.0,
        current_replicas=1,
    )
    assert dec["decision"] == DECISION_SCALE_DOWN_VERTICAL
    assert dec["proposed_allocation"]["cpu_cores"] == 1.0  # Downsized from 2 to min 1 core
    assert dec["estimated_cost_after_inr"] < dec["estimated_cost_before_inr"]


def test_policy_bounds_prevent_further_scale_down(mock_engine, sample_resource, sample_policy):
    """When already at policy minimum (1 core, 0.5 GB), low metrics do not trigger scale down."""
    sample_resource.cpu_cores = 1
    sample_resource.memory = 0.5
    for _ in range(3):
        dec = mock_engine.evaluate_resource(
            resource=sample_resource,
            policy=sample_policy,
            observed_cpu=5.0,
            observed_memory_percent=15.0,
            current_replicas=1,
        )
    assert dec["decision"] == DECISION_NO_ACTION
    assert "already at minimum policy bounds" in dec["reason"]


def test_approval_required_policy_blocks_auto_execution(mock_engine, sample_resource, sample_policy):
    """When policy has requires_approval=True and actor is VM Owner, returns APPROVAL_REQUIRED."""
    sample_policy.requires_approval = True
    mock_engine.config.operating_mode = MODE_AUTO

    # Fulfill 3 sustained samples
    for _ in range(2):
        mock_engine.evaluate_resource(
            resource=sample_resource,
            policy=sample_policy,
            observed_cpu=90.0,
            observed_memory_percent=85.0,
        )
    dec = mock_engine.evaluate_resource(
        resource=sample_resource,
        policy=sample_policy,
        observed_cpu=90.0,
        observed_memory_percent=85.0,
    )
    assert dec["decision"] == DECISION_APPROVAL_REQUIRED
    assert dec["executed"] is False
    assert "approval before automated scaling" in dec["reason"]


def test_auto_mode_executes_and_verifies_limits(mock_engine, sample_resource, sample_policy):
    """In AUTO mode with an authorized action, executes and marks verified=True."""
    mock_engine.config.operating_mode = MODE_AUTO
    # Simulate a single-instance workload to test vertical execution
    sample_resource.id = "vm-blr-prod-01"
    sample_resource.name = "prod-db-cluster-01"
    sample_policy.max_replicas = 1

    for _ in range(2):
        mock_engine.evaluate_resource(
            resource=sample_resource,
            policy=sample_policy,
            observed_cpu=90.0,
            observed_memory_percent=85.0,
        )
    dec = mock_engine.evaluate_resource(
        resource=sample_resource,
        policy=sample_policy,
        observed_cpu=90.0,
        observed_memory_percent=85.0,
    )
    assert dec["executed"] is True
    assert dec["verified"] is True
    assert dec["decision"] == DECISION_SCALE_UP_VERTICAL
    assert mock_engine.vertical_scaler._mock_containers["autoscaling-lab-app-1"]["cpu_cores"] == 4.0


def test_cooldown_active_prevents_oscillation(mock_engine, sample_resource, sample_policy):
    """Following an execution, cooldown timer blocks any immediate subsequent actions."""
    mock_engine.config.operating_mode = MODE_AUTO
    sample_resource.id = "vm-blr-prod-01"
    sample_resource.name = "autoscaling-lab-app-1"

    # Trigger action to set cooldown
    for _ in range(3):
        mock_engine.evaluate_resource(
            resource=sample_resource,
            policy=sample_policy,
            observed_cpu=90.0,
            observed_memory_percent=85.0,
        )

    # Immediately evaluate low load
    dec = mock_engine.evaluate_resource(
        resource=sample_resource,
        policy=sample_policy,
        observed_cpu=10.0,
        observed_memory_percent=15.0,
    )
    assert dec["decision"] == DECISION_NO_ACTION
    assert mock_engine.get_remaining_cooldown(sample_resource.id) > 0


def test_cost_calculation_replica_accounting(mock_engine, sample_resource, sample_policy):
    """Cost before and after must account for all replicas (2 vCPU, 1 GB = ₹1800 per replica)."""
    # 2 replicas: ₹1800 * 2 = ₹3600
    curr_reps = 2
    sample_resource.cpu_cores = 2
    sample_resource.memory = 1.0
    sample_resource.estimated_monthly_cost = 3600.0

    for _ in range(3):
        dec = mock_engine.evaluate_resource(
            resource=sample_resource,
            policy=sample_policy,
            observed_cpu=90.0,
            observed_memory_percent=85.0,
            current_replicas=curr_reps,
        )
    # Proposed replicas: 3 -> Total cost: ₹1800 * 3 = ₹5400
    assert dec["estimated_cost_before_inr"] == 3600.0
    assert dec["estimated_cost_after_inr"] == 5400.0
    assert dec["estimated_monthly_savings_inr"] == -1800.0


# =========================================================================
# Stage 7.1: Correctness and Reliability Tests
# =========================================================================

class MockClock:
    def __init__(self, start: float = 1000.0):
        self.time = start

    def __call__(self) -> float:
        return self.time

    def advance(self, seconds: float) -> None:
        self.time += seconds


def test_canonical_cost_formula_overrides_stale_db_cost(mock_engine, sample_resource, sample_policy):
    """
    Stale database cost (e.g. ₹99,999 or ₹0) must NOT override canonical formula:
    (2 cores * 800) + (1 GB * 200) = ₹1800.
    """
    sample_resource.cpu_cores = 2
    sample_resource.memory = 1.0
    sample_resource.estimated_monthly_cost = 99999.0  # Deliberately stale DB cost

    dec = mock_engine.evaluate_resource(
        resource=sample_resource,
        policy=sample_policy,
        observed_cpu=50.0,
        observed_memory_percent=50.0,
        current_replicas=1,
    )
    assert dec["estimated_cost_before_inr"] == 1800.0
    assert dec["estimated_cost_after_inr"] == 1800.0
    assert dec["estimated_monthly_savings_inr"] == 0.0


def test_time_aware_sustained_window_normal_gap(sample_resource, sample_policy):
    """Samples arriving within max_sample_gap_seconds (e.g. 5s apart) successfully satisfy sustained window."""
    clock = MockClock(start=100.0)
    config = OptimizationEngineConfig(
        enabled=True,
        operating_mode=MODE_DRY_RUN,
        evaluation_interval_seconds=5.0,
        sustained_window_samples=3,
        scale_up_cpu_threshold=75.0,
    )
    engine = UnifiedOptimizationEngine(config=config, clock=clock)

    # Sample 1 at t=100.0
    dec1 = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=80.0, observed_memory_percent=50.0)
    assert "sample 1 of 3" in dec1["reason"]
    assert dec1["decision"] == DECISION_NO_ACTION

    # Sample 2 at t=105.0 (gap = 5.0s <= 12.5s)
    clock.advance(5.0)
    dec2 = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=80.0, observed_memory_percent=50.0)
    assert "sample 2 of 3" in dec2["reason"]
    assert dec2["decision"] == DECISION_NO_ACTION

    # Sample 3 at t=110.0 (gap = 5.0s <= 12.5s)
    clock.advance(5.0)
    dec3 = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=80.0, observed_memory_percent=50.0)
    assert dec3["decision"] in (DECISION_SCALE_OUT_HORIZONTAL, DECISION_SCALE_UP_VERTICAL)


def test_time_aware_sustained_window_gap_exceeded_resets_count(sample_resource, sample_policy):
    """If the time between samples exceeds max_sample_gap_seconds (e.g. 15s > 12.5s), sample window resets to 1."""
    clock = MockClock(start=100.0)
    config = OptimizationEngineConfig(
        enabled=True,
        operating_mode=MODE_DRY_RUN,
        evaluation_interval_seconds=5.0,
        sustained_window_samples=3,
        scale_up_cpu_threshold=75.0,
    )
    engine = UnifiedOptimizationEngine(config=config, clock=clock)

    # Sample 1 at t=100.0
    dec1 = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=80.0, observed_memory_percent=50.0)
    assert "sample 1 of 3" in dec1["reason"]

    # Sample 2 at t=105.0
    clock.advance(5.0)
    dec2 = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=80.0, observed_memory_percent=50.0)
    assert "sample 2 of 3" in dec2["reason"]

    # Large gap of 15 seconds (max gap is 2.5 * 5.0 = 12.5s)
    clock.advance(15.0)
    dec3 = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=80.0, observed_memory_percent=50.0)
    # Counter must be reset to 1 due to expired observation gap
    assert "sample 1 of 3" in dec3["reason"]
    assert dec3["decision"] == DECISION_NO_ACTION


def test_missing_metrics_resets_sustained_window(sample_resource, sample_policy):
    """Missing metrics must immediately reset the sample window back to zero."""
    clock = MockClock(start=100.0)
    config = OptimizationEngineConfig(
        enabled=True,
        operating_mode=MODE_DRY_RUN,
        evaluation_interval_seconds=5.0,
        sustained_window_samples=3,
    )
    engine = UnifiedOptimizationEngine(config=config, clock=clock)

    # Accumulate 2 high CPU samples
    engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=85.0, observed_memory_percent=50.0)
    clock.advance(5.0)
    engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=85.0, observed_memory_percent=50.0)

    # Missing metrics at sample 3
    clock.advance(5.0)
    dec_missing = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=None, observed_memory_percent=50.0)
    assert dec_missing["decision"] == DECISION_NO_ACTION
    assert "missing or unavailable" in dec_missing["reason"]

    # Next evaluation must start from sample 1
    clock.advance(5.0)
    dec_next = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=85.0, observed_memory_percent=50.0)
    assert "sample 1 of 3" in dec_next["reason"]


def test_neutral_metrics_resets_sustained_window(sample_resource, sample_policy):
    """Metrics in normal equilibrium range immediately reset accumulated samples."""
    clock = MockClock(start=100.0)
    config = OptimizationEngineConfig(
        enabled=True,
        operating_mode=MODE_DRY_RUN,
        evaluation_interval_seconds=5.0,
        sustained_window_samples=3,
    )
    engine = UnifiedOptimizationEngine(config=config, clock=clock)

    # 2 scale-up samples
    engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=85.0, observed_memory_percent=50.0)
    clock.advance(5.0)
    engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=85.0, observed_memory_percent=50.0)

    # Neutral observation
    clock.advance(5.0)
    dec_neutral = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=50.0, observed_memory_percent=50.0)
    assert dec_neutral["decision"] == DECISION_NO_ACTION
    assert "nominal equilibrium" in dec_neutral["reason"]

    # Subsequent spike must start at sample 1
    clock.advance(5.0)
    dec_spike = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=85.0, observed_memory_percent=50.0)
    assert "sample 1 of 3" in dec_spike["reason"]


def test_opposing_metrics_clears_opposite_window(sample_resource, sample_policy):
    """High utilization immediately resets scale-down tracking, and vice versa."""
    clock = MockClock(start=100.0)
    config = OptimizationEngineConfig(
        enabled=True,
        operating_mode=MODE_DRY_RUN,
        evaluation_interval_seconds=5.0,
        sustained_window_samples=3,
    )
    engine = UnifiedOptimizationEngine(config=config, clock=clock)

    # 2 scale-down samples
    engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=10.0, observed_memory_percent=20.0)
    clock.advance(5.0)
    engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=10.0, observed_memory_percent=20.0)

    # Immediate high load spike
    clock.advance(5.0)
    dec_spike = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=90.0, observed_memory_percent=80.0)
    assert "sample 1 of 3" in dec_spike["reason"]

    # Low load again must start from sample 1 (previous scale-down window was cleared by opposing spike)
    clock.advance(5.0)
    dec_low = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=10.0, observed_memory_percent=20.0)
    assert "sample 1 of 3" in dec_low["reason"]


def test_cooldown_unblocks_after_clock_advance(sample_resource, sample_policy):
    """Cooldown countdown is deterministic using injectable clock."""
    clock = MockClock(start=100.0)
    v_scaler = VerticalScalingService()
    v_scaler._mock_mode = True
    v_scaler._mock_containers["autoscaling-lab-app-1"] = {"cpu_cores": 2.0, "memory_gb": 1.0, "status": "running"}
    h_scaler = AutoscalingController()
    h_scaler._mock_mode = True
    h_scaler._mock_replicas = 1

    config = OptimizationEngineConfig(
        enabled=True,
        operating_mode=MODE_AUTO,
        evaluation_interval_seconds=5.0,
        sustained_window_samples=1,  # 1 sample triggers immediate action
        cooldown_seconds=60.0,
    )
    engine = UnifiedOptimizationEngine(config=config, vertical_scaler=v_scaler, autoscaler=h_scaler, clock=clock)

    sample_resource.is_simulated = False
    sample_resource.can_scale_horizontally = True
    sample_policy.max_replicas = 5

    # Action 1 executes at t=100.0
    dec1 = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=90.0, observed_memory_percent=80.0)
    assert dec1["executed"] is True
    assert engine.get_remaining_cooldown(sample_resource.id) == 60.0

    # Next evaluation at t=105.0: cooldown active!
    clock.advance(5.0)
    dec2 = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=90.0, observed_memory_percent=80.0)
    assert dec2["decision"] == DECISION_NO_ACTION
    assert "cooldown is active" in dec2["reason"]
    assert engine.get_remaining_cooldown(sample_resource.id) == 55.0

    # Advance clock past cooldown (advance by 56 seconds, total elapsed = 61s)
    clock.advance(56.0)
    assert engine.get_remaining_cooldown(sample_resource.id) == 0.0

    # Action is now permitted
    dec3 = engine.evaluate_resource(sample_resource, sample_policy, observed_cpu=90.0, observed_memory_percent=80.0)
    assert dec3["executed"] is True


def test_capability_based_horizontal_scaling_independent_of_name(sample_resource, sample_policy):
    """
    Renaming a workload (e.g. to 'payments-production-worker') does NOT break horizontal scaling
    if can_scale_horizontally=True and is_simulated=False.
    """
    sample_resource.id = "workload-production-99"
    sample_resource.name = "payments-production-worker"  # No 'autoscal' or 'app-1' in name
    sample_resource.is_simulated = False
    sample_resource.can_scale_horizontally = True
    sample_policy.min_replicas = 1
    sample_policy.max_replicas = 5

    v_scaler = VerticalScalingService()
    v_scaler._mock_mode = True
    h_scaler = AutoscalingController()
    h_scaler._mock_mode = True
    h_scaler._mock_replicas = 1

    config = OptimizationEngineConfig(
        enabled=True,
        operating_mode=MODE_DRY_RUN,
        sustained_window_samples=1,
    )
    engine = UnifiedOptimizationEngine(config=config, vertical_scaler=v_scaler, autoscaler=h_scaler)

    dec = engine.evaluate_resource(
        sample_resource,
        sample_policy,
        observed_cpu=90.0,
        observed_memory_percent=80.0,
        current_replicas=1,
    )
    assert dec["decision"] == DECISION_SCALE_OUT_HORIZONTAL
    assert dec["proposed_allocation"]["replicas"] == 2


def test_simulated_vm_never_scales_horizontally_regardless_of_name(sample_resource, sample_policy):
    """
    A simulated VM (is_simulated=True), even with 'autoscaling' in its name, must NEVER scale horizontally.
    It must follow the vertical scaling path.
    """
    sample_resource.id = "sim-vm-99"
    sample_resource.name = "autoscaling-fleet-worker-simulated"
    sample_resource.is_simulated = True
    sample_resource.can_scale_horizontally = False
    sample_policy.min_replicas = 1
    sample_policy.max_replicas = 5

    config = OptimizationEngineConfig(
        enabled=True,
        operating_mode=MODE_DRY_RUN,
        sustained_window_samples=1,
    )
    engine = UnifiedOptimizationEngine(config=config)

    dec = engine.evaluate_resource(
        sample_resource,
        sample_policy,
        observed_cpu=90.0,
        observed_memory_percent=80.0,
        current_replicas=1,
    )
    assert dec["decision"] == DECISION_SCALE_UP_VERTICAL
    assert dec["proposed_allocation"]["replicas"] == 1
    assert dec["proposed_allocation"]["cpu_cores"] == 4.0


def test_dry_run_and_recommendation_modes_never_mutate_docker(sample_resource, sample_policy):
    """
    In DRY_RUN and RECOMMENDATION modes, container limits must NEVER be mutated.
    """
    v_scaler = VerticalScalingService()
    v_scaler._mock_mode = True
    v_scaler._mock_containers["autoscaling-lab-app-1"] = {"cpu_cores": 2.0, "memory_gb": 1.0, "status": "running"}

    sample_resource.is_simulated = False
    sample_policy.max_replicas = 1  # Force vertical path

    # 1. DRY_RUN mode
    config_dry = OptimizationEngineConfig(enabled=True, operating_mode=MODE_DRY_RUN, sustained_window_samples=1)
    engine_dry = UnifiedOptimizationEngine(config=config_dry, vertical_scaler=v_scaler)
    dec_dry = engine_dry.evaluate_resource(sample_resource, sample_policy, observed_cpu=90.0, observed_memory_percent=85.0)
    assert dec_dry["executed"] is False
    assert v_scaler._mock_containers["autoscaling-lab-app-1"]["cpu_cores"] == 2.0

    # 2. RECOMMENDATION mode
    config_rec = OptimizationEngineConfig(enabled=True, operating_mode=MODE_RECOMMENDATION, sustained_window_samples=1)
    engine_rec = UnifiedOptimizationEngine(config=config_rec, vertical_scaler=v_scaler)
    dec_rec = engine_rec.evaluate_resource(sample_resource, sample_policy, observed_cpu=90.0, observed_memory_percent=85.0)
    assert dec_rec["decision"] == DECISION_RECOMMENDATION_ONLY
    assert dec_rec["executed"] is False
    assert v_scaler._mock_containers["autoscaling-lab-app-1"]["cpu_cores"] == 2.0


def test_api_optimizer_status_and_config():
    """Verify GET /api/optimizer/status and PUT /api/optimizer/config via FastAPI TestClient."""
    from fastapi.testclient import TestClient
    from main import app, unified_optimizer_engine
    client = TestClient(app)

    # Status check
    res = client.get("/api/optimizer/status", headers={"X-Demo-User": "admin@cloudflow.com"})
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "operating_mode" in data
    assert "max_sample_gap_seconds" in data
    assert data["max_sample_gap_seconds"] > 0
    assert "scheduler_running" in data

    # Update config with custom max_sample_gap_seconds
    update_res = client.put(
        "/api/optimizer/config",
        json={"max_sample_gap_seconds": 20.0, "operating_mode": "DRY_RUN"},
        headers={"X-Demo-User": "admin@cloudflow.com"},
    )
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["max_sample_gap_seconds"] == 20.0
    assert updated_data["operating_mode"] == "DRY_RUN"


def test_api_optimizer_evaluate_canonical_pricing():
    """Verify POST /api/optimizer/evaluate returns canonical ₹1800 calculation for docker demo."""
    from fastapi.testclient import TestClient
    from main import app
    client = TestClient(app)

    res = client.post(
        "/api/optimizer/evaluate",
        json={"resource_id": "demo-docker-app-01", "mode_override": "DRY_RUN"},
        headers={"X-Demo-User": "admin@cloudflow.com"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["resource_id"] == "demo-docker-app-01"
    assert data["estimated_cost_before_inr"] == 1800.0
    assert data["operating_mode"] == "DRY_RUN"
    assert data["executed"] is False


