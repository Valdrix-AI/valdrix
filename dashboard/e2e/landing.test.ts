import { expect, test } from '@playwright/test';

test.describe('Landing Page Content', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/');
	});

	test('should display correct value proposition', async ({ page }) => {
		await expect(
			page.getByRole('heading', {
				level: 1,
				name: /stop cloud and software waste|control every dollar|control cloud margin risk/i
			})
		).toBeVisible();
		await expect(page.getByRole('heading', { name: /realtime spend scenario simulator/i })).toBeVisible();
	});

	test('should have a functional CTA button', async ({ page }) => {
		const ctaLink = page.getByRole('link', { name: /Start Free|Book Executive Briefing/i }).first();
		await expect(ctaLink).toBeVisible();
	});
});
