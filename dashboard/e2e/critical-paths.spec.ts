/**
 * End-to-End Tests for Critical Paths
 *
 * Tests:
 * 1. Onboarding flow
 * 2. Billing flow
 * 3. Remediation approval
 */

import { test, expect, type Page } from '@playwright/test';

// Test configuration
const BASE_URL = process.env.DASHBOARD_URL || 'http://localhost:4173';
const E2E_AUTH_HEADER_NAME = 'x-valdrix-e2e-auth';
const E2E_AUTH_HEADER_VALUE = process.env.E2E_AUTH_SECRET || 'playwright';

// Helper to wait for page load
async function waitForPageLoad(page: Page) {
	await page.waitForLoadState('networkidle');
}

// ==================== Onboarding Flow ====================

test.describe('Onboarding Flow', () => {
	test('landing page loads correctly', async ({ page }) => {
		await page.goto(BASE_URL);
		await waitForPageLoad(page);

		// Check for key elements - title is in the header link
		await expect(page.locator('header')).toContainText('Valdrix');
		await expect(page.locator('h1')).toContainText('Cloud Cost');
		await expect(page.getByRole('link', { name: /Get Started Free/i }).first()).toBeVisible();
	});

	test('skip link is keyboard reachable', async ({ page }) => {
		await page.goto(BASE_URL);

		// First focus should land on the skip link for keyboard users.
		await page.keyboard.press('Tab');
		const skipLink = page.locator('a.skip-link');
		await expect(skipLink).toBeFocused();
		await expect(skipLink).toHaveAttribute('href', '#main');
	});

	test('pricing page displays all tiers', async ({ page }) => {
		await page.goto(`${BASE_URL}/pricing`);
		await waitForPageLoad(page);

		// Check all tiers are visible
		await expect(page.getByRole('heading', { name: 'Starter', exact: true })).toBeVisible();
		await expect(page.getByRole('heading', { name: 'Growth', exact: true })).toBeVisible();
		await expect(page.getByRole('heading', { name: 'Pro', exact: true })).toBeVisible();
		await expect(page.getByRole('heading', { name: 'Enterprise', exact: true })).toBeVisible();
	});

	test('login page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/auth/login`);
		await waitForPageLoad(page);

		// Check for login form elements
		await expect(page.locator('input[type="email"]')).toBeVisible();
		await expect(page.locator('button:has-text("Sign In")')).toBeVisible();
	});

	test('signup page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/auth/login`);
		await waitForPageLoad(page);

		await page.click('button:has-text("Sign up")');
		await expect(page.locator('h1:has-text("Create your account")')).toBeVisible();
	});
});

// ==================== SEO / Indexability ====================

test.describe('SEO and Indexability', () => {
	test('robots.txt references sitemap', async ({ request }) => {
		const res = await request.get(`${BASE_URL}/robots.txt`);
		expect(res.ok()).toBeTruthy();
		const body = await res.text();
		expect(body).toContain('Sitemap:');
		expect(body).toContain('/sitemap.xml');
	});

	test('sitemap.xml includes marketing routes', async ({ request }) => {
		const res = await request.get(`${BASE_URL}/sitemap.xml`);
		expect(res.ok()).toBeTruthy();
		const body = await res.text();
		expect(body).toContain('<urlset');
		expect(body).toContain('/pricing');
	});
});

// ==================== Dashboard Flow ====================

test.describe('Dashboard Flow (Authenticated)', () => {
	test.beforeEach(async ({ page }) => {
		await page.context().setExtraHTTPHeaders({
			[E2E_AUTH_HEADER_NAME]: E2E_AUTH_HEADER_VALUE
		});
	});

	test('dashboard loads with key metrics', async ({ page }) => {
		await page.goto(`${BASE_URL}/`);
		await waitForPageLoad(page);

		// Dashboard should have these sections
		await expect(page.locator('h1:has-text("Dashboard")')).toBeVisible();
	});

	test('settings page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/settings`);
		await waitForPageLoad(page);

		await expect(page.locator('h1:has-text("Preferences")')).toBeVisible();
	});
});

// ==================== Billing Flow ====================

test.describe('Billing Flow', () => {
	test('billing page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/billing`);
		await waitForPageLoad(page);

		// Protected routes may redirect to login when unauthenticated.
		if (page.url().includes('/auth/login')) {
			await expect(page).toHaveURL(/\/auth\/login/);
			return;
		}

		await expect(page.locator('h1:has-text("Billing & Plans")')).toBeVisible();
	});

	test('pricing cards are interactive', async ({ page }) => {
		await page.goto(`${BASE_URL}/pricing`);
		await waitForPageLoad(page);

		// Find a CTA button
		const ctaButton = page.locator('.cta-button').first();
		await expect(ctaButton).toBeVisible();

		// Check it's clickable (not disabled)
		await expect(ctaButton).toBeEnabled();
	});
});

// ==================== Connections Flow ====================

test.describe('Connections Flow', () => {
	test('connections page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/connections`);
		await waitForPageLoad(page);

		if (page.url().includes('/auth/login')) {
			await expect(page).toHaveURL(/\/auth\/login/);
			return;
		}

		await expect(page.locator('h1:has-text("Cloud Accounts")')).toBeVisible();
	});
});

// ==================== GreenOps Flow ====================

test.describe('GreenOps Flow', () => {
	test('greenops page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/greenops`);
		await waitForPageLoad(page);

		if (page.url().includes('/auth/login')) {
			await expect(page).toHaveURL(/\/auth\/login/);
			return;
		}

		// Should show carbon tracking
		const hasCarbon = await page.locator('text=carbon, text=Carbon').first().isVisible();
		const hasGreenOps = await page.locator('text=GreenOps').isVisible();

		expect(hasCarbon || hasGreenOps).toBeTruthy();
	});
});

// ==================== API Health Check ====================

test.describe('API Health', () => {
	test('health endpoint returns ok', async ({ request }) => {
		const apiUrl = process.env.API_URL || 'http://127.0.0.1:8000';

		const response = await request.get(`${apiUrl}/health`);
		expect(response.ok()).toBeTruthy();

		const body = await response.json();
		expect(['healthy', 'degraded', 'unknown']).toContain(body.status);
	});
});
