"""
SmartCloud Optimizer — Stage 5 Demo Workload Application
========================================================
Lightweight containerized web service for local autoscaling demonstration.
Provides health endpoints, replica identification headers, and a CPU-intensive
workload endpoint for load testing.
"""
import os
import time
import hashlib
from fastapi import FastAPI, Response, Query

app = FastAPI(title="SmartCloud Autoscaling Demo Workload", version="1.0.0")

HOSTNAME = os.environ.get("HOSTNAME", "replica-unknown")
START_TIME = time.time()


@app.middleware("http")
async def add_replica_identity_headers(request, call_next):
    """Stamp each HTTP response with the identity of the replica container that handled it."""
    response: Response = await call_next(request)
    response.headers["X-Replica-Id"] = HOSTNAME
    response.headers["X-Handled-By"] = f"replica-{HOSTNAME}"
    response.headers["Server-Timing"] = f"replica;desc=\"{HOSTNAME}\""
    return response


@app.get("/")
def root():
    """Service status and replica info."""
    return {
        "service": "smartcloud-autoscaling-demo",
        "replica_id": HOSTNAME,
        "handled_by": f"replica-{HOSTNAME}",
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }


@app.get("/health")
def health():
    """Health check endpoint identifying the active replica."""
    return {
        "status": "healthy",
        "replica_id": HOSTNAME,
        "uptime_seconds": round(time.time() - START_TIME, 1),
    }


@app.get("/work")
def compute_work(iterations: int = Query(35000, ge=1000, le=500000)):
    """
    Simulates real-world application request processing with deterministic CPU work.
    Used by k6 to generate realistic container CPU load.
    """
    t0 = time.perf_counter()
    data = b"smartcloud-optimization-benchmark-seed"
    for _ in range(iterations):
        data = hashlib.sha256(data).digest()
    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)

    return {
        "status": "processed",
        "replica_id": HOSTNAME,
        "handled_by": f"replica-{HOSTNAME}",
        "iterations": iterations,
        "elapsed_ms": elapsed_ms,
    }
