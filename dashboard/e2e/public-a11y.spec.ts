import { expect, test } from '@playwright/test';
import { getViolations, injectAxe } from 'axe-playwright';

const BLOCKING_IMPACTS = new Set(['critical', 'serious']);

type PublicRoute = {
	path: string;
	mainHeading?: RegExp;
};

const PUBLIC_ROUTES: readonly PublicRoute[] = [
	{ path: '/', mainHeading: /control|waste|margin risk/i },
	{ path: '/docs/technical-validation', mainHeading: /public capability validation summary/i },
	{ path: '/pricing' },
	{ path: '/auth/login' },
	{ path: '/privacy' },
	{ path: '/terms' }
] as const;

async function assertNoBlockingViolations(page: Parameters<typeof test>[0]['page']) {
	await injectAxe(page);
	const violations = await getViolations(page);
	const blocking = violations.filter((violation) =>
		BLOCKING_IMPACTS.has((violation.impact || '').toLowerCase())
	);
	const summary = blocking.map((violation) => ({
		id: violation.id,
		impact: violation.impact,
		help: violation.help,
		nodes: violation.nodes.map((node) => ({
			target: node.target,
			failureSummary: node.failureSummary
		}))
	}));
	expect(blocking, JSON.stringify(summary, null, 2)).toEqual([]);
}

test.describe('Public Accessibility Gate', () => {
	for (const routeCase of PUBLIC_ROUTES) {
		test(`${routeCase.path} has no critical/serious axe violations`, async ({ page }) => {
			await page.goto(routeCase.path);
			await page.waitForLoadState('networkidle');
			await expect(page.locator('main')).toHaveCount(1);
			if (routeCase.mainHeading) {
				await expect(page.getByRole('heading', { level: 1, name: routeCase.mainHeading })).toBeVisible();
			}
			await page.keyboard.press('Tab');
			const focusedTag = await page.evaluate(() => document.activeElement?.tagName || 'UNKNOWN');
			expect(focusedTag).not.toBe('BODY');
			await assertNoBlockingViolations(page);
		});
	}

	test.describe('mobile menu state', () => {
		test.use({ viewport: { width: 390, height: 844 } });

		test('landing mobile menu open state has no blocking violations', async ({ page }) => {
			await page.goto('/');
			await page.waitForLoadState('networkidle');

			const menuButton = page.getByRole('button', { name: /toggle menu/i });
			await expect(menuButton).toBeVisible();
			await menuButton.click();
			await expect(page.getByRole('dialog', { name: /public navigation menu/i })).toBeVisible();

			await assertNoBlockingViolations(page);
		});
	});
});
