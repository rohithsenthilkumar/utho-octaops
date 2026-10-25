"""
SmartCloud Optimizer — Stage 7 Unified Optimization Engine
==========================================================
Observes workload metrics, evaluates policies, decides whether optimization
is justified, and safely coordinates vertical scaling, horizontal scaling, or no action.

Supported Decisions:
- NO_ACTION
- SCALE_UP_VERTICAL
- SCALE_DOWN_VERTICAL
- SCALE_OUT_HORIZONTAL
- SCALE_IN_HORIZONTAL
- RECOMMENDATION_ONLY
- APPROVAL_REQUIRED
- BLOCKED_BY_POLICY

Supported Operating Modes:
- DRY_RUN (Default: evaluates metrics and makes decisions without modifying resources)
- RECOMMENDATION (Persists recommendations for authorized user review)
- AUTO (Executes only eligible actions passing authorization, policy, approval, and safety checks)
"""
import time
import uuid
import logging
import threading
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

from models import CloudResource, ResourcePolicy, ResourceChangeRequest, AuditEvent, User
from engines.vertical_scaler import VerticalScalingService, estimate_compute_monthly_cost
from engines.autoscaler import AutoscalingController

logger = logging.getLogger("smartcloud.unified_optimizer")

# Supported Decisions
DECISION_NO_ACTION = "NO_ACTION"
DECISION_SCALE_UP_VERTICAL = "SCALE_UP_VERTICAL"
DECISION_SCALE_DOWN_VERTICAL = "SCALE_DOWN_VERTICAL"
DECISION_SCALE_OUT_HORIZONTAL = "SCALE_OUT_HORIZONTAL"
DECISION_SCALE_IN_HORIZONTAL = "SCALE_IN_HORIZONTAL"
DECISION_RECOMMENDATION_ONLY = "RECOMMENDATION_ONLY"
DECISION_APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
DECISION_BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"

# Operating Modes
MODE_DRY_RUN = "DRY_RUN"
MODE_RECOMMENDATION = "RECOMMENDATION"
MODE_AUTO = "AUTO"


@dataclass
class OptimizationEngineConfig:
    enabled: bool = False
    operating_mode: str = MODE_DRY_RUN
    evaluation_interval_seconds: float = 5.0
    scale_up_cpu_threshold: float = 75.0
    scale_down_cpu_threshold: float = 25.0
    scale_up_memory_threshold: float = 80.0
    scale_down_memory_threshold: float = 40.0
    sustained_window_samples: int = 3
    cooldown_seconds: float = 60.0
    max_sample_gap_seconds: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d.get("max_sample_gap_seconds") is None:
            d["max_sample_gap_seconds"] = round(2.5 * self.evaluation_interval_seconds, 2)
        return d


