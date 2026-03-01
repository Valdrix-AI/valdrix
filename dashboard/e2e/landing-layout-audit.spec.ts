import { expect, test } from '@playwright/test';

test.describe('Landing layout audit regressions', () => {
	test('does not trigger unresolved Supabase host errors on anonymous landing loads', async ({
		page
	}) => {
		const failedRequests: { url: string; reason: string }[] = [];
		const consoleErrors: string[] = [];

		page.on('requestfailed', (request) => {
			const failure = request.failure();
			failedRequests.push({
				url: request.url(),
				reason: failure?.errorText ?? 'unknown'
			});
		});

		page.on('console', (message) => {
			if (message.type() !== 'error') return;
			consoleErrors.push(message.text());
		});

		await page.goto('/');
		await page.waitForLoadState('networkidle');

		const supabaseDnsFailures = failedRequests.filter((entry) =>
			entry.url.includes('.supabase.co')
		);
		const unresolvedErrors = consoleErrors.filter((entry) =>
			/ERR_NAME_NOT_RESOLVED|dns/i.test(entry)
		);

		expect(supabaseDnsFailures).toEqual([]);
		expect(unresolvedErrors).toEqual([]);
	});

	test.describe('mobile viewport 390', () => {
		test.use({ viewport: { width: 390, height: 844 } });

		test('prevents horizontal overflow and keeps sr-only clipped', async ({ page }) => {
			await page.goto('/');
			await page.waitForLoadState('networkidle');

			const overflow = await page.evaluate(() => ({
				scrollWidth: document.documentElement.scrollWidth,
				viewportWidth: window.innerWidth
			}));
			expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.viewportWidth + 1);

			const srOnlyMetrics = await page.locator('#signal-map-summary').evaluate((element) => {
				const node = element as HTMLElement;
				const style = window.getComputedStyle(node);
				const rect = node.getBoundingClientRect();
				return {
					width: rect.width,
					height: rect.height,
					position: style.position,
					overflow: style.overflow,
					whiteSpace: style.whiteSpace
				};
			});

			expect(srOnlyMetrics.width).toBeLessThanOrEqual(2);
			expect(srOnlyMetrics.height).toBeLessThanOrEqual(2);
			expect(srOnlyMetrics.position).toBe('absolute');
			expect(srOnlyMetrics.overflow).toBe('hidden');
			expect(srOnlyMetrics.whiteSpace).toBe('nowrap');

			const switchOverflow = await page.locator('.landing-hook-switch').evaluate((element) => ({
				scrollWidth: element.scrollWidth,
				clientWidth: element.clientWidth
			}));
			expect(switchOverflow.scrollWidth).toBeLessThanOrEqual(switchOverflow.clientWidth + 1);

			const withValdricsToggle = page.getByRole('button', { name: /^With Valdrics$/i });
			await expect(withValdricsToggle).toBeVisible();
			const toggleBounds = await withValdricsToggle.boundingBox();
			expect(toggleBounds).not.toBeNull();
			if (toggleBounds) {
				expect(toggleBounds.x).toBeGreaterThanOrEqual(0);
				expect(toggleBounds.x + toggleBounds.width).toBeLessThanOrEqual(390);
			}
		});
	});

	test.describe('mobile viewport 500', () => {
		test.use({ viewport: { width: 500, height: 900 } });

		test('keeps header actions on-screen at mobile/tablet breakpoint', async ({ page }) => {
			await page.goto('/');
			await page.waitForLoadState('networkidle');

			const headerOverflow = await page.evaluate(() => ({
				scrollWidth: document.documentElement.scrollWidth,
				viewportWidth: window.innerWidth
			}));
			expect(headerOverflow.scrollWidth).toBeLessThanOrEqual(headerOverflow.viewportWidth + 1);

			const menuToggle = page.getByRole('button', { name: /toggle menu/i });
			await expect(menuToggle).toBeVisible();
			const toggleBounds = await menuToggle.boundingBox();
			expect(toggleBounds).not.toBeNull();
			if (toggleBounds) {
				expect(toggleBounds.x).toBeGreaterThanOrEqual(0);
				expect(toggleBounds.x + toggleBounds.width).toBeLessThanOrEqual(500);
			}

			await menuToggle.click();
			const mobileStartFree = page.locator('#public-mobile-menu a', { hasText: 'Start Free' });
			await expect(mobileStartFree).toBeVisible();
			const ctaBounds = await mobileStartFree.boundingBox();
			expect(ctaBounds).not.toBeNull();
			if (ctaBounds) {
				expect(ctaBounds.x).toBeGreaterThanOrEqual(0);
				expect(ctaBounds.x + ctaBounds.width).toBeLessThanOrEqual(500);
			}
		});
	});
});
