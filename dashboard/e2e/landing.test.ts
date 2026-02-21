import { expect, test } from '@playwright/test';

test.describe('Landing Page Content', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/');
	});

	test('should display correct value proposition', async ({ page }) => {
		const headingContent = page.locator('p', {
			hasText: 'Unify spend, carbon, and risk into a single signal map'
		});
		await expect(headingContent).toBeVisible();
	});

	test('should have a functional CTA button', async ({ page }) => {
		const ctaLink = page.getByRole('link', { name: /Get Started Free/i }).first();
		await expect(ctaLink).toBeVisible();
	});
});
