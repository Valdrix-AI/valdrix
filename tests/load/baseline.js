/**
 * K6 Load Testing Suite
 * 
 * Tests API performance and capacity limits.
 * Run: k6 run tests/load/baseline.js
 * 
 * Scenarios:
 * - Smoke: 1 VU, 30s (sanity check)
 * - Load: 50 VUs, 5min (normal traffic)
 * - Stress: 100 VUs, 3min (peak capacity)
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const analysisTime = new Trend('analysis_time');

// Configuration
const BASE_URL = __ENV.API_URL || 'http://localhost:8000';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';

// Test scenarios
export const options = {
    scenarios: {
        // Smoke test - verify basic functionality
        smoke: {
            executor: 'constant-vus',
            vus: 1,
            duration: '30s',
            startTime: '0s',
            tags: { test_type: 'smoke' },
        },
        // Load test - typical production load
        load: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '1m', target: 25 },   // Ramp up
                { duration: '3m', target: 50 },   // Hold at 50
                { duration: '1m', target: 0 },    // Ramp down
            ],
            startTime: '30s',
            tags: { test_type: 'load' },
        },
        // Stress test - find breaking point
        stress: {
            executor: 'ramping-vus',
            startVUs: 0,
            stages: [
                { duration: '30s', target: 50 },
                { duration: '1m', target: 100 },
                { duration: '30s', target: 100 },
                { duration: '1m', target: 0 },
            ],
            startTime: '6m',
            tags: { test_type: 'stress' },
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<500', 'p(99)<1000'],  // 95% under 500ms
        errors: ['rate<0.01'],                            // <1% error rate
        analysis_time: ['p(95)<3000'],                    // Analysis under 3s
    },
};

// Request headers
const headers = {
    'Content-Type': 'application/json',
    'Authorization': AUTH_TOKEN ? `Bearer ${AUTH_TOKEN}` : '',
};

export default function() {
    group('Health Check', function() {
        const res = http.get(`${BASE_URL}/health`, { headers });
        check(res, {
            'health status is 200': (r) => r.status === 200,
            'health response has status': (r) => r.json('status') !== undefined,
        });
        errorRate.add(res.status !== 200);
    });

    group('Job Queue Status', function() {
        const res = http.get(`${BASE_URL}/jobs/status`, { headers });
        check(res, {
            'jobs status is 200': (r) => r.status === 200 || r.status === 401,
        });
    });

    group('Usage Metrics', function() {
        const res = http.get(`${BASE_URL}/usage`, { headers });
        check(res, {
            'usage returns data or auth error': (r) => r.status === 200 || r.status === 401,
        });
    });

    // Simulate authenticated user flow
    if (AUTH_TOKEN) {
        group('Cost API', function() {
            const start = Date.now();
            const res = http.get(`${BASE_URL}/costs`, { headers });
            check(res, {
                'costs status is 200': (r) => r.status === 200,
            });
            errorRate.add(res.status !== 200);
            analysisTime.add(Date.now() - start);
        });

        group('Zombie Resources', function() {
            const res = http.get(`${BASE_URL}/zombies`, { headers });
            check(res, {
                'zombies status is 200': (r) => r.status === 200,
            });
        });
    }

    sleep(1);
}

// Setup function - runs once before test
export function setup() {
    console.log(`Testing ${BASE_URL}`);
    console.log(`Auth configured: ${!!AUTH_TOKEN}`);
    
    // Verify API is reachable
    const res = http.get(`${BASE_URL}/health`);
    if (res.status !== 200) {
        throw new Error(`API not reachable: ${res.status}`);
    }
    
    return { startTime: Date.now() };
}

// Teardown function - runs once after test
export function teardown(data) {
    const duration = (Date.now() - data.startTime) / 1000;
    console.log(`Test completed in ${duration}s`);
}
