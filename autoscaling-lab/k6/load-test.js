import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';

export const replicaCounter = new Counter('replica_responses');

export const options = {
  scenarios: {
    autoscaling_lifecycle: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        // 1. Low-load baseline: 2 VUs for 6s (CPU ~10-20%)
        { duration: '6s', target: 2 },
        // 2. Ramp-up: Rapid surge to 25 VUs over 8s (CPU climbs > 50%)
        { duration: '8s', target: 25 },
        // 3. Sustained-high-load: 25 VUs for 15s (Sustained overload triggers scale-out to 2-3 replicas)
        { duration: '15s', target: 25 },
        // 4. Ramp-down: Decrease to 2 VUs over 8s (CPU drops < 20%)
        { duration: '8s', target: 2 },
        // 5. Cooldown baseline: 1 VU for 8s (Low load allows scale-in)
        { duration: '8s', target: 1 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.05'], // < 5% failures allowed
    http_req_duration: ['p(95)<3000'], // P95 latency under 3s
  },
};

const BASE_URL = __ENV.TARGET_URL || 'http://127.0.0.1:8080';

export default function () {
  // Call workload endpoint which performs deterministic CPU calculations
  const res = http.get(`${BASE_URL}/work?iterations=35000`);

  check(res, {
    'status is 200': (r) => r.status === 200,
    'has replica header': (r) => r.headers['X-Replica-Id'] !== undefined,
    'handled by identified replica': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body && body.replica_id !== undefined;
      } catch (e) {
        return false;
      }
    },
  });

  const replicaId = res.headers['X-Replica-Id'] || 'unknown';
  replicaCounter.add(1, { replica: replicaId });

  sleep(0.05);
}