class UnifiedOptimizationEngine:
    """
    Central authoritative optimization coordinator.
    Evaluates observed metrics against policy, prevents conflicting scaling decisions,
    manages operating modes (DRY_RUN, RECOMMENDATION, AUTO), and coordinates vertical
    and horizontal execution.
    """

    def __init__(
        self,
        config: Optional[OptimizationEngineConfig] = None,
        vertical_scaler: Optional[VerticalScalingService] = None,
        autoscaler: Optional[AutoscalingController] = None,
        clock: Optional[Any] = None,
    ):
        self.config = config or OptimizationEngineConfig()
        self.vertical_scaler = vertical_scaler or VerticalScalingService()
        self.autoscaler = autoscaler or AutoscalingController()
        self.clock = clock or time.monotonic

        # Monotonic timestamp sample tracking: resource_id -> list of monotonic timestamps
        self._scale_up_samples: Dict[str, List[float]] = {}
        self._scale_down_samples: Dict[str, List[float]] = {}
        self.last_action_timestamp: Dict[str, float] = {}
        self.last_action_type: Dict[str, str] = {}

        # History and status
        self.recent_decisions: List[Dict[str, Any]] = []
        self.recent_errors: List[Dict[str, Any]] = []
        self.last_run_timestamp: Optional[str] = None
        self.last_evaluation_timestamp: Optional[str] = None
        self.next_run_timestamp: Optional[str] = None
        self._is_evaluating = False
        self._is_scaling = False
        self._scaling_lock = threading.Lock()
        self.scheduler_running: bool = False
        self.scheduler_state: str = "INITIALIZING"

    @property
    def max_sample_gap_seconds(self) -> float:
        if self.config.max_sample_gap_seconds is not None:
            return float(self.config.max_sample_gap_seconds)
        return round(2.5 * self.config.evaluation_interval_seconds, 2)

    @property
    def consecutive_scale_up_samples(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self._scale_up_samples.items()}

    @property
    def consecutive_scale_down_samples(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self._scale_down_samples.items()}

    def reset_samples(self, resource_id: Optional[str] = None) -> None:
        """Reset sample windows for a given resource or all resources."""
        if resource_id:
            self._scale_up_samples.pop(resource_id, None)
            self._scale_down_samples.pop(resource_id, None)
        else:
            self._scale_up_samples.clear()
            self._scale_down_samples.clear()

    def get_remaining_cooldown(self, resource_id: str) -> float:
        """Calculate remaining cooldown time for a resource in seconds using the engine clock."""
        last_time = self.last_action_timestamp.get(resource_id)
        if not last_time:
            return 0.0
        elapsed = self.clock() - last_time
        return max(0.0, round(self.config.cooldown_seconds - elapsed, 1))

    def evaluate_resource(
        self,
        resource: CloudResource,
        policy: Optional[ResourcePolicy],
        observed_cpu: Optional[float],
        observed_memory_percent: Optional[float],
        current_replicas: int = 1,
        mode_override: Optional[str] = None,
        db_session: Optional[Any] = None,
        actor: Optional[User] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate a single resource against policies, metrics, and thresholds.
        Returns a rich decision record with cost impact, approval status, and execution results.
        """
        now = datetime.now(timezone.utc)
        now_mono = self.clock()
        correlation_id = f"opt-{uuid.uuid4().hex[:12]}"
        mode = mode_override or self.config.operating_mode
        res_id = resource.id

        # Current allocations
        curr_cpu = float(resource.cpu_cores)
        curr_mem_gb = float(resource.memory)

        # Canonical pricing formula: (CPU * 800) + (RAM * 200), multiplied by current replicas
        # Stored resource cost never overrides canonical calculation
        effective_replicas = max(1, current_replicas)
        curr_cost = round(
            estimate_compute_monthly_cost(curr_cpu, curr_mem_gb) * effective_replicas, 2
        )

        # Default policy boundaries
        min_cpu = float(policy.min_cpu_cores) if policy else 1.0
        max_cpu = float(policy.max_cpu_cores) if policy else 16.0
        min_mem_gb = float(policy.min_memory_gb) if policy else 0.5
        max_mem_gb = float(policy.max_memory_gb) if policy else 64.0
        min_replicas = int(policy.min_replicas) if policy and hasattr(policy, "min_replicas") else 1
        max_replicas = int(policy.max_replicas) if policy and hasattr(policy, "max_replicas") else 5
        allow_manual = policy.allow_manual_scaling if policy else True
        allow_auto = policy.allow_auto_scaling if policy and hasattr(policy, "allow_auto_scaling") else True
        requires_approval = policy.requires_approval if policy else False

        # Base Decision Payload
        decision_record: Dict[str, Any] = {
            "correlation_id": correlation_id,
            "timestamp": now.isoformat(),
            "resource_id": res_id,
            "resource_name": resource.name,
            "tenant_id": resource.tenant_id,
            "operating_mode": mode,
            "observed_metrics": {
                "cpu_utilization_percent": observed_cpu,
                "memory_utilization_percent": observed_memory_percent,
            },
            "current_allocation": {
                "cpu_cores": curr_cpu,
                "memory_gb": curr_mem_gb,
                "replicas": current_replicas,
            },
            "proposed_allocation": {
                "cpu_cores": curr_cpu,
                "memory_gb": curr_mem_gb,
                "replicas": current_replicas,
            },
            "decision": DECISION_NO_ACTION,
            "reason": "",
            "estimated_cost_before_inr": curr_cost,
            "estimated_cost_after_inr": curr_cost,
            "estimated_monthly_savings_inr": 0.0,
            "requires_approval": requires_approval,
            "executed": False,
            "verified": False,
            "execution_error": None,
        }

        # Rule 1: Handle Missing or Unhealthy Metrics Safely (Never assume zero)
        if observed_cpu is None or observed_memory_percent is None:
            decision_record["decision"] = DECISION_NO_ACTION
            decision_record["reason"] = (
                "Workload metrics are missing or unavailable. Safety protocol engaged: "
                "missing metrics are never assumed to be 0% utilization. No scaling action taken."
            )
            self.reset_samples(res_id)
            self._record_decision(decision_record)
            return decision_record

        # Rule 2: Check Policy Scaling Permissions
        if mode == MODE_AUTO and not allow_auto:
            decision_record["decision"] = DECISION_BLOCKED_BY_POLICY
            decision_record["reason"] = "Automated scaling is disabled by company resource policy for this resource."
            self._record_decision(decision_record)
            return decision_record

        # Rule 3: Deterministic Decision Priority - Check for Scale Up / Out Needs
        needs_scale_up = (
            observed_cpu >= self.config.scale_up_cpu_threshold
            or observed_memory_percent >= self.config.scale_up_memory_threshold
        )
        needs_scale_down = (
            observed_cpu <= self.config.scale_down_cpu_threshold
            and observed_memory_percent <= self.config.scale_down_memory_threshold
        )

        remaining_cooldown = self.get_remaining_cooldown(res_id)

        # SCALE UP / OUT PATH
        if needs_scale_up:
            # Reset opposing scale-down tracking
            self._scale_down_samples.pop(res_id, None)

            # Time-aware monotonic sample tracking
            existing_up = self._scale_up_samples.get(res_id, [])
            if existing_up:
                gap = now_mono - existing_up[-1]
                if gap > self.max_sample_gap_seconds:
                    # Gap between observations exceeded maximum allowed interval: discard and reset
                    self._scale_up_samples[res_id] = [now_mono]
                else:
                    self._scale_up_samples[res_id].append(now_mono)
            else:
                self._scale_up_samples[res_id] = [now_mono]

            up_samples_count = len(self._scale_up_samples[res_id])

            # Sustained window check
            if up_samples_count < self.config.sustained_window_samples:
                decision_record["decision"] = DECISION_NO_ACTION
                decision_record["reason"] = (
                    f"Scale-up threshold met (CPU {observed_cpu:.1f}%, RAM {observed_memory_percent:.1f}%), "
                    f"evaluating sustained window: sample {up_samples_count} "
                    f"of {self.config.sustained_window_samples} required consecutive samples."
                )
                self._record_decision(decision_record)
                return decision_record

            # Cooldown check
            if remaining_cooldown > 0:
                decision_record["decision"] = DECISION_NO_ACTION
                decision_record["reason"] = (
                    f"High utilization sustained, but cooldown is active ({remaining_cooldown:.1f}s remaining). "
                    "Action postponed to prevent rapid oscillation."
                )
                self._record_decision(decision_record)
                return decision_record

            # Capability-based Horizontal vs Vertical check:
            # Never scale simulated resources horizontally. Only live workloads configured with horizontal capability.
            is_horizontal_workload = (
                not getattr(resource, "is_simulated", True)
                and (
                    getattr(resource, "can_scale_horizontally", False)
                    or (policy and getattr(policy, "can_scale_horizontally", False))
                    or (policy and getattr(policy, "max_replicas", 1) > 1)
                )
            )

            if is_horizontal_workload and current_replicas < max_replicas:
                # Propose Horizontal Scale-Out
                new_replicas = min(max_replicas, current_replicas + 1)
                decision_record["decision"] = DECISION_SCALE_OUT_HORIZONTAL
                decision_record["proposed_allocation"]["replicas"] = new_replicas
                after_cost = round(estimate_compute_monthly_cost(curr_cpu, curr_mem_gb) * new_replicas, 2)
                decision_record["estimated_cost_after_inr"] = after_cost
                decision_record["estimated_monthly_savings_inr"] = round(curr_cost - after_cost, 2)
                decision_record["reason"] = (
                    f"Sustained high load (CPU {observed_cpu:.1f}%, RAM {observed_memory_percent:.1f}%). "
                    f"Proposing horizontal scale-out from {current_replicas} to {new_replicas} replicas."
                )
            else:
                # Vertical Scale-Up
                proposed_cpu = min(max_cpu, curr_cpu * 2 if curr_cpu < max_cpu else max_cpu)
                proposed_mem = min(max_mem_gb, curr_mem_gb * 2 if curr_mem_gb < max_mem_gb else max_mem_gb)

                if proposed_cpu == curr_cpu and proposed_mem == curr_mem_gb:
                    decision_record["decision"] = DECISION_BLOCKED_BY_POLICY
                    decision_record["reason"] = (
                        f"High utilization detected, but resource is already at maximum policy limit "
                        f"({max_cpu} vCPU, {max_mem_gb} GB RAM)."
                    )
                    self._record_decision(decision_record)
                    return decision_record

                decision_record["decision"] = DECISION_SCALE_UP_VERTICAL
                decision_record["proposed_allocation"]["cpu_cores"] = proposed_cpu
                decision_record["proposed_allocation"]["memory_gb"] = proposed_mem
                after_cost = round(estimate_compute_monthly_cost(proposed_cpu, proposed_mem) * current_replicas, 2)
                decision_record["estimated_cost_after_inr"] = after_cost
                decision_record["estimated_monthly_savings_inr"] = round(curr_cost - after_cost, 2)
                decision_record["reason"] = (
                    f"Sustained resource pressure (CPU {observed_cpu:.1f}%, RAM {observed_memory_percent:.1f}%). "
                    f"Proposing vertical scale-up to {proposed_cpu} vCPU, {proposed_mem} GB RAM."
                )

        # SCALE DOWN / IN PATH
        elif needs_scale_down:
            # Reset opposing scale-up tracking
            self._scale_up_samples.pop(res_id, None)

            # Time-aware monotonic sample tracking
            existing_down = self._scale_down_samples.get(res_id, [])
            if existing_down:
                gap = now_mono - existing_down[-1]
                if gap > self.max_sample_gap_seconds:
                    # Gap between observations exceeded maximum allowed interval: discard and reset
                    self._scale_down_samples[res_id] = [now_mono]
                else:
                    self._scale_down_samples[res_id].append(now_mono)
            else:
                self._scale_down_samples[res_id] = [now_mono]

            down_samples_count = len(self._scale_down_samples[res_id])

            # Sustained window check
            if down_samples_count < self.config.sustained_window_samples:
                decision_record["decision"] = DECISION_NO_ACTION
                decision_record["reason"] = (
                    f"Low utilization detected (CPU {observed_cpu:.1f}%, RAM {observed_memory_percent:.1f}%), "
                    f"evaluating sustained window: sample {down_samples_count} "
                    f"of {self.config.sustained_window_samples} required consecutive samples."
                )
                self._record_decision(decision_record)
                return decision_record

            # Cooldown check
            if remaining_cooldown > 0:
                decision_record["decision"] = DECISION_NO_ACTION
                decision_record["reason"] = (
                    f"Scale-down condition met, but cooldown is active ({remaining_cooldown:.1f}s remaining). "
                    "Action postponed to prevent oscillation."
                )
                self._record_decision(decision_record)
                return decision_record

            # Capability-based Horizontal Scale-In vs Vertical Scale-Down
            is_horizontal_workload = (
                not getattr(resource, "is_simulated", True)
                and (
                    getattr(resource, "can_scale_horizontally", False)
                    or (policy and getattr(policy, "can_scale_horizontally", False))
                    or (policy and getattr(policy, "max_replicas", 1) > 1)
                )
            )

            if is_horizontal_workload and current_replicas > min_replicas:
                new_replicas = max(min_replicas, current_replicas - 1)
                decision_record["decision"] = DECISION_SCALE_IN_HORIZONTAL
                decision_record["proposed_allocation"]["replicas"] = new_replicas
                after_cost = round(estimate_compute_monthly_cost(curr_cpu, curr_mem_gb) * new_replicas, 2)
                decision_record["estimated_cost_after_inr"] = after_cost
                decision_record["estimated_monthly_savings_inr"] = round(curr_cost - after_cost, 2)
                decision_record["reason"] = (
                    f"Sustained low utilization (CPU {observed_cpu:.1f}%, RAM {observed_memory_percent:.1f}%). "
                    f"Proposing horizontal scale-in from {current_replicas} to {new_replicas} replicas."
                )
            else:
                # Vertical Scale-Down
                proposed_cpu = max(min_cpu, curr_cpu / 2 if curr_cpu > min_cpu else min_cpu)
                proposed_mem = max(min_mem_gb, curr_mem_gb / 2 if curr_mem_gb > min_mem_gb else min_mem_gb)

                if proposed_cpu == curr_cpu and proposed_mem == curr_mem_gb:
                    decision_record["decision"] = DECISION_NO_ACTION
                    decision_record["reason"] = (
                        f"Workload is under-utilized, but resource is already at minimum policy bounds "
                        f"({min_cpu} vCPU, {min_mem_gb} GB RAM). No further downsizing safe."
                    )
                    self._record_decision(decision_record)
                    return decision_record

                decision_record["decision"] = DECISION_SCALE_DOWN_VERTICAL
                decision_record["proposed_allocation"]["cpu_cores"] = proposed_cpu
                decision_record["proposed_allocation"]["memory_gb"] = proposed_mem
                after_cost = round(estimate_compute_monthly_cost(proposed_cpu, proposed_mem) * current_replicas, 2)
                decision_record["estimated_cost_after_inr"] = after_cost
                decision_record["estimated_monthly_savings_inr"] = round(curr_cost - after_cost, 2)
                decision_record["reason"] = (
                    f"Sustained low workload demand (CPU {observed_cpu:.1f}%, RAM {observed_memory_percent:.1f}%). "
                    f"Proposing vertical downsizing to {proposed_cpu} vCPU, {proposed_mem} GB RAM."
                )
        else:
            # In normal healthy range (neutral observation: reset both sample windows)
            self.reset_samples(res_id)
            decision_record["decision"] = DECISION_NO_ACTION
            decision_record["reason"] = (
                f"Workload metrics are in nominal equilibrium: CPU {observed_cpu:.1f}% "
                f"[{self.config.scale_down_cpu_threshold}% - {self.config.scale_up_cpu_threshold}%] and "
                f"RAM {observed_memory_percent:.1f}% "
                f"[{self.config.scale_down_memory_threshold}% - {self.config.scale_up_memory_threshold}%]."
            )
            self._record_decision(decision_record)
            return decision_record

        # Rule 4: Apply Operating Mode Behavior (DRY_RUN, RECOMMENDATION, AUTO)
        if mode == MODE_DRY_RUN:
            decision_record["reason"] += " [DRY_RUN mode active: evaluation only, no infrastructure modified]."
            self._record_decision(decision_record)
            return decision_record

        if mode == MODE_RECOMMENDATION:
            decision_record["reason"] += " [RECOMMENDATION mode active: proposal recorded for review]."
            decision_record["decision"] = DECISION_RECOMMENDATION_ONLY
            self._record_decision(decision_record)
            return decision_record

        # AUTO MODE: Check Approval Gate
        if requires_approval and (not actor or actor.role != "COMPANY_ADMIN"):
            decision_record["decision"] = DECISION_APPROVAL_REQUIRED
            decision_record["reason"] += (
                " Policy requires Company Administrator approval before automated scaling can execute."
            )
            # Create a change request in DB if session is available
            if db_session:
                self._create_change_request(
                    db_session=db_session,
                    resource=resource,
                    decision_record=decision_record,
                    actor=actor,
                )
            self._record_decision(decision_record)
            return decision_record

        # AUTO MODE: Execute Authorized Action
        self._execute_decision(
            decision_record=decision_record,
            resource=resource,
            db_session=db_session,
            actor=actor,
        )

        self._record_decision(decision_record)
        return decision_record

    def _execute_decision(
        self,
        decision_record: Dict[str, Any],
        resource: CloudResource,
        db_session: Optional[Any],
        actor: Optional[User],
    ) -> None:
        """Execute scaling action with post-action verification, concurrency locking, and audit logging."""
        if self._is_scaling:
            decision_record["executed"] = False
            decision_record["verified"] = False
            decision_record["reason"] += " (Execution deferred: An overlapping scaling operation is actively running on this workload)."
            return

        with self._scaling_lock:
            self._is_scaling = True
            try:
                decision = decision_record["decision"]
                target = decision_record["proposed_allocation"]

                if decision in (DECISION_SCALE_UP_VERTICAL, DECISION_SCALE_DOWN_VERTICAL):
                    container_name = "autoscaling-lab-app-1"
                    req_cpu = target["cpu_cores"]
                    req_mem = target["memory_gb"]

                    ok, inspected, msg = self.vertical_scaler.update_container_limits(
                        container_name=container_name,
                        requested_cpu=req_cpu,
                        requested_memory_gb=req_mem,
                    )

                    if ok and inspected.get("effective_limits_verified"):
                        decision_record["executed"] = True
                        decision_record["verified"] = True
                        decision_record["reason"] += f" Successfully verified container limits ({req_cpu} vCPU, {req_mem} GB RAM)."
                        self.last_action_timestamp[resource.id] = self.clock()
                        self.last_action_type[resource.id] = decision
                        self.reset_samples(resource.id)

                        # Update database resource model
                        if db_session:
                            resource.cpu_cores = int(req_cpu)
                            resource.memory = float(req_mem)
                            resource.estimated_monthly_cost = decision_record["estimated_cost_after_inr"]
                            self._record_audit_event(
                                db_session=db_session,
                                resource=resource,
                                action=decision,
                                outcome="SUCCESS",
                                actor_email=actor.email if actor else "optimizer-service@smartcloud",
                                reason=decision_record["reason"],
                            )
                    else:
                        decision_record["executed"] = False
                        decision_record["verified"] = False
                        decision_record["execution_error"] = msg
                        decision_record["reason"] += f" Execution failed: {msg}"
                        self._record_error("VERTICAL_SCALE_FAILED", msg, decision_record)

                elif decision in (DECISION_SCALE_OUT_HORIZONTAL, DECISION_SCALE_IN_HORIZONTAL):
                    target_reps = target["replicas"]
                    ok = self.autoscaler.execute_docker_scale(target_reps)

                    if ok:
                        decision_record["executed"] = True
                        decision_record["verified"] = True
                        decision_record["reason"] += f" Successfully verified replica count to {target_reps}."
                        self.last_action_timestamp[resource.id] = self.clock()
                        self.last_action_type[resource.id] = decision
                        self.reset_samples(resource.id)

                        if db_session:
                            resource.estimated_monthly_cost = decision_record["estimated_cost_after_inr"]
                            self._record_audit_event(
                                db_session=db_session,
                                resource=resource,
                                action=decision,
                                outcome="SUCCESS",
                                actor_email=actor.email if actor else "optimizer-service@smartcloud",
                                reason=decision_record["reason"],
                            )
                    else:
                        decision_record["executed"] = False
                        decision_record["verified"] = False
                        err_msg = f"Failed to execute or verify docker scale to {target_reps} replicas."
                        decision_record["execution_error"] = err_msg
                        decision_record["reason"] += f" Execution error: {err_msg}"
                        self._record_error("HORIZONTAL_SCALE_FAILED", err_msg, decision_record)
            finally:
                self._is_scaling = False

    def _create_change_request(
        self,
        db_session: Any,
        resource: CloudResource,
        decision_record: Dict[str, Any],
        actor: Optional[User],
    ) -> None:
        """Create change request in SQLite when policy approval is required."""
        try:
            target = decision_record["proposed_allocation"]
            cr = ResourceChangeRequest(
                id=f"cr-opt-{uuid.uuid4().hex[:8]}",
                tenant_id=resource.tenant_id,
                resource_id=resource.id,
                requester_id=actor.id if actor else "optimizer-service",
                current_cpu=float(resource.cpu_cores),
                requested_cpu=float(target["cpu_cores"]),
                current_memory_gb=float(resource.memory),
                requested_memory_gb=float(target["memory_gb"]),
                estimated_cost_before=decision_record["estimated_cost_before_inr"],
                estimated_cost_after=decision_record["estimated_cost_after_inr"],
                monthly_cost_diff=round(
                    decision_record["estimated_cost_after_inr"] - decision_record["estimated_cost_before_inr"], 2
                ),
                status="PENDING",
                reason=f"Unified Optimizer recommendation: {decision_record['reason']}",
            )
            db_session.add(cr)
            db_session.commit()
            decision_record["change_request_id"] = cr.id
        except Exception as e:
            logger.error(f"Failed to record change request: {e}")

    def _record_audit_event(
        self,
        db_session: Any,
        resource: CloudResource,
        action: str,
        outcome: str,
        actor_email: str,
        reason: str,
    ) -> None:
        """Record immutable audit event."""
        try:
            import json
            audit = AuditEvent(
                id=f"audit-opt-{uuid.uuid4().hex[:8]}",
                actor_id=actor_email,
                actor_role="OPTIMIZER_SERVICE",
                tenant_id=resource.tenant_id,
                resource_id=resource.id,
                action=f"OPTIMIZER_{action}",
                outcome=outcome,
                reason=reason,
            )
            db_session.add(audit)
            db_session.commit()
        except Exception as e:
            logger.error(f"Failed to record audit event: {e}")

    def _record_decision(self, record: Dict[str, Any]) -> None:
        """Store decision in recent history (bounded)."""
        self.recent_decisions.insert(0, record)
        if len(self.recent_decisions) > 100:
            self.recent_decisions.pop()

    def _record_error(self, code: str, message: str, details: Any) -> None:
        """Store error in recent error queue."""
        self.recent_errors.insert(0, {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "code": code,
            "message": message,
            "details": details,
        })
        if len(self.recent_errors) > 50:
            self.recent_errors.pop()

    def get_status(self) -> Dict[str, Any]:
        """Return engine operational status, configuration, and health."""
        return {
            "status": "healthy" if len(self.recent_errors) == 0 else "degraded",
            "enabled": self.config.enabled,
            "scheduler_running": self.scheduler_running,
            "scheduler_state": self.scheduler_state,
            "operating_mode": self.config.operating_mode,
            "evaluation_interval_seconds": self.config.evaluation_interval_seconds,
            "max_sample_gap_seconds": self.max_sample_gap_seconds,
            "config": self.config.to_dict(),
            "last_run_timestamp": self.last_run_timestamp,
            "last_evaluation_timestamp": self.last_evaluation_timestamp,
            "next_run_timestamp": self.next_run_timestamp,
            "recent_decisions_count": len(self.recent_decisions),
            "recent_errors_count": len(self.recent_errors),
            "recent_decisions": self.recent_decisions[:10],
            "recent_errors": self.recent_errors[:5],
        }
