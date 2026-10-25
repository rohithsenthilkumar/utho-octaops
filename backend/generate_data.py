"""
SmartCloud Optimizer — Synthetic Data Generator
================================================
Generates realistic 30-day cloud infrastructure telemetry for 80 VMs,
5 orphaned block volumes, and 5 unused public IPs.

Run once to create data/inventory.json and data/metrics_data.json.
Replace this script's output files with real cloud API data for production use.
"""

import json
import os
import math
import numpy as np
from datetime import datetime, timedelta

# ---------- reproducibility ----------
np.random.seed(42)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")

# ---------- load pricing catalog ----------
with open(os.path.join(DATA_DIR, "pricing_catalog.json")) as f:
    PRICING = json.load(f)

TIER_MAP = {t["tier"]: t for t in PRICING["instance_types"]}

# ---------- time grid: 30 days, 1-hour intervals ----------
END_TIME = datetime(2026, 10, 23, 23, 0, 0)
START_TIME = END_TIME - timedelta(days=30)
HOURS = int((END_TIME - START_TIME).total_seconds() // 3600)  # 720
TIMESTAMPS = [(START_TIME + timedelta(hours=h)).isoformat() for h in range(HOURS)]

# Helper: hour-of-day and day-of-week arrays for pattern shaping
HOD = np.array([(START_TIME + timedelta(hours=h)).hour for h in range(HOURS)])
DOW = np.array([(START_TIME + timedelta(hours=h)).weekday() for h in range(HOURS)])  # 0=Mon
IS_WEEKEND = (DOW >= 5).astype(float)
DAY_INDEX = np.array([(START_TIME + timedelta(hours=h)).timetuple().tm_yday
                       for h in range(HOURS)])

# ---------- pattern generators ----------

def _clamp(arr: np.ndarray, lo: float = 0.0, hi: float = 100.0) -> np.ndarray:
    return np.clip(arr, lo, hi)


def _noise(n: int, scale: float = 2.0) -> np.ndarray:
    return np.random.normal(0, scale, n)


def pattern_bursty_api(vm_idx: int) -> dict:
    """prod-core-api: low at night, 70-90% spike during 2-4 PM."""
    base_cpu = 12 + vm_idx * 1.5
    cpu = np.full(HOURS, base_cpu)
    for h in range(HOURS):
        hour = HOD[h]
        if 9 <= hour <= 18:
            cpu[h] += 15  # business hours uplift
        if 14 <= hour <= 16:
            cpu[h] += 40 + np.random.uniform(-5, 10)  # peak burst
        if IS_WEEKEND[h]:
            cpu[h] *= 0.4
    cpu = _clamp(cpu + _noise(HOURS, 3))
    ram = _clamp(np.full(HOURS, 45 + vm_idx * 2) + _noise(HOURS, 3))
    disk = _clamp(np.full(HOURS, 35) + np.linspace(0, 3, HOURS) + _noise(HOURS, 0.5))
    iops = _clamp(cpu * 12 + _noise(HOURS, 20), lo=5, hi=3000)
    net_in = _clamp(cpu * 50 + _noise(HOURS, 40), lo=10, hi=10000)
    net_out = _clamp(cpu * 35 + _noise(HOURS, 30), lo=10, hi=8000)
    return _pack(cpu, ram, disk, iops, net_in, net_out)


def pattern_batch_worker(vm_idx: int) -> dict:
    """prod-batch-worker: dormant 22 hrs, spike 1-3 AM."""
    cpu = np.full(HOURS, 3.0) + _noise(HOURS, 1)
    ram = np.full(HOURS, 8.0) + _noise(HOURS, 2)
    for h in range(HOURS):
        if 1 <= HOD[h] <= 2:
            cpu[h] = 88 + np.random.uniform(-5, 7)
            ram[h] = 72 + np.random.uniform(-5, 8)
    cpu = _clamp(cpu)
    ram = _clamp(ram)
    disk = _clamp(np.full(HOURS, 40) + _noise(HOURS, 1))
    iops = _clamp(cpu * 15 + _noise(HOURS, 10), lo=2, hi=5000)
    net_in = _clamp(cpu * 30 + _noise(HOURS, 20), lo=5, hi=6000)
    net_out = _clamp(cpu * 20 + _noise(HOURS, 15), lo=5, hi=4000)
    return _pack(cpu, ram, disk, iops, net_in, net_out)


def pattern_dev_idle(vm_idx: int) -> dict:
    """dev-test-runner: 3-8% weekdays, near 0 weekends."""
    base = 4 + vm_idx * 0.5
    cpu = np.full(HOURS, base)
    for h in range(HOURS):
        if IS_WEEKEND[h]:
            cpu[h] = 0.5 + np.random.uniform(0, 0.8)
        elif 9 <= HOD[h] <= 18:
            cpu[h] += 2 + np.random.uniform(0, 3)
    cpu = _clamp(cpu + _noise(HOURS, 0.8))
    ram = _clamp(cpu * 2.5 + 5 + _noise(HOURS, 1.5))
    disk = _clamp(np.full(HOURS, 20) + _noise(HOURS, 0.3))
    iops = _clamp(cpu * 3 + _noise(HOURS, 2), lo=0, hi=500)
    net_in = _clamp(cpu * 8 + _noise(HOURS, 5), lo=0, hi=500)
    net_out = _clamp(cpu * 5 + _noise(HOURS, 3), lo=0, hi=300)
    return _pack(cpu, ram, disk, iops, net_in, net_out)


def pattern_zombie(vm_idx: int) -> dict:
    """staging-analytics-old: constant 1-3% CPU, basically forgotten."""
    cpu = _clamp(np.full(HOURS, 1.5) + _noise(HOURS, 0.5))
    ram = _clamp(np.full(HOURS, 6.0) + _noise(HOURS, 0.8))
    disk = _clamp(np.full(HOURS, 55) + _noise(HOURS, 0.2))
    iops = _clamp(np.full(HOURS, 3.0) + _noise(HOURS, 1), lo=0, hi=50)
    net_in = _clamp(np.full(HOURS, 2.0) + _noise(HOURS, 1), lo=0, hi=30)
    net_out = _clamp(np.full(HOURS, 1.0) + _noise(HOURS, 0.5), lo=0, hi=20)
    return _pack(cpu, ram, disk, iops, net_in, net_out)


def pattern_memory_leak(vm_idx: int) -> dict:
    """prod-payment-gateway-02: normal CPU, RAM leak starting day 20."""
    cpu = np.full(HOURS, 32.0)
    for h in range(HOURS):
        if 10 <= HOD[h] <= 20:
            cpu[h] += 15 + np.random.uniform(-3, 5)
    cpu = _clamp(cpu + _noise(HOURS, 3))

    # RAM: normal baseline 30%, then leak starts at hour 480 (day 20)
    ram = np.full(HOURS, 30.0) + _noise(HOURS, 2)
    leak_start = 20 * 24  # hour 480
    for h in range(leak_start, HOURS):
        days_since_leak = (h - leak_start) / 24.0
        ram[h] += days_since_leak * 4.5  # ~4.5% per day increase
    ram = _clamp(ram)

    disk = _clamp(np.full(HOURS, 45) + np.linspace(0, 8, HOURS) + _noise(HOURS, 0.5))
    iops = _clamp(cpu * 10 + _noise(HOURS, 15), lo=5, hi=3000)
    net_in = _clamp(cpu * 40 + _noise(HOURS, 30), lo=10, hi=8000)
    net_out = _clamp(cpu * 25 + _noise(HOURS, 20), lo=10, hi=6000)
    return _pack(cpu, ram, disk, iops, net_in, net_out)


def pattern_staging_moderate(vm_idx: int) -> dict:
    """Staging VMs: 20-40% weekday, idle weekends."""
    base = 22 + vm_idx * 2
    cpu = np.full(HOURS, base)
    for h in range(HOURS):
        if IS_WEEKEND[h]:
            cpu[h] = 3 + np.random.uniform(0, 2)
        elif 10 <= HOD[h] <= 17:
            cpu[h] += 10 + np.random.uniform(-3, 5)
    cpu = _clamp(cpu + _noise(HOURS, 3))
    ram = _clamp(cpu * 0.8 + 15 + _noise(HOURS, 2))
    disk = _clamp(np.full(HOURS, 30) + _noise(HOURS, 0.5))
    iops = _clamp(cpu * 8 + _noise(HOURS, 10), lo=2, hi=2000)
    net_in = _clamp(cpu * 20 + _noise(HOURS, 15), lo=5, hi=4000)
    net_out = _clamp(cpu * 12 + _noise(HOURS, 10), lo=5, hi=3000)
    return _pack(cpu, ram, disk, iops, net_in, net_out)


def pattern_prod_webserver(vm_idx: int) -> dict:
    """General prod web servers: steady 30-50% with business peaks."""
    base = 30 + vm_idx * 1.5
    cpu = np.full(HOURS, base)
    for h in range(HOURS):
        if 10 <= HOD[h] <= 18:
            cpu[h] += 12 + np.random.uniform(-2, 6)
        if 12 <= HOD[h] <= 14:
            cpu[h] += 5  # lunch-hour micro-spike
        if IS_WEEKEND[h]:
            cpu[h] *= 0.55
    cpu = _clamp(cpu + _noise(HOURS, 3))
    ram = _clamp(cpu * 0.7 + 20 + _noise(HOURS, 2))
    disk = _clamp(np.full(HOURS, 40) + np.linspace(0, 2, HOURS) + _noise(HOURS, 0.4))
    iops = _clamp(cpu * 10 + _noise(HOURS, 12), lo=5, hi=2500)
    net_in = _clamp(cpu * 35 + _noise(HOURS, 25), lo=10, hi=6000)
    net_out = _clamp(cpu * 22 + _noise(HOURS, 18), lo=10, hi=5000)
    return _pack(cpu, ram, disk, iops, net_in, net_out)


def _pack(cpu, ram, disk, iops, net_in, net_out) -> dict:
    """Package numpy arrays into a list of metric dicts."""
    records = []
    for i in range(HOURS):
        records.append({
            "timestamp": TIMESTAMPS[i],
            "cpu_percent": round(float(cpu[i]), 2),
            "ram_percent": round(float(ram[i]), 2),
            "disk_percent": round(float(disk[i]), 2),
            "disk_iops": round(float(iops[i]), 1),
            "network_in_kbps": round(float(net_in[i]), 1),
            "network_out_kbps": round(float(net_out[i]), 1),
        })
    return {"metrics": records}


# ---------- VM definitions ----------

def _make_vm(rid: str, name: str, region: str, env: str, owner: str,
             tier: str, disk_gb: int, created: str, status: str = "running") -> dict:
    t = TIER_MAP[tier]
    return {
        "resource_id": rid,
        "name": name,
        "type": "vm",
        "region": region,
        "environment": env,
        "owner": owner,
        "instance_tier": tier,
        "vcpu": t["vcpu"],
        "ram_gb": t["ram_gb"],
        "disk_gb": disk_gb,
        "os": "Ubuntu 22.04",
        "created_date": created,
        "monthly_cost_inr": t["monthly_cost_inr"] + disk_gb * PRICING["storage_cost_per_gb_month_inr"],
        "status": status,
    }


def generate_inventory():
    vms = []
    metrics = {}
    idx = 1

    # --- 1. prod-core-api (8 VMs, Bangalore, bursty) ---
    for i in range(8):
        rid = f"vm-{idx:03d}"
        vm = _make_vm(rid, f"prod-core-api-{i+1:02d}", "Bangalore", "prod",
                       "Core API", "performance-1", 200, "2025-03-15")
        vms.append(vm)
        metrics[rid] = pattern_bursty_api(i)
        idx += 1

    # --- 2. prod-batch-worker (3 VMs, Mumbai, batch spikes) ---
    for i in range(3):
        rid = f"vm-{idx:03d}"
        vm = _make_vm(rid, f"prod-batch-worker-{i+1:02d}", "Mumbai", "prod",
                       "Data Engineering", "performance-1", 500, "2025-06-01")
        vms.append(vm)
        metrics[rid] = pattern_batch_worker(i)
        idx += 1

    # --- 3. dev-test-runner (6 VMs, Noida, idle weekends) ---
    for i in range(6):
        rid = f"vm-{idx:03d}"
        vm = _make_vm(rid, f"dev-test-runner-{i+1:02d}", "Noida", "dev",
                       "standard-2", "standard-2", 100, "2025-09-10")
        vms.append(vm)
        metrics[rid] = pattern_dev_idle(i)
        idx += 1

    # --- 4. staging-analytics-old (1 zombie VM, Mumbai) ---
    rid = f"vm-{idx:03d}"
    vm = _make_vm(rid, "staging-analytics-old", "Mumbai", "staging",
                   "Data Engineering", "standard-2", 200, "2024-12-05")
    vms.append(vm)
    metrics[rid] = pattern_zombie(0)
    idx += 1

    # --- 5. prod-payment-gateway-02 (1 VM, Bangalore, memory leak anomaly) ---
    rid = f"vm-{idx:03d}"
    vm = _make_vm(rid, "prod-payment-gateway-02", "Bangalore", "prod",
                   "Core API", "performance-1", 200, "2025-04-20")
    vms.append(vm)
    metrics[rid] = pattern_memory_leak(0)
    idx += 1

    # --- 6. Staging moderate VMs (14 VMs across regions) ---
    stg_regions = ["Noida"] * 5 + ["Bangalore"] * 5 + ["Mumbai"] * 4
    stg_owners = ["Frontend", "DevOps", "ML Platform", "Core API", "Data Engineering"]
    for i in range(14):
        rid = f"vm-{idx:03d}"
        vm = _make_vm(rid, f"staging-svc-{i+1:02d}", stg_regions[i], "staging",
                       stg_owners[i % len(stg_owners)], "standard-2", 100, "2025-07-15")
        vms.append(vm)
        metrics[rid] = pattern_staging_moderate(i)
        idx += 1

    # --- 7. General prod web servers (24 VMs across regions) ---
    prod_regions = ["Noida"] * 8 + ["Bangalore"] * 8 + ["Mumbai"] * 8
    prod_owners = ["Core API", "Frontend", "DevOps", "ML Platform", "Data Engineering"]
    prod_tiers = ["standard-2", "performance-1"]
    for i in range(24):
        rid = f"vm-{idx:03d}"
        tier = prod_tiers[i % 2]
        vm = _make_vm(rid, f"prod-web-{i+1:02d}", prod_regions[i], "prod",
                       prod_owners[i % len(prod_owners)], tier,
                       150 + (i % 3) * 50, "2025-05-01")
        vms.append(vm)
        metrics[rid] = pattern_prod_webserver(i)
        idx += 1

    # --- 8. Dev VMs (14 more, Noida, low usage) ---
    for i in range(14):
        rid = f"vm-{idx:03d}"
        owners_dev = ["Frontend", "Core API", "ML Platform", "DevOps", "Data Engineering"]
        vm = _make_vm(rid, f"dev-env-{i+1:02d}", "Noida", "dev",
                       owners_dev[i % len(owners_dev)], "standard-1", 80, "2025-10-01")
        vms.append(vm)
        metrics[rid] = pattern_dev_idle(i)
        idx += 1

    # --- 9. QA VMs (5, Bangalore, low usage) ---
    for i in range(5):
        rid = f"vm-{idx:03d}"
        vm = _make_vm(rid, f"qa-runner-{i+1:02d}", "Bangalore", "qa",
                       "DevOps", "basic-2", 50, "2026-01-15")
        vms.append(vm)
        metrics[rid] = pattern_dev_idle(i)
        idx += 1

    # --- Orphaned block volumes ---
    volumes = []
    for i in range(5):
        size = [500, 250, 300, 100, 200][i]
        region = ["Bangalore", "Noida", "Mumbai", "Bangalore", "Noida"][i]
        volumes.append({
            "resource_id": f"vol-{i+1:03d}",
            "name": f"orphan-vol-snap-{i+1:02d}",
            "type": "block_volume",
            "region": region,
            "size_gb": size,
            "attached_to": None,
            "created_date": "2025-06-10",
            "last_detached_date": "2026-09-15",
            "monthly_cost_inr": size * PRICING["storage_cost_per_gb_month_inr"],
            "status": "available",
        })

    # --- Unused public IPs ---
    ips = []
    for i in range(5):
        region = ["Noida", "Noida", "Bangalore", "Mumbai", "Mumbai"][i]
        ips.append({
            "resource_id": f"ip-{i+1:03d}",
            "name": f"unused-elastic-ip-{i+1:02d}",
            "type": "public_ip",
            "region": region,
            "ip_address": f"203.0.113.{10+i}",
            "associated_instance": None,
            "created_date": "2025-08-20",
            "monthly_cost_inr": PRICING["public_ip_monthly_cost_inr"],
            "status": "available",
        })

    inventory = vms + volumes + ips
    return inventory, metrics


def main():
    print("Generating synthetic cloud infrastructure data …")
    inventory, metrics = generate_inventory()

    inv_path = os.path.join(DATA_DIR, "inventory.json")
    met_path = os.path.join(DATA_DIR, "metrics_data.json")

    with open(inv_path, "w") as f:
        json.dump(inventory, f, indent=2)
    print(f"  ✓ Wrote {len(inventory)} resources to {inv_path}")

    vm_count = sum(1 for r in inventory if r["type"] == "vm")
    total_points = vm_count * HOURS
    with open(met_path, "w") as f:
        json.dump(metrics, f)  # compact — no indent for speed
    size_mb = os.path.getsize(met_path) / (1024 * 1024)
    print(f"  ✓ Wrote {total_points:,} metric data points ({size_mb:.1f} MB) to {met_path}")
    print("Done!")


if __name__ == "__main__":
    main()
