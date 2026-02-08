/**
 * Valdrix Load Test - k6
 * 
 * Run: k6 run loadtest/k6-test.js
 * With options: k6 run --vus 50 --duration 5m loadtest/k6-test.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const apiLatency = new Trend('api_latency');

// Test configuration
export const options = {
  stages: [
    { duration: '1m', target: 10 },   // Ramp up
    { duration: '3m', target: 50 },   // Sustained load
    { duration: '2m', target: 100 },  // Peak load
    { duration: '1m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1500'],
    http_req_failed: ['rate<0.01'],
    errors: ['rate<0.05'],
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

// Test data
const testTenantId = 'test-tenant-001';

export function setup() {
  // Health check before starting
  const res = http.get(`${BASE_URL}/health`);
  check(res, { 'API is healthy': (r) => r.status === 200 });
  return { token: __ENV.LOADTEST_TOKEN || 'test-bearer-token' };
}

export default function(data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.token}`,
  };

  // 1. Health Check (20%)
  if (Math.random() < 0.2) {
    const start = Date.now();
    const res = http.get(`${BASE_URL}/health`);
    apiLatency.add(Date.now() - start);
    
    const success = check(res, {
      'health status is 200': (r) => r.status === 200,
      'health response is OK': (r) => r.json('status') === 'healthy',
    });
    errorRate.add(!success);
  }

  // 2. Get Savings Summary (30%)
  if (Math.random() < 0.3) {
    const start = Date.now();
    // Fixed: /api/v1/savings/summary -> /api/v1/costs
    const res = http.get(`${BASE_URL}/api/v1/costs`, { headers });
    apiLatency.add(Date.now() - start);
    
    const success = check(res, {
      'savings status is 200': (r) => r.status === 200,
      'savings has data': (r) => r.json('total_savings') !== undefined,
    });
    errorRate.add(!success);
  }

  // 3. List Zombies (30%)
  if (Math.random() < 0.3) {
    const start = Date.now();
    const res = http.get(`${BASE_URL}/api/v1/zombies?page=1&per_page=20`, { headers });
    apiLatency.add(Date.now() - start);
    
    const success = check(res, {
      'zombies status is 200': (r) => r.status === 200,
      'zombies has items': (r) => Array.isArray(r.json('items')),
    });
    errorRate.add(!success);
  }

  // 4. Get Connections (20%)
  if (Math.random() < 0.2) {
    const start = Date.now();
    const res = http.get(`${BASE_URL}/api/v1/connections`, { headers });
    apiLatency.add(Date.now() - start);
    
    const success = check(res, {
      'connections status is 200': (r) => r.status === 200,
    });
    errorRate.add(!success);
  }

  sleep(Math.random() * 2 + 0.5); // Random 0.5-2.5s think time
}

export function teardown(data) {
  console.log('Load test completed');
}
