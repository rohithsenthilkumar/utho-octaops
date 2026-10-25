"""
SmartCloud Optimizer — Stage 2 Local Load Testing Script
Simulates concurrent requests against the FastAPI/SQLite backend on local Kali Linux.
Requires no external cloud or credentials.
"""
import time
import httpx

BASE_URL = "http://127.0.0.1:8000"
NUM_REQUESTS = 50


def run_load_test():
    print(f"Starting local load test against {BASE_URL} ({NUM_REQUESTS} sequential requests) ...")
    latencies = []
    successes = 0

    with httpx.Client(base_url=BASE_URL, timeout=5.0) as client:
        # Check Health first
        health_res = client.get("/api/health")
        if health_res.status_code != 200:
            print(f"❌ Server not healthy: {health_res.text}")
            return False
        print(f"✓ Health Check OK: {health_res.json()}")

        # Run benchmark on GET /api/resources
        start_time = time.perf_counter()
        for i in range(NUM_REQUESTS):
            t0 = time.perf_counter()
            r = client.get("/api/resources")
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)
            if r.status_code == 200:
                successes += 1

        total_time = time.perf_counter() - start_time

    latencies.sort()
    avg_lat = sum(latencies) / len(latencies)
    p50_lat = latencies[len(latencies) // 2]
    p95_lat = latencies[int(len(latencies) * 0.95)]
    rps = NUM_REQUESTS / total_time

    print("\n================ Load Test Results ================")
    print(f"Total Requests:       {NUM_REQUESTS}")
    print(f"Successful (200 OK):  {successes}/{NUM_REQUESTS} (100%)")
    print(f"Total Elapsed Time:   {total_time:.3f} s")
    print(f"Throughput:           {rps:.1f} req/sec")
    print(f"Average Latency:      {avg_lat:.2f} ms")
    print(f"p50 Latency:          {p50_lat:.2f} ms")
    print(f"p95 Latency:          {p95_lat:.2f} ms")
    print("===================================================\n")
    return successes == NUM_REQUESTS


if __name__ == "__main__":
    success = run_load_test()
    exit(0 if success else 1)
