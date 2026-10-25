"""
SmartCloud Optimizer — Stage 5 Autoscaling Controller
======================================================
Autonomous scaling controller for local containerized demo workloads.
Measures actual container CPU utilization, enforces sustained evaluation windows,
cooldown periods, min/max replica boundaries, and records every scaling decision.
"""
import os
import re
import time
import subprocess
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import urllib.request
import json


class AutoscalerConfig:
    def __init__(
        self,
        min_replicas: int = 1,
        max_replicas: int = 5,
        scale_out_threshold: float = 45.0,
        scale_in_threshold: float = 20.0,
        scale_out_cooldown: float = 15.0,
        scale_in_cooldown: float = 20.0,
        sustained_window_samples: int = 2,
        docker_host: str = "unix:///var/run/docker.sock",
        compose_file_path: Optional[str] = None,
        gateway_url: str = "http://127.0.0.1:8080",
    ):
        self.min_replicas = max(1, min_replicas)
        self.max_replicas = max(self.min_replicas, max_replicas)
        self.scale_out_threshold = scale_out_threshold
        self.scale_in_threshold = scale_in_threshold
        self.scale_out_cooldown = scale_out_cooldown
        self.scale_in_cooldown = scale_in_cooldown
        self.sustained_window_samples = max(1, sustained_window_samples)
        self.docker_host = docker_host
        self.compose_file_path = compose_file_path or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "autoscaling-lab", "docker-compose.yml")
        )
        self.gateway_url = gateway_url


