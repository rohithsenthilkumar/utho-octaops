"""
Engine: Metrics Analyzer
========================
Computes statistical summaries (mean, p50, p95, p99, min, max) for
each metric dimension of a single cloud resource, plus derived
indicators like burst ratio and weekday/weekend averages.
"""

from typing import Any
import numpy as np
from datetime import datetime


def analyze_metrics(metrics_records: list[dict]) -> dict[str, Any]:
    """
    Compute a full statistical summary from raw time-series records.

    Parameters
    ----------
    metrics_records : list[dict]
        Each dict has keys: timestamp, cpu_percent, ram_percent,
        disk_percent, disk_iops, network_in_kbps, network_out_kbps.

    Returns
    -------
    dict  with per-metric stats and derived indicators.
    """
    if not metrics_records:
        return {}

    cpu = np.array([r["cpu_percent"] for r in metrics_records])
    ram = np.array([r["ram_percent"] for r in metrics_records])
    disk = np.array([r["disk_percent"] for r in metrics_records])
    iops = np.array([r["disk_iops"] for r in metrics_records])
    net_in = np.array([r["network_in_kbps"] for r in metrics_records])
    net_out = np.array([r["network_out_kbps"] for r in metrics_records])

    def _stats(arr: np.ndarray) -> dict:
        return {
            "mean": round(float(np.mean(arr)), 2),
            "p50": round(float(np.percentile(arr, 50)), 2),
            "p95": round(float(np.percentile(arr, 95)), 2),
            "p99": round(float(np.percentile(arr, 99)), 2),
            "min": round(float(np.min(arr)), 2),
            "max": round(float(np.max(arr)), 2),
            "std": round(float(np.std(arr)), 2),
        }

    cpu_stats = _stats(cpu)
    ram_stats = _stats(ram)

    # Burst ratio: how spiky is CPU relative to its average?
    burst_ratio = round(cpu_stats["p99"] / cpu_stats["mean"], 2) if cpu_stats["mean"] > 0 else 0.0

    # Weekday vs weekend breakdown
    weekday_cpu = []
    weekend_cpu = []
    weekday_ram = []
    weekend_ram = []
    hourly_cpu = {h: [] for h in range(24)}

    for r in metrics_records:
        ts = datetime.fromisoformat(r["timestamp"])
        dow = ts.weekday()  # 0=Mon, 6=Sun
        hour = ts.hour
        hourly_cpu[hour].append(r["cpu_percent"])
        if dow >= 5:
            weekend_cpu.append(r["cpu_percent"])
            weekend_ram.append(r["ram_percent"])
        else:
            weekday_cpu.append(r["cpu_percent"])
            weekday_ram.append(r["ram_percent"])

    hourly_avg_cpu = {h: round(float(np.mean(v)), 2) if v else 0.0
                      for h, v in hourly_cpu.items()}

    # Idle detection: are last 14 days (336 hours) all below thresholds?
    last_14d = metrics_records[-336:] if len(metrics_records) >= 336 else metrics_records
    last_14d_cpu = np.array([r["cpu_percent"] for r in last_14d])
    last_14d_net = np.array([r["network_in_kbps"] + r["network_out_kbps"] for r in last_14d])
    is_idle_14d = bool(np.percentile(last_14d_cpu, 95) < 3.0 and np.mean(last_14d_net) < 50)

    # Disk growth trend (linear slope in percent per day)
    if len(disk) > 48:
        x = np.arange(len(disk)) / 24.0  # days
        slope, _ = np.polyfit(x, disk, 1)
        disk_growth_pct_per_day = round(float(slope), 4)
    else:
        disk_growth_pct_per_day = 0.0

    # RAM trend (for memory leak detection)
    if len(ram) > 48:
        x = np.arange(len(ram)) / 24.0
        slope_ram, _ = np.polyfit(x, ram, 1)
        ram_trend_pct_per_day = round(float(slope_ram), 4)
    else:
        ram_trend_pct_per_day = 0.0

    return {
        "cpu": cpu_stats,
        "ram": ram_stats,
        "disk": _stats(disk),
        "disk_iops": _stats(iops),
        "network_in": _stats(net_in),
        "network_out": _stats(net_out),
        "burst_ratio": burst_ratio,
        "weekday_avg_cpu": round(float(np.mean(weekday_cpu)), 2) if weekday_cpu else 0.0,
        "weekend_avg_cpu": round(float(np.mean(weekend_cpu)), 2) if weekend_cpu else 0.0,
        "weekday_avg_ram": round(float(np.mean(weekday_ram)), 2) if weekday_ram else 0.0,
        "weekend_avg_ram": round(float(np.mean(weekend_ram)), 2) if weekend_ram else 0.0,
        "hourly_avg_cpu": hourly_avg_cpu,
        "is_idle_14d": is_idle_14d,
        "disk_growth_pct_per_day": disk_growth_pct_per_day,
        "ram_trend_pct_per_day": ram_trend_pct_per_day,
        "total_data_points": len(metrics_records),
    }
