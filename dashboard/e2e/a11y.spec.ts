import { expect, test } from '@playwright/test';
import { getViolations, injectAxe } from 'axe-playwright';

const CRITICAL_AND_SERIOUS = ['critical', 'serious'] as const;
const E2E_AUTH_HEADER_NAME = 'x-valdrics-e2e-auth';
const E2E_AUTH_HEADER_VALUE = process.env.E2E_AUTH_SECRET || 'playwright';

type RouteCase = {
	path: string;
	authenticated?: boolean;
};

const A11Y_ROUTES: RouteCase[] = [
	{ path: '/' },
	{ path: '/pricing' },
	{ path: '/auth/login' },
	{ path: '/privacy' },
	{ path: '/terms' },
	{ path: '/settings', authenticated: true },
	{ path: '/connections', authenticated: true },
	{ path: '/billing', authenticated: true },
	{ path: '/audit', authenticated: true },
	{ path: '/ops', authenticated: true },
	{ path: '/savings', authenticated: true },
	{ path: '/greenops', authenticated: true },
	{ path: '/leaderboards', authenticated: true },
	{ path: '/llm', authenticated: true },
	{ path: '/admin/health', authenticated: true },
	{ path: '/onboarding', authenticated: true }
];

async function expectNoCriticalOrSeriousViolations(
	routeCase: RouteCase,
	page: Parameters<typeof test>[0]['page']
) {
	if (routeCase.authenticated) {
		await page.context().setExtraHTTPHeaders({
			[E2E_AUTH_HEADER_NAME]: E2E_AUTH_HEADER_VALUE
		});
	} else {
		await page.context().setExtraHTTPHeaders({});
	}

	await page.goto(routeCase.path);
	await page.waitForLoadState('networkidle');
	await page.waitForTimeout(1400);
	await injectAxe(page);
	const violations = await getViolations(page);
	const blocking = violations.filter((violation) =>
		CRITICAL_AND_SERIOUS.includes((violation.impact ?? '') as (typeof CRITICAL_AND_SERIOUS)[number])
	);
	expect(
		blocking,
		JSON.stringify(
			blocking.map((violation) => ({
				id: violation.id,
				impact: violation.impact,
				help: violation.help,
				nodes: violation.nodes.map((node) => ({
					target: node.target,
					failureSummary: node.failureSummary
				}))
			})),
			null,
			2
		)
	).toEqual([]);

	// Keyboard accessibility sanity check: tab should move focus away from body.
	await page.keyboard.press('Tab');
	const focusedTag = await page.evaluate(() => document.activeElement?.tagName ?? 'UNKNOWN');
	expect(focusedTag).not.toBe('BODY');

	// Basic semantic structure check: every route should expose a main landmark.
	await expect(page.locator('main')).toHaveCount(1);
}

test.describe('Accessibility Gate', () => {
	for (const routeCase of A11Y_ROUTES) {
		test(`${routeCase.path} has no critical/serious axe violations`, async ({ page }) => {
			await expectNoCriticalOrSeriousViolations(routeCase, page);
		});
	}
});
