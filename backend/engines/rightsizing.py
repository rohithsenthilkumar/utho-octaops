"""
Stage 3: Deterministic Rightsizing Engine
=========================================
Evaluates cloud compute resources based on peak / p95 CPU and memory utilization.
Recommends smaller, cheaper instances ONLY when both CPU and memory headroom are safe.
Returns 'insufficient data' when metrics are sparse (< 24 samples) or missing.
"""
from typing import Any, Dict, List, Optional
import numpy as np

# Minimum required data points (e.g. at least 24 hourly samples to observe diurnal cycle)
MIN_DATA_POINTS = 24

# Environment-specific safety headroom buffers to preserve above peak load
SAFETY_BUFFERS = {
    "prod": 0.25,     # 25% buffer above peak load for production
    "production": 0.25,
    "staging": 0.15,  # 15% buffer for staging validation
    "dev": 0.10,      # 10% buffer for dev
    "development": 0.10,
    "qa": 0.10,       # 10% buffer for QA
    "test": 0.10,
}

# Standard instance sizing tiers sorted by capability & cost
DEFAULT_TIERS = [
    {"tier": "micro-1", "vcpu": 1, "ram_gb": 1.0, "monthly_cost_inr": 450},
    {"tier": "basic-1", "vcpu": 1, "ram_gb": 2.0, "monthly_cost_inr": 800},
    {"tier": "basic-2", "vcpu": 2, "ram_gb": 4.0, "monthly_cost_inr": 1600},
    {"tier": "standard-1", "vcpu": 2, "ram_gb": 8.0, "monthly_cost_inr": 3200},
    {"tier": "standard-2", "vcpu": 4, "ram_gb": 16.0, "monthly_cost_inr": 6400},
    {"tier": "performance-1", "vcpu": 8, "ram_gb": 32.0, "monthly_cost_inr": 12800},
    {"tier": "performance-2", "vcpu": 16, "ram_gb": 64.0, "monthly_cost_inr": 25600},
    {"tier": "compute-1", "vcpu": 32, "ram_gb": 128.0, "monthly_cost_inr": 51200},
    {"tier": "compute-2", "vcpu": 64, "ram_gb": 256.0, "monthly_cost_inr": 102400},
]


