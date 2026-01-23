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
const BASE_URL = process.env.DASHBOARD_URL || 'http://localhost:5173';

// Helper to wait for page load
async function waitForPageLoad(page: Page) {
	await page.waitForLoadState('networkidle');
}

// ==================== Onboarding Flow ====================

test.describe('Onboarding Flow', () => {
	test('landing page loads correctly', async ({ page }) => {
		await page.goto(BASE_URL);
		await waitForPageLoad(page);

		// Check for key elements
		await expect(page.locator('h1')).toContainText('Valdrix');
		await expect(page.locator('text=Get Started')).toBeVisible();
		await expect(page.locator('text=Features')).toBeVisible();
	});

	test('pricing page displays all tiers', async ({ page }) => {
		await page.goto(`${BASE_URL}/pricing`);
		await waitForPageLoad(page);

		// Check all tiers are visible
		await expect(page.locator('text=Starter')).toBeVisible();
		await expect(page.locator('text=Growth')).toBeVisible();
		await expect(page.locator('text=Pro')).toBeVisible();
		await expect(page.locator('text=Enterprise')).toBeVisible();
	});

	test('login page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/login`);
		await waitForPageLoad(page);

		// Check for login form elements
		await expect(page.locator('input[type="email"]')).toBeVisible();
		await expect(page.locator('button:has-text("Sign")')).toBeVisible();
	});

	test('signup page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/signup`);
		await waitForPageLoad(page);

		// Check for signup form
		await expect(page.locator('input[type="email"]')).toBeVisible();
	});
});

// ==================== Dashboard Flow ====================

test.describe('Dashboard Flow (Authenticated)', () => {
	// Skip if no test credentials available
	test.skip(
		!process.env.TEST_EMAIL || !process.env.TEST_PASSWORD,
		'Requires TEST_EMAIL and TEST_PASSWORD env vars'
	);

	test.beforeEach(async ({ page }) => {
		// Login before each test
		await page.goto(`${BASE_URL}/login`);
		await page.fill('input[type="email"]', process.env.TEST_EMAIL!);
		await page.fill('input[type="password"]', process.env.TEST_PASSWORD!);
		await page.click('button:has-text("Sign")');
		await waitForPageLoad(page);
	});

	test('dashboard loads with key metrics', async ({ page }) => {
		await page.goto(`${BASE_URL}/dashboard`);
		await waitForPageLoad(page);

		// Dashboard should have these sections
		await expect(page.locator('text=Overview')).toBeVisible();
	});

	test('settings page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/settings`);
		await waitForPageLoad(page);

		await expect(page.locator('h1:has-text("Settings")')).toBeVisible();
	});
});

// ==================== Billing Flow ====================

test.describe('Billing Flow', () => {
	test('billing page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/billing`);
		await waitForPageLoad(page);

		// Should show billing info or upgrade prompt
		const hasUpgrade = await page.locator('text=Upgrade').isVisible();
		const hasBilling = await page.locator('text=Billing').isVisible();

		expect(hasUpgrade || hasBilling).toBeTruthy();
	});

	test('pricing cards are interactive', async ({ page }) => {
		await page.goto(`${BASE_URL}/pricing`);
		await waitForPageLoad(page);

		// Find a CTA button
		const ctaButton = page
			.locator('button:has-text("Get Started"), a:has-text("Get Started")')
			.first();
		await expect(ctaButton).toBeVisible();

		// Check it's clickable (not disabled)
		await expect(ctaButton).toBeEnabled();
	});
});

// ==================== Zombie Resources Flow ====================

test.describe('Zombie Resources Flow', () => {
	test('zombies page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/zombies`);
		await waitForPageLoad(page);

		// Should show zombie resources section
		await expect(page.locator('h1, h2').filter({ hasText: /zombie|resource/i })).toBeVisible();
	});
});

// ==================== GreenOps Flow ====================

test.describe('GreenOps Flow', () => {
	test('greenops page loads', async ({ page }) => {
		await page.goto(`${BASE_URL}/greenops`);
		await waitForPageLoad(page);

		// Should show carbon tracking
		const hasCarbon = await page.locator('text=carbon, text=Carbon').first().isVisible();
		const hasGreenOps = await page.locator('text=GreenOps').isVisible();

		expect(hasCarbon || hasGreenOps).toBeTruthy();
	});
});

// ==================== API Health Check ====================

test.describe('API Health', () => {
	test('health endpoint returns ok', async ({ request }) => {
		const apiUrl = process.env.API_URL || 'http://localhost:8000';

		const response = await request.get(`${apiUrl}/health`);
		expect(response.ok()).toBeTruthy();

		const body = await response.json();
		expect(body.status).toBe('active');
	});
});
