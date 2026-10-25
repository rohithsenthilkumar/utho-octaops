"""
Test Engine 1 Dynamic Adaptation
=================================
This script demonstrates how Engine 1 dynamically changes its recommendation
when request rate / traffic load shifts on a VM.

Scenario:
1. Low Load Profile (underutilized VM) -> Engine 1 recommends DOWNSIZE (saving money).
2. Spiky / Bursty Load Profile -> Engine 1 detects high p99 burst -> Marks HIGH RISK or blocks downsize.
3. Heavy / Overloaded Profile -> Engine 1 detects p99 > 90% -> Recommends UPSIZE (outage prevention).
"""

import json
import numpy as np
from engines.metrics_analyzer import analyze_metrics
from engines.rightsizing import RightsizingEngine

with open("data/pricing_catalog.json") as f:
    pricing = json.load(f)

engine = RightsizingEngine(pricing)

# Base VM specification (c5.2xlarge equivalent: 8 vCPU, 32 GB RAM, performance-1 in prod)
base_vm = {
    "resource_id": "vm-test-dynamic",
    "name": "prod-workload-tester",
    "type": "vm",
    "region": "Bangalore",
    "environment": "prod",
    "owner": "Core API",
    "instance_tier": "performance-1",
    "vcpu": 8,
    "ram_gb": 32,
    "disk_gb": 200,
    "monthly_cost_inr": 14400,
    "status": "running"
}

def generate_telemetry(pattern_type: str):
    """Generates 720 hours (30 days) of telemetry based on traffic pattern."""
    np.random.seed(42)
    records = []
    
    for h in range(720):
        if pattern_type == "LOW_LOAD":
            # Idle / steady low traffic: CPU 5-15%, RAM 20%
            cpu = np.clip(np.random.normal(12, 3), 2, 25)
            ram = np.clip(np.random.normal(25, 2), 15, 35)
        elif pattern_type == "BURSTY_PEAKS":
            # Normal 15%, but spikes to 80% daily for 2 hours
            hour_of_day = h % 24
            if 14 <= hour_of_day <= 16:
                cpu = np.clip(np.random.normal(82, 5), 60, 95)
            else:
                cpu = np.clip(np.random.normal(15, 3), 5, 25)
            ram = np.clip(np.random.normal(45, 4), 30, 60)
        elif pattern_type == "OVERLOADED":
            # Heavy continuous load: CPU 85-98%, RAM 92%
            cpu = np.clip(np.random.normal(92, 4), 70, 99)
            ram = np.clip(np.random.normal(94, 2), 85, 98)
            
        records.append({
            "timestamp": f"2026-10-01T{h%24:02d}:00:00",
            "cpu_percent": float(cpu),
            "ram_percent": float(ram),
            "disk_percent": 40.0,
            "disk_iops": float(cpu * 10),
            "network_in_kbps": float(cpu * 50),
            "network_out_kbps": float(cpu * 30)
        })
    return records

print("=====================================================================")
print("🧪 TESTING ENGINE 1: DYNAMIC ADAPTATION TO TRAFFIC / REQUEST RATES")
print("=====================================================================\n")

scenarios = [
    ("Scenario 1: Low Request Rate (Underutilized)", "LOW_LOAD"),
    ("Scenario 2: Bursty Request Rate (Short Daily Peaks)", "BURSTY_PEAKS"),
    ("Scenario 3: High Request Rate Surge (Resource Exhaustion)", "OVERLOADED"),
]

for title, pattern in scenarios:
    print(f"--- {title} ---")
    telemetry = generate_telemetry(pattern)
    summary = analyze_metrics(telemetry)
    
    # Run Engine 1 analysis
    rec = engine._analyze_resource(base_vm, summary, rec_idx=1)
    
    print(f"  • Traffic Stats  : Mean CPU={summary['cpu']['mean']}%, p95 CPU={summary['cpu']['p95']}%, p99 CPU={summary['cpu']['p99']}%, Burst Ratio={summary['burst_ratio']}x")
    if rec:
        print(f"  • Action Decided : [{rec['action']}]")
        print(f"  • Recommendation : Current '{rec['current_spec']}' -> '{rec['recommended_spec']}'")
        print(f"  • Cost Impact    : Current ₹{rec['current_monthly_cost_inr']} -> Projected ₹{rec['projected_monthly_cost_inr']} (Savings: ₹{rec['estimated_savings_inr']})")
        print(f"  • Risk Level     : {rec['risk_level']}")
        print(f"  • Justification  : {rec['justification']}")
    else:
        print("  • Action Decided : [KEEP_CURRENT] - VM is optimally sized for current peak loads.")
    print()

