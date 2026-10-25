"""
SmartCloud Optimizer — Stage 9A: Dedicated KVM VM Optimizer Engine
==================================================================
Provides autonomous and recommendation-driven capacity optimization for real
libvirt virtual machines.

Key Invariants:
1. Complete Independence: Enabling VM AUTO never enables Container AUTO, and vice-versa.
2. VM AUTO is disabled by default.
3. DRY_RUN mode calculates recommendations without hypervisor mutation.
4. If guest telemetry is absent, never guesses utilization.
5. Respects policy bounds, cooldowns, and host headroom.
"""
import uuid
import time
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from dataclasses import dataclass, asdict

from engines.kvm_adapter import KvmLibvirtAdapter, estimate_vm_monthly_cost
from models import CloudResource, ResourcePolicy, AuditEvent, ResourceChangeRequest

MODE_DRY_RUN = "DRY_RUN"
MODE_RECOMMENDATION = "RECOMMENDATION"
MODE_AUTO = "AUTO"

DECISION_NO_ACTION = "NO_ACTION"
DECISION_VM_SCALE_UP = "VM_SCALE_UP"
DECISION_VM_SCALE_DOWN = "VM_SCALE_DOWN"
DECISION_BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
DECISION_INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
DECISION_REQUIRES_SHUTDOWN = "REQUIRES_SHUTDOWN"