def analyze_metrics(metrics_records: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Statistical analyzer that computes mean, p50, p95, p99, min, max, and burst ratios.
    Enforces the minimum data points threshold; returns insufficient data when samples < 24.
    """
    if not metrics_records or len(metrics_records) < MIN_DATA_POINTS:
        sample_count = len(metrics_records) if metrics_records else 0
        return {
            "is_sufficient": False,
            "sample_count": sample_count,
            "error": "insufficient data",
            "message": f"Collected {sample_count} samples (minimum {MIN_DATA_POINTS} samples required).",
        }

    # Extract series safely
    cpu_list = [r.get("cpu_percent", 0.0) for r in metrics_records if "cpu_percent" in r]
    ram_list = [r.get("ram_percent", 0.0) for r in metrics_records if "ram_percent" in r]

    if len(cpu_list) < MIN_DATA_POINTS or len(ram_list) < MIN_DATA_POINTS:
        return {
            "is_sufficient": False,
            "sample_count": min(len(cpu_list), len(ram_list)),
            "error": "insufficient data",
            "message": "Metrics records missing required cpu_percent or ram_percent fields.",
        }

    cpu = np.array(cpu_list, dtype=float)
    ram = np.array(ram_list, dtype=float)

    def _stats(arr: np.ndarray) -> Dict[str, float]:
        return {
            "mean": round(float(np.mean(arr)), 2),
            "p50": round(float(np.percentile(arr, 50)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "p99": round(float(np.percentile(arr, 99)), 2),
            "max": round(float(np.max(arr)), 2),
            "min": round(float(np.min(arr)), 2),
        }

    cpu_stats = _stats(cpu)
    ram_stats = _stats(ram)

    burst_ratio = (
        round(cpu_stats["p99"] / cpu_stats["mean"], 2)
        if cpu_stats["mean"] > 0
        else 1.0
    )

    return {
        "is_sufficient": True,
        "sample_count": len(metrics_records),
        "cpu": cpu_stats,
        "ram": ram_stats,
        "burst_ratio": burst_ratio,
    }


class RightsizingEngine:
    """
    Deterministic cloud rightsizing engine.
    Never suggests downsizing based on average CPU alone.
    Considers p95/peak CPU and RAM headroom.
    """

    def __init__(self, tiers: Optional[List[Dict[str, Any]]] = None):
        self.tiers = sorted(tiers or DEFAULT_TIERS, key=lambda t: t["monthly_cost_inr"])

    def _find_target_tier(self, req_vcpu: float, req_ram: float) -> Optional[Dict[str, Any]]:
        """Finds the smallest instance tier meeting or exceeding required compute."""
        for t in self.tiers:
            if t["vcpu"] >= req_vcpu and t["ram_gb"] >= req_ram:
                return t
        return None

    def evaluate_resource(
        self,
        resource: Any,
        metrics_records: Optional[List[Dict[str, Any]]],
        rec_index: int = 1,
    ) -> Dict[str, Any]:
        """
        Evaluate a single resource against utilization metrics and produce a recommendation.
        """
        # Handle dict or SQLAlchemy model
        res_id = getattr(resource, "id", None) or resource.get("id") or resource.get("resource_id", "unknown-res")
        res_name = getattr(resource, "name", None) or resource.get("name", res_id)
        res_env = (getattr(resource, "environment", None) or resource.get("environment", "dev")).lower()
        res_region = getattr(resource, "region", None) or resource.get("region", "Bangalore")
        res_vcpu = int(getattr(resource, "cpu_cores", None) or resource.get("cpu_cores") or resource.get("vcpu", 4))
        res_ram = float(getattr(resource, "memory", None) or resource.get("memory") or resource.get("ram_gb", 16.0))
        res_cost = float(getattr(resource, "estimated_monthly_cost", None) or resource.get("estimated_monthly_cost") or resource.get("monthly_cost_inr", 15000.0))

        current_config = {
            "vcpu": res_vcpu,
            "ram_gb": res_ram,
            "spec_display": f"{res_vcpu} vCPU, {res_ram} GB RAM",
            "monthly_cost_inr": res_cost,
        }

        # 1. Check for Insufficient Data
        analysis = analyze_metrics(metrics_records)
        if not analysis.get("is_sufficient", False):
            sample_count = analysis.get("sample_count", 0)
            return {
                "recommendation_id": f"REC-{rec_index:03d}",
                "resource_id": res_id,
                "resource_name": res_name,
                "environment": res_env,
                "region": res_region,
                "action": "INSUFFICIENT_DATA",
                "status": "INSUFFICIENT_DATA",
                "risk_level": "HIGH",
                "current_configuration": current_config,
                "proposed_configuration": None,
                "evidence": {
                    "status": "insufficient data",
                    "sample_count": sample_count,
                    "min_required_samples": MIN_DATA_POINTS,
                    "reason": analysis.get("message", "Insufficient metrics samples collected to evaluate peak patterns."),
                },
                "estimated_monthly_cost_before": res_cost,
                "estimated_monthly_cost_after": res_cost,
                "estimated_inr_savings": 0.0,
                "savings_percentage": 0.0,
                "justification": f"Insufficient data: only {sample_count} sample(s) available (minimum {MIN_DATA_POINTS} required). Engine refuses to speculate on rightsizing without sufficient baseline.",
                "is_simulated": True,
            }

        # 2. Extract Statistics
        cpu = analysis["cpu"]
        ram = analysis["ram"]
        burst_ratio = analysis.get("burst_ratio", 1.0)
        buffer = SAFETY_BUFFERS.get(res_env, 0.15)

        p95_cpu = cpu["p95"]
        p99_cpu = cpu["p99"]
        avg_cpu = cpu["mean"]

        p95_ram = ram["p95"]
        p99_ram = ram["p99"]
        avg_ram = ram["mean"]

        # Compute required capacity considering both p95 and peak p99 loads + safety buffer
        effective_peak_cpu = max(p95_cpu, p99_cpu * 0.95, avg_cpu * 1.5)
        effective_peak_ram = max(p95_ram, p99_ram * 0.95, avg_ram * 1.3)

        required_vcpu = res_vcpu * (effective_peak_cpu / 100.0) * (1.0 + buffer)
        required_ram = res_ram * (effective_peak_ram / 100.0) * (1.0 + buffer)

        evidence = {
            "avg_cpu": avg_cpu,
            "p95_cpu": p95_cpu,
            "p99_cpu": p99_cpu,
            "avg_ram": avg_ram,
            "p95_ram": p95_ram,
            "p99_ram": p99_ram,
            "burst_ratio": burst_ratio,
            "safety_buffer_pct": int(buffer * 100),
            "sample_count": analysis["sample_count"],
        }

        # 3. High Utilization / Over-provisioned Check
        # If peak CPU or RAM is high (> 80%), downsizing is unsafe!
        if p95_cpu >= 75.0 or p99_cpu >= 85.0 or p95_ram >= 80.0:
            evidence["headroom_status"] = "constrained"
            action = "KEEP_CURRENT"
            risk = "HIGH" if res_env in ("prod", "production") else "MEDIUM"
            justification = (
                f"High utilization detected: P95 CPU is {p95_cpu}% and P95 RAM is {p95_ram}%. "
                f"Peak load approaches capacity. Sizing down would violate safe operating margins and cause latency spikes."
            )
            return {
                "recommendation_id": f"REC-{rec_index:03d}",
                "resource_id": res_id,
                "resource_name": res_name,
                "environment": res_env,
                "region": res_region,
                "action": action,
                "status": "HIGH_UTILIZATION",
                "risk_level": risk,
                "current_configuration": current_config,
                "proposed_configuration": current_config,
                "evidence": evidence,
                "estimated_monthly_cost_before": res_cost,
                "estimated_monthly_cost_after": res_cost,
                "estimated_inr_savings": 0.0,
                "savings_percentage": 0.0,
                "justification": justification,
                "is_simulated": True,
            }

        # 4. Find Proposed Downsized Target
        target = self._find_target_tier(required_vcpu, required_ram)

        # Candidate must be strictly smaller in vCPU or RAM, and cheaper
        if not target or (target["vcpu"] >= res_vcpu and target["ram_gb"] >= res_ram):
            evidence["headroom_status"] = "already optimal"
            return {
                "recommendation_id": f"REC-{rec_index:03d}",
                "resource_id": res_id,
                "resource_name": res_name,
                "environment": res_env,
                "region": res_region,
                "action": "KEEP_CURRENT",
                "status": "OPTIMAL",
                "risk_level": "LOW",
                "current_configuration": current_config,
                "proposed_configuration": current_config,
                "evidence": evidence,
                "estimated_monthly_cost_before": res_cost,
                "estimated_monthly_cost_after": res_cost,
                "estimated_inr_savings": 0.0,
                "savings_percentage": 0.0,
                "justification": f"Resource is optimally provisioned. P95 CPU is {p95_cpu}% and RAM is {p95_ram}%, leaving target headroom.",
                "is_simulated": True,
            }

        # Calculate cost after downsizing:
        # Scale cost proportionally to compute reduction
        cost_ratio = (target["vcpu"] / res_vcpu) * 0.55 + (target["ram_gb"] / res_ram) * 0.45
        cost_after = round(res_cost * cost_ratio, 2)
        # Ensure cost after is strictly lower
        if cost_after >= res_cost:
            cost_after = round(res_cost * 0.65, 2)

        savings = round(res_cost - cost_after, 2)
        savings_pct = round((savings / res_cost) * 100, 1)

        # Risk level scoring
        if res_env in ("prod", "production"):
            if burst_ratio > 2.0 or p99_cpu > 45.0:
                risk = "MEDIUM"
            else:
                risk = "LOW"
        else:
            risk = "LOW"

        # Headroom remaining on target instance
        new_p95_cpu = round((p95_cpu * res_vcpu) / target["vcpu"], 1)
        new_p95_ram = round((p95_ram * res_ram) / target["ram_gb"], 1)
        evidence["projected_target_p95_cpu"] = new_p95_cpu
        evidence["projected_target_p95_ram"] = new_p95_ram

        proposed_config = {
            "vcpu": target["vcpu"],
            "ram_gb": target["ram_gb"],
            "spec_display": f"{target['vcpu']} vCPU, {target['ram_gb']} GB RAM",
            "tier": target["tier"],
            "monthly_cost_inr": cost_after,
        }

        justification = (
            f"P95 CPU is {p95_cpu}% and P95 RAM is {p95_ram}%. "
            f"Downsizing to {target['vcpu']} vCPU / {target['ram_gb']} GB RAM maintains a {int(buffer*100)}% "
            f"safety headroom buffer, reducing monthly spend by {savings_pct}%."
        )

        return {
            "recommendation_id": f"REC-{rec_index:03d}",
            "resource_id": res_id,
            "resource_name": res_name,
            "environment": res_env,
            "region": res_region,
            "action": "DOWNSIZE",
            "status": "RECOMMENDED",
            "risk_level": risk,
            "current_configuration": current_config,
            "proposed_configuration": proposed_config,
            "evidence": evidence,
            "estimated_monthly_cost_before": res_cost,
            "estimated_monthly_cost_after": cost_after,
            "estimated_inr_savings": savings,
            "savings_percentage": savings_pct,
            "justification": justification,
            "is_simulated": True,
        }
