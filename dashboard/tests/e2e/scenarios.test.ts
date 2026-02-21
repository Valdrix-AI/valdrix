import { test, expect } from '@playwright/test';

const E2E_AUTH_HEADER_NAME = 'x-valdrix-e2e-auth';
const E2E_AUTH_HEADER_VALUE = process.env.E2E_AUTH_SECRET || 'playwright';

test.describe('Authentication Flow', () => {
	test('shows landing page when not authenticated', async ({ page }) => {
		await page.goto('/');
		await expect(page.locator('h1')).toContainText(/Cloud Cost Intelligence/i);
	});

	test('shows sign in button on login page', async ({ page }) => {
		await page.goto('/auth/login');
		await expect(page.getByRole('button', { name: /Sign in/i })).toBeVisible();
	});
});

test.describe('Route Guards', () => {
	test('redirects unauthenticated user from settings to login', async ({ page }) => {
		await page.goto('/settings');
		await expect(page).toHaveURL(/\/auth\/login/);
	});
});

test.describe('Authenticated Route Access (test-mode)', () => {
	test.beforeEach(async ({ page }) => {
		await page.context().setExtraHTTPHeaders({
			[E2E_AUTH_HEADER_NAME]: E2E_AUTH_HEADER_VALUE
		});
	});

	test('loads dashboard shell with authenticated heading', async ({ page }) => {
		await page.goto('/');
		await expect(page.locator('h1')).toContainText(/Dashboard/i);
	});

	test('loads settings page when test auth header is set', async ({ page }) => {
		await page.goto('/settings');
		await expect(page).toHaveURL(/\/settings$/);
		await expect(page.locator('h1')).toContainText('Preferences');
	});
});
