"""
Valdrix Load Test - Locust

Run: locust -f loadtest/locustfile.py --host=http://localhost:8000
Web UI: http://localhost:8089
"""

from locust import HttpUser, task, between, tag
import random


import os

class ValdrixUser(HttpUser):
    """Simulates a typical Valdrix dashboard user."""
    
    wait_time = between(1, 5)  # Think time between requests
    
    def on_start(self):
        """Called when a user starts - setup auth."""
        self.token = os.getenv("LOADTEST_TOKEN", "test-bearer-token")
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    @task(3)
    @tag("critical", "health")
    def health_check(self):
        """Health endpoint - high frequency."""
        with self.client.get("/health", catch_response=True) as response:
            if response.status_code == 200:
                data = response.json()
                if data.get("status") != "healthy":
                    response.failure("Health check returned unhealthy status")
            else:
                response.failure(f"Health check failed: {response.status_code}")
    
    @task(5)
    @tag("core", "savings")
    def get_savings_summary(self):
        """Main savings summary - most common API call."""
        # Fixed: /api/v1/savings/summary -> /api/v1/costs (valid endpoint)
        self.client.get("/api/v1/costs", headers=self.headers)
    
    @task(4)
    @tag("core", "zombies")
    def list_zombies(self):
        """List zombie resources with pagination."""
        page = random.randint(1, 5)
        self.client.get(
            f"/api/v1/zombies?page={page}&per_page=20",
            headers=self.headers,
            name="/api/v1/zombies?page=[N]"
        )
    
    @task(3)
    @tag("core", "connections")
    def list_connections(self):
        """List cloud connections."""
        self.client.get("/api/v1/connections", headers=self.headers)
    
    @task(2)
    @tag("reporting")
    def get_carbon_report(self):
        """Carbon footprint report."""
        # Fixed: /api/v1/reports/carbon -> /api/v1/carbon
        self.client.get("/api/v1/carbon", headers=self.headers)
    
    @task(1)
    @tag("analytics")
    def get_forecast(self):
        """Cost forecast - less frequent, heavier endpoint."""
        # Fixed: /api/v1/forecast -> /api/v1/costs/forecast
        self.client.get("/api/v1/costs/forecast?days=30", headers=self.headers)


class AdminUser(HttpUser):
    """Simulates admin user doing management tasks."""
    
    wait_time = between(5, 15)  # Admins are slower
    weight = 1  # 1:10 ratio vs regular users
    
    def on_start(self):
        token = os.getenv("ADMIN_TOKEN", "admin-token")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    
    @task(2)
    @tag("admin")
    def list_tenants(self):
        """Admin: list all tenants."""
        self.client.get("/api/v1/admin/tenants", headers=self.headers)
    
    @task(1)
    @tag("admin", "audit")
    def get_audit_logs(self):
        """Admin: fetch audit logs."""
        self.client.get("/api/v1/admin/audit?limit=50", headers=self.headers)


class APIUser(HttpUser):
    """Simulates programmatic API access (CI/CD, scripts)."""
    
    wait_time = between(0.1, 0.5)  # Fast, automated
    weight = 2
    
    @task
    @tag("api")
    def bulk_zombie_check(self):
        """API: bulk check for zombies."""
        api_key = os.getenv("API_TOKEN", "api-key")
        self.client.get(
            "/api/v1/zombies?per_page=100",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
        )
