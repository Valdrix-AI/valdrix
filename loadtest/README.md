# Load Testing for Valdrix

## k6 (Recommended for CI/CD)

### Installation
```bash
# macOS
brew install k6

# Linux
sudo gpg --no-default-keyring --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update && sudo apt-get install k6
```

### Run Tests
```bash
# Basic run
k6 run loadtest/k6-test.js

# With custom options
k6 run --vus 50 --duration 5m loadtest/k6-test.js

# Against production
BASE_URL=https://api.valdrix.io k6 run loadtest/k6-test.js
```

---

## Locust (Recommended for exploratory testing)

### Installation
```bash
pip install locust
```

### Run Tests
```bash
# Start with Web UI
locust -f loadtest/locustfile.py --host=http://localhost:8000

# Headless mode
locust -f loadtest/locustfile.py --host=http://localhost:8000 \
  --headless -u 100 -r 10 --run-time 5m
```

Access Web UI at: http://localhost:8089

---

## Performance Targets

| Metric | Target | Critical |
|---|---|---|
| p95 Latency | < 500ms | < 1500ms |
| Error Rate | < 1% | < 5% |
| Throughput | > 100 RPS | > 50 RPS |

---

## CI/CD Integration

Add to GitHub Actions:
```yaml
- name: Run Load Test
  run: |
    k6 run --out json=results.json loadtest/k6-test.js
    
- name: Check Thresholds
  run: |
    if grep -q '"thresholds":{".*":{"ok":false' results.json; then
      echo "Load test failed!"
      exit 1
    fi
```