class AutoscalingController:
    def __init__(self, config: Optional[AutoscalerConfig] = None):
        self.config = config or AutoscalerConfig()
        self.consecutive_high_samples = 0
        self.consecutive_low_samples = 0
        self.last_scale_time: Optional[float] = None
        self.last_scale_action: Optional[str] = None
        self.scaling_events: List[Dict[str, Any]] = []
        self.metric_history: List[Dict[str, Any]] = []
        self._mock_mode = False
        self._mock_replicas = 1
        self._mock_cpu = 10.0

    def get_remaining_cooldown(self) -> float:
        """Calculate remaining cooldown time in seconds."""
        if not self.last_scale_time:
            return 0.0
        elapsed = time.time() - self.last_scale_time
        required_cooldown = (
            self.config.scale_out_cooldown
            if self.last_scale_action == "SCALE_OUT"
            else self.config.scale_in_cooldown
        )
        return max(0.0, round(required_cooldown - elapsed, 1))

    def measure_container_metrics(self) -> Tuple[float, List[Dict[str, Any]], bool]:
        """
        Collect actual CPU metrics directly from docker stats for app replica containers.
        Returns: (average_cpu_percent, replicas_detail_list, is_healthy)
        """
        if self._mock_mode:
            detail = [
                {
                    "name": f"autoscaling-lab-app-{i+1}",
                    "cpu_percent": self._mock_cpu,
                    "memory": "32.0MiB / 15.35GiB",
                    "status": "Running",
                }
                for i in range(self._mock_replicas)
            ]
            return self._mock_cpu, detail, self.check_gateway_health()

        env = os.environ.copy()

        env["DOCKER_HOST"] = self.config.docker_host

        try:
            # Query actual container stats
            cmd = ["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"]
            res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                return 0.0, [], False

            replicas: List[Dict[str, Any]] = []
            cpu_values: List[float] = []

            for line in res.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.split("\t")
                if len(parts) >= 3:
                    name, cpu_str, mem = parts[0].strip(), parts[1].strip(), parts[2].strip()
                    # Match demo app containers
                    if "autoscaling-lab-app" in name or "smartcloud-autoscaling-app" in name:
                        clean_cpu = re.sub(r"[^\d.]", "", cpu_str)
                        try:
                            val = float(clean_cpu)
                        except ValueError:
                            val = 0.0
                        cpu_values.append(val)

                        # Parse Docker memory: '49.9MiB / 1GiB'
                        used_mb, limit_mb, mem_pct = 0.0, 0.0, 0.0
                        try:
                            mem_parts = mem.split("/")
                            if len(mem_parts) == 2:
                                def _to_mb(s: str) -> float:
                                    s = s.strip().lower()
                                    raw = float(re.sub(r"[^\d.]", "", s)) if re.sub(r"[^\d.]", "", s) else 0.0
                                    if "gib" in s:
                                        return raw * 1024.0
                                    elif "mib" in s:
                                        return raw
                                    elif "kib" in s:
                                        return raw / 1024.0
                                    elif "b" in s:
                                        return raw / (1024.0 * 1024.0)
                                    return raw
                                used_mb = round(_to_mb(mem_parts[0]), 2)
                                limit_mb = round(_to_mb(mem_parts[1]), 2)
                                mem_pct = round((used_mb / limit_mb * 100.0), 1) if limit_mb > 0 else 0.0
                        except Exception:
                            pass

                        replicas.append({
                            "name": name,
                            "cpu_percent": val,
                            "memory": mem,
                            "memory_used_mb": used_mb,
                            "memory_limit_mb": limit_mb,
                            "memory_percent": mem_pct,
                            "status": "Running",
                        })

            avg_cpu = round(sum(cpu_values) / len(cpu_values), 1) if cpu_values else 0.0

            # Health check via gateway
            is_healthy = self.check_gateway_health()

            return avg_cpu, replicas, is_healthy
        except Exception as e:
            return 0.0, [], False

    def check_gateway_health(self) -> bool:
        """Probe the load balancer health endpoint."""
        try:
            req = urllib.request.Request(f"{self.config.gateway_url}/health", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def get_current_replica_count(self, replicas_detail: List[Dict[str, Any]]) -> int:
        """Determine number of active running replicas."""
        if self._mock_mode:
            return self._mock_replicas
        return len(replicas_detail)

    def execute_docker_scale(self, target_replicas: int) -> bool:
        """
        Call docker compose to scale the app service, then actively verify
        that the running replica count reaches the target count.
        """
        target_replicas = max(self.config.min_replicas, min(self.config.max_replicas, target_replicas))

        if self._mock_mode:
            self._mock_replicas = target_replicas
            return True

        env = os.environ.copy()
        env["DOCKER_HOST"] = self.config.docker_host

        try:
            cmd = [
                "docker", "compose",
                "-f", self.config.compose_file_path,
                "up", "-d",
                "--scale", f"app={target_replicas}",
                "--no-recreate",
            ]
            res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=15)
            if res.returncode != 0:
                logger.error(f"Docker scale failed with returncode {res.returncode}: {res.stderr}")
                return False

            # Active post-scale verification: assert actual running replicas match target
            verified = False
            for _ in range(6):
                time.sleep(0.4)
                _, replicas, _ = self.measure_container_metrics()
                count = self.get_current_replica_count(replicas)
                if count == target_replicas:
                    verified = True
                    break

            if not verified:
                logger.warning(
                    f"Docker scale command succeeded but running count ({count}) "
                    f"did not converge to target ({target_replicas}) within verification window."
                )
            return verified
        except Exception as e:
            logger.error(f"Exception during docker scale: {e}")
            return False

    def evaluate_and_scale(self) -> Dict[str, Any]:
        """
        Core autoscaling loop iteration:
        Measures real CPU load, evaluates sustained windows and cooldowns,
        makes deterministic scaling decision, logs audit event, and returns current status.
        """
        avg_cpu, replicas_detail, is_healthy = self.measure_container_metrics()
        current_replicas = self.get_current_replica_count(replicas_detail)
        now_ts = datetime.now(timezone.utc).isoformat()
        remaining_cooldown = self.get_remaining_cooldown()

        decision = {
            "timestamp": now_ts,
            "measured_cpu_percent": avg_cpu,
            "previous_replicas": current_replicas,
            "new_replicas": current_replicas,
            "action": "MAINTAIN",
            "reason": f"Load {avg_cpu}% is within normal range [{self.config.scale_in_threshold}% - {self.config.scale_out_threshold}%].",
            "is_healthy": is_healthy,
        }

        # Check if gateway is unhealthy
        if not is_healthy and current_replicas > 0:
            decision["reason"] += " (Warning: Gateway health check did not return 200 OK)."

        # Scale-Out Condition
        if avg_cpu > self.config.scale_out_threshold:
            self.consecutive_high_samples += 1
            self.consecutive_low_samples = 0

            if self.consecutive_high_samples < self.config.sustained_window_samples:
                decision["action"] = "SUSTAINED_WINDOW_EVALUATING"
                decision["reason"] = (
                    f"Measured average CPU {avg_cpu}% exceeded scale-out threshold "
                    f"({self.config.scale_out_threshold}%). Evaluating sustained window: "
                    f"sample {self.consecutive_high_samples}/{self.config.sustained_window_samples}."
                )
            elif remaining_cooldown > 0:
                decision["action"] = "COOLDOWN_ACTIVE"
                decision["reason"] = (
                    f"Scale-out condition met ({avg_cpu}% CPU), but cooldown is active "
                    f"({remaining_cooldown}s remaining). Maintaining {current_replicas} replicas to prevent oscillation."
                )
            elif current_replicas >= self.config.max_replicas:
                decision["action"] = "MAX_REPLICAS_LIMIT"
                decision["reason"] = (
                    f"High load detected ({avg_cpu}% CPU), but workload is already at maximum "
                    f"replica ceiling ({self.config.max_replicas} replicas)."
                )
            else:
                # Determine scale-out increment: +2 if heavily overloaded (>75%), otherwise +1
                step = 2 if avg_cpu >= 75.0 and (current_replicas + 2 <= self.config.max_replicas) else 1
                target = min(self.config.max_replicas, current_replicas + step)
                success = self.execute_docker_scale(target)

                if success:
                    decision["action"] = "SCALE_OUT"
                    decision["new_replicas"] = target
                    decision["reason"] = (
                        f"Average CPU {avg_cpu}% sustained above threshold ({self.config.scale_out_threshold}%) "
                        f"for {self.config.sustained_window_samples} consecutive samples. "
                        f"Scaled out from {current_replicas} to {target} replicas."
                    )
                    self.last_scale_time = time.time()
                    self.last_scale_action = "SCALE_OUT"
                    self.consecutive_high_samples = 0
                else:
                    decision["action"] = "SCALE_ERROR"
                    decision["reason"] = f"Failed to execute docker scale command to {target} replicas."

        # Scale-In Condition
        elif avg_cpu < self.config.scale_in_threshold:
            self.consecutive_low_samples += 1
            self.consecutive_high_samples = 0

            if self.consecutive_low_samples < self.config.sustained_window_samples:
                decision["action"] = "SUSTAINED_WINDOW_EVALUATING"
                decision["reason"] = (
                    f"Measured average CPU {avg_cpu}% fell below scale-in threshold "
                    f"({self.config.scale_in_threshold}%). Evaluating sustained window: "
                    f"sample {self.consecutive_low_samples}/{self.config.sustained_window_samples}."
                )
            elif remaining_cooldown > 0:
                decision["action"] = "COOLDOWN_ACTIVE"
                decision["reason"] = (
                    f"Scale-in condition met ({avg_cpu}% CPU), but cooldown is active "
                    f"({remaining_cooldown}s remaining). Maintaining {current_replicas} replicas."
                )
            elif current_replicas <= self.config.min_replicas:
                decision["action"] = "MIN_REPLICAS_LIMIT"
                decision["reason"] = (
                    f"Workload is idle/low load ({avg_cpu}% CPU), but already at minimum "
                    f"replica floor ({self.config.min_replicas} replica)."
                )
            else:
                target = max(self.config.min_replicas, current_replicas - 1)
                success = self.execute_docker_scale(target)

                if success:
                    decision["action"] = "SCALE_IN"
                    decision["new_replicas"] = target
                    decision["reason"] = (
                        f"Average CPU {avg_cpu}% remained below scale-in threshold ({self.config.scale_in_threshold}%) "
                        f"for {self.config.sustained_window_samples} consecutive samples. "
                        f"Scaled in from {current_replicas} to {target} replicas."
                    )
                    self.last_scale_time = time.time()
                    self.last_scale_action = "SCALE_IN"
                    self.consecutive_low_samples = 0
                else:
                    decision["action"] = "SCALE_ERROR"
                    decision["reason"] = f"Failed to execute docker scale command to {target} replicas."

        else:
            # Stable operating window
            self.consecutive_high_samples = 0
            self.consecutive_low_samples = 0
            decision["action"] = "MAINTAIN"
            decision["reason"] = (
                f"Workload CPU {avg_cpu}% is within safe target envelope "
                f"({self.config.scale_in_threshold}% - {self.config.scale_out_threshold}%). "
                f"Maintaining {current_replicas} replicas."
            )

        if not is_healthy and current_replicas > 0:
            decision["reason"] += " (Warning: Gateway health check did not return 200 OK)."

        # Log decision
        self.scaling_events.insert(0, decision)

        if len(self.scaling_events) > 50:
            self.scaling_events.pop()

        # Record metric point
        metric_point = {
            "timestamp": now_ts,
            "average_cpu_percent": avg_cpu,
            "replicas_count": decision["new_replicas"],
            "is_healthy": is_healthy,
        }
        self.metric_history.append(metric_point)
        if len(self.metric_history) > 60:
            self.metric_history.pop(0)

        return {
            "status": "success",
            "timestamp": now_ts,
            "current_replicas": decision["new_replicas"],
            "target_replicas": decision["new_replicas"],
            "min_replicas": self.config.min_replicas,
            "max_replicas": self.config.max_replicas,
            "scale_out_threshold": self.config.scale_out_threshold,
            "scale_in_threshold": self.config.scale_in_threshold,
            "average_cpu_percent": avg_cpu,
            "replicas_detail": replicas_detail,
            "is_healthy": is_healthy,
            "remaining_cooldown_seconds": self.get_remaining_cooldown(),
            "last_action": decision["action"],
            "latest_decision": decision,
            "recent_events": self.scaling_events[:15],
            "metric_history": self.metric_history,
            "load_balancer_url": self.config.gateway_url,
        }
