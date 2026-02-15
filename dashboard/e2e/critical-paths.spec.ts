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
		await expect(page.locator('text=Get Started')).toBeVisible();
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
		await expect(page.locator('text=Starter')).toBeVisible();
		await expect(page.locator('text=Growth')).toBeVisible();
		await expect(page.locator('text=Pro')).toBeVisible();
		await expect(page.locator('text=Enterprise')).toBeVisible();
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
	// Skip if no test credentials available
	test.skip(
		!process.env.TEST_EMAIL || !process.env.TEST_PASSWORD,
		'Requires TEST_EMAIL and TEST_PASSWORD env vars'
	);

	test.beforeEach(async ({ page }) => {
		// Login before each test
		await page.goto(`${BASE_URL}/auth/login`);
		await page.fill('input[type="email"]', process.env.TEST_EMAIL!);
		await page.fill('input[type="password"]', process.env.TEST_PASSWORD!);
		await page.click('button:has-text("Sign")');
		await waitForPageLoad(page);
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

		// Should show billing info or upgrade prompt
		const hasUpgrade = await page.locator('text=Upgrade').isVisible();
		const hasBilling = await page.locator('text=Billing').isVisible();

		expect(hasUpgrade || hasBilling).toBeTruthy();
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

		await expect(page.locator('h1:has-text("Cloud Accounts")')).toBeVisible();
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
		const apiUrl = process.env.API_URL || 'http://127.0.0.1:8000';

		const response = await request.get(`${apiUrl}/health`);
		expect(response.ok()).toBeTruthy();

		const body = await response.json();
		expect(['healthy', 'degraded']).toContain(body.status);
	});
});
