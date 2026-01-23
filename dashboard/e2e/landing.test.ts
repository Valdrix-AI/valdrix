import { expect, test } from '@playwright/test';

test.describe('Landing Page Content', () => {
	test.beforeEach(async ({ page }) => {
		await page.goto('/');
	});

	test('should display correct value proposition', async ({ page }) => {
		const headingContent = page.locator('p', {
			hasText: 'A FinOps engine that continuously optimizes cloud value'
		});
		await expect(headingContent).toBeVisible();
	});

	test('should display value optimizer message in chart section', async ({ page }) => {
		// The user added "Value Optimizer: Continuously eliminating waste and technical debt."
		const efficiencyMessage = page.getByText(
			'Value Optimizer: Continuously eliminating waste and technical debt.'
		);
		await expect(efficiencyMessage).toBeVisible();
	});

	test('should have a functional CTA button', async ({ page }) => {
		const ctaBtn = page.getByRole('button', { name: /Connect AWS/i });
		await expect(ctaBtn).toBeVisible();
	});
});