@dataclass
class VmOptimizerConfig:
    enabled: bool = False
    operating_mode: str = MODE_DRY_RUN
    evaluation_interval_seconds: float = 10.0
    scale_up_cpu_threshold: float = 80.0
    scale_down_cpu_threshold: float = 20.0
    scale_up_memory_threshold: float = 85.0
    scale_down_memory_threshold: float = 35.0
    sustained_window_samples: int = 2
    cooldown_seconds: float = 60.0
    max_sample_gap_seconds: float = 25.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class KvmVmOptimizerEngine:
    def __init__(self, adapter: Optional[KvmLibvirtAdapter] = None):
        self.adapter = adapter or KvmLibvirtAdapter()
        self.config = VmOptimizerConfig()
        self._vm_lock = threading.Lock()
        self._is_evaluating = False
        self._scale_up_samples: Dict[str, List[float]] = {}
        self._scale_down_samples: Dict[str, List[float]] = {}
        self._last_action_timestamp: Dict[str, float] = {}
        self._decisions: List[Dict[str, Any]] = []
        self._errors: List[Dict[str, Any]] = []

    def get_status(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "enabled": self.config.enabled,
            "operating_mode": self.config.operating_mode,
            "config": self.config.to_dict(),
            "scheduler_state": "ACTIVE" if self.config.enabled else "IDLE_DISABLED",
            "recent_decisions_count": len(self._decisions),
            "recent_decisions": self._decisions[:10],
            "recent_errors": self._errors[:10],
        }

    def update_config(self, updates: Dict[str, Any]) -> VmOptimizerConfig:
        with self._vm_lock:
            for k, v in updates.items():
                if hasattr(self.config, k) and v is not None:
                    setattr(self.config, k, v)
            return self.config

    def evaluate_vm(
        self,
        domain_name: str,
        resource: Optional[CloudResource] = None,
        policy: Optional[ResourcePolicy] = None,
        observed_guest_cpu: Optional[float] = None,
        observed_guest_ram_percent: Optional[float] = None,
        mode_override: Optional[str] = None,
        db_session: Optional[Any] = None,
        actor: Optional[Any] = None,
        allow_shutdown: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate a KVM domain against policies, guest metrics, and thresholds.
        """
        now = datetime.now(timezone.utc)
        now_mono = time.monotonic()
        correlation_id = f"opt-vm-{uuid.uuid4().hex[:10]}"
        mode = mode_override or self.config.operating_mode

        # 1. Inspect live domain
        domain_info = self.adapter.inspect_domain(domain_name)
        if not domain_info:
            record = {
                "correlation_id": correlation_id,
                "timestamp": now.isoformat(),
                "domain_name": domain_name,
                "operating_mode": mode,
                "decision": DECISION_NO_ACTION,
                "reason": f"Domain '{domain_name}' is not found or inaccessible via hypervisor.",
                "executed": False,
                "verified": False,
            }
            self._record_decision(record)
            return record

        curr_cpu = float(domain_info["current_cpu_cores"])
        curr_mem = float(domain_info["current_memory_gb"])
        curr_cost = estimate_vm_monthly_cost(curr_cpu, curr_mem)

        # 2. Extract policy bounds
        min_cpu = float(policy.min_cpu_cores) if policy else 1.0
        max_cpu = float(policy.max_cpu_cores) if policy else float(domain_info["max_cpu_cores"])
        min_mem = float(policy.min_memory_gb) if policy else 0.5
        max_mem = float(policy.max_memory_gb) if policy else float(domain_info["max_memory_gb"])
        requires_approval = policy.requires_approval if policy else False

        record: Dict[str, Any] = {
            "correlation_id": correlation_id,
            "timestamp": now.isoformat(),
            "domain_name": domain_name,
            "uuid": domain_info["uuid"],
            "state": domain_info["state"],
            "operating_mode": mode,
            "current_allocation": {"cpu_cores": curr_cpu, "memory_gb": curr_mem},
            "proposed_allocation": {"cpu_cores": curr_cpu, "memory_gb": curr_mem},
            "observed_metrics": {
                "guest_cpu_percent": observed_guest_cpu,
                "guest_ram_percent": observed_guest_ram_percent,
            },
            "decision": DECISION_NO_ACTION,
            "reason": "",
            "estimated_cost_before_inr": curr_cost,
            "estimated_cost_after_inr": curr_cost,
            "estimated_monthly_savings_inr": 0.0,
            "requires_approval": requires_approval,
            "requires_shutdown": False,
            "executed": False,
            "verified": False,
        }

        # Rule 1: Trustworthy metrics requirement
        if observed_guest_cpu is None or observed_guest_ram_percent is None:
            record["decision"] = DECISION_INSUFFICIENT_DATA
            record["reason"] = (
                "Guest VM utilization metrics (qemu-guest-agent) are unavailable. "
                "Safety rule: SmartCloud Optimizer never treats physical host CPU as guest VM CPU. "
                "No capacity scaling action will be proposed without verified guest telemetry."
            )
            self._record_decision(record)
            return record

        # Rule 2: Cooldown check
        last_action = self._last_action_timestamp.get(domain_name, 0.0)
        cooldown_remaining = max(0.0, self.config.cooldown_seconds - (now_mono - last_action))

        needs_scale_up = (
            observed_guest_cpu >= self.config.scale_up_cpu_threshold
            or observed_guest_ram_percent >= self.config.scale_up_memory_threshold
        )
        needs_scale_down = (
            observed_guest_cpu <= self.config.scale_down_cpu_threshold
            and observed_guest_ram_percent <= self.config.scale_down_memory_threshold
        )

        if needs_scale_up:
            self._scale_down_samples.pop(domain_name, None)
            samples = self._scale_up_samples.setdefault(domain_name, [])
            samples.append(now_mono)

            if len(samples) < self.config.sustained_window_samples:
                record["decision"] = DECISION_NO_ACTION
                record["reason"] = (
                    f"VM CPU pressure detected ({observed_guest_cpu:.1f}%), evaluating sustained window: "
                    f"sample {len(samples)} of {self.config.sustained_window_samples} required."
                )
                self._record_decision(record)
                return record

            if cooldown_remaining > 0:
                record["decision"] = DECISION_NO_ACTION
                record["reason"] = f"Scale-up indicated, but cooldown active ({cooldown_remaining:.1f}s remaining)."
                self._record_decision(record)
                return record

            # Propose Scale Up
            target_cpu = min(max_cpu, curr_cpu * 2 if curr_cpu < max_cpu else max_cpu)
            target_mem = min(max_mem, curr_mem * 2 if curr_mem < max_mem else max_mem)

            if target_cpu == curr_cpu and target_mem == curr_mem:
                record["decision"] = DECISION_BLOCKED_BY_POLICY
                record["reason"] = f"High load detected, but VM is already at maximum policy limit ({max_cpu} vCPU, {max_mem} GB RAM)."
                self._record_decision(record)
                return record

            record["decision"] = DECISION_VM_SCALE_UP
            record["proposed_allocation"] = {"cpu_cores": target_cpu, "memory_gb": target_mem}
            after_cost = estimate_vm_monthly_cost(target_cpu, target_mem)
            record["estimated_cost_after_inr"] = after_cost
            record["estimated_monthly_savings_inr"] = round(curr_cost - after_cost, 2)
            record["reason"] = f"Sustained guest demand (CPU {observed_guest_cpu:.1f}%, RAM {observed_guest_ram_percent:.1f}%). Proposing vertical scale-up to {target_cpu} vCPU, {target_mem} GB RAM."

        elif needs_scale_down:
            self._scale_up_samples.pop(domain_name, None)
            samples = self._scale_down_samples.setdefault(domain_name, [])
            samples.append(now_mono)

            if len(samples) < self.config.sustained_window_samples:
                record["decision"] = DECISION_NO_ACTION
                record["reason"] = (
                    f"Low VM utilization detected ({observed_guest_cpu:.1f}%), evaluating sustained window: "
                    f"sample {len(samples)} of {self.config.sustained_window_samples} required."
                )
                self._record_decision(record)
                return record

            if cooldown_remaining > 0:
                record["decision"] = DECISION_NO_ACTION
                record["reason"] = f"Scale-down indicated, but cooldown active ({cooldown_remaining:.1f}s remaining)."
                self._record_decision(record)
                return record

            # Propose Scale Down
            target_cpu = max(min_cpu, curr_cpu / 2 if curr_cpu > min_cpu else min_cpu)
            target_mem = max(min_mem, curr_mem / 2 if curr_mem > min_mem else min_mem)

            if target_cpu == curr_cpu and target_mem == curr_mem:
                record["decision"] = DECISION_BLOCKED_BY_POLICY
                record["reason"] = f"Workload is under-utilized, but VM is already at minimum policy bounds ({min_cpu} vCPU, {min_mem} GB RAM)."
                self._record_decision(record)
                return record

            record["decision"] = DECISION_VM_SCALE_DOWN
            record["proposed_allocation"] = {"cpu_cores": target_cpu, "memory_gb": target_mem}
            after_cost = estimate_vm_monthly_cost(target_cpu, target_mem)
            record["estimated_cost_after_inr"] = after_cost
            record["estimated_monthly_savings_inr"] = round(curr_cost - after_cost, 2)
            record["reason"] = f"Sustained low guest demand (CPU {observed_guest_cpu:.1f}%, RAM {observed_guest_ram_percent:.1f}%). Proposing vertical downsizing to {target_cpu} vCPU, {target_mem} GB RAM."

        else:
            self._scale_up_samples.pop(domain_name, None)
            self._scale_down_samples.pop(domain_name, None)
            record["decision"] = DECISION_NO_ACTION
            record["reason"] = f"Guest workload within normal operating thresholds (CPU {observed_guest_cpu:.1f}%, RAM {observed_guest_ram_percent:.1f}%)."
            self._record_decision(record)
            return record

        # 3. Execution based on mode
        if mode == MODE_DRY_RUN:
            record["reason"] += " [DRY_RUN mode active: evaluation only, no hypervisor mutation]."
            self._record_decision(record)
            return record

        if mode == MODE_RECOMMENDATION or requires_approval:
            record["reason"] += " [RECOMMENDATION: Requires administrator approval prior to hypervisor execution]."
            if db_session and resource:
                self._create_change_request(db_session, resource, record, actor)
            self._record_decision(record)
            return record

        # MODE_AUTO Execution
        if mode == MODE_AUTO:
            target_c = record["proposed_allocation"]["cpu_cores"]
            target_m = record["proposed_allocation"]["memory_gb"]

            result = self.adapter.resize_vm(
                domain_name=domain_name,
                target_cpu=target_c,
                target_memory_gb=target_m,
                policy=policy,
                allow_shutdown=allow_shutdown,
            )

            if result["success"]:
                record["executed"] = True
                record["verified"] = True
                record["reason"] += f" Successfully verified hypervisor limits ({target_c} vCPU, {target_m} GB RAM)."
                self._last_action_timestamp[domain_name] = now_mono
                self._scale_up_samples.pop(domain_name, None)
                self._scale_down_samples.pop(domain_name, None)

                if db_session and resource:
                    resource.cpu_cores = int(target_c)
                    resource.memory = float(target_m)
                    resource.estimated_monthly_cost = record["estimated_cost_after_inr"]
                    self._record_audit(db_session, resource, record["decision"], "SUCCESS", "OPTIMIZER_VM_AUTO", record["reason"])
            else:
                record["executed"] = False
                record["verified"] = False
                record["requires_shutdown"] = result.get("requires_shutdown", False)
                record["reason"] += f" Execution halted: {result.get('error', 'Unknown error')}"
                if db_session and resource:
                    self._record_audit(db_session, resource, record["decision"], "FAILURE", "OPTIMIZER_VM_AUTO", result.get("error", ""))

        self._record_decision(record)
        return record

    def _create_change_request(self, db_session: Any, resource: CloudResource, record: Dict[str, Any], actor: Any):
        try:
            cr = ResourceChangeRequest(
                id=f"cr-vm-{uuid.uuid4().hex[:8]}",
                tenant_id=resource.tenant_id,
                resource_id=resource.id,
                requester_id=actor.id if actor else "optimizer-vm-service",
                current_cpu=int(record["current_allocation"]["cpu_cores"]),
                requested_cpu=int(record["proposed_allocation"]["cpu_cores"]),
                current_memory_gb=float(record["current_allocation"]["memory_gb"]),
                requested_memory_gb=float(record["proposed_allocation"]["memory_gb"]),
                estimated_cost_before=record["estimated_cost_before_inr"],
                estimated_cost_after=record["estimated_cost_after_inr"],
                monthly_cost_diff=round(record["estimated_cost_after_inr"] - record["estimated_cost_before_inr"], 2),
                status="PENDING",
                reason=f"KVM Optimizer: {record['reason']}",
            )
            db_session.add(cr)
            db_session.commit()
            record["change_request_id"] = cr.id
        except Exception:
            pass

    def _record_audit(self, db_session: Any, resource: CloudResource, action: str, outcome: str, actor_id: str, reason: str):
        try:
            audit = AuditEvent(
                id=f"audit-vm-{uuid.uuid4().hex[:8]}",
                actor_id=actor_id,
                actor_role="VM_OPTIMIZER_SERVICE",
                tenant_id=resource.tenant_id,
                resource_id=resource.id,
                action=f"KVM_VM_{action}",
                outcome=outcome,
                reason=reason,
            )
            db_session.add(audit)
            db_session.commit()
        except Exception:
            pass

    def _record_decision(self, record: Dict[str, Any]):
        self._decisions.insert(0, record)
        if len(self._decisions) > 100:
            self._decisions = self._decisions[:100]
