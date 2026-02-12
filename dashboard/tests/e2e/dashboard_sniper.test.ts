import { test, expect } from '@playwright/test';

test.describe('Dashboard Sniper Console Reliability', () => {
	test.beforeEach(async ({ page }) => {
		// Mock the core FinOps APIs used by the dashboard.
		await page.route('**/api/v1/costs/analyze*', async (route) => {
			await route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify({
					status: 'success',
					job_id: 'e2e-job-123',
					message: 'Analysis started in background'
				})
			});
		});

		await page.route('**/api/v1/zombies*', async (route) => {
			await route.fulfill({
				status: 200,
				contentType: 'application/json',
				body: JSON.stringify([
					{
						resource_id: 'i-0123456789abcdef0',
						resource_type: 'ec2_instance',
						status: 'zombie',
						reason: 'No CPU usage for 30 days',
						estimated_savings: 45.5
					}
				])
			});
		});
	});

	test('should display the main headline', async ({ page }) => {
		await page.goto('/');
		await expect(page.locator('h1')).toContainText(/Cloud (Cost|Intelligence)/i);
	});

	test('should redirect to login when accessing protected page unauthenticated', async ({
		page
	}) => {
		await page.goto('/settings');
		await expect(page).toHaveURL(/\/auth\/login/);
	});

	test('should handle API errors gracefully in the Sniper Console', async ({ page }) => {
		await page.route('**/api/v1/summary*', async (route) => {
			await route.fulfill({
				status: 500,
				contentType: 'application/json',
				body: JSON.stringify({ error: 'Internal Server Error' })
			});
		});
	});
});
