import { expect, test } from '@playwright/test';
import { getViolations, injectAxe } from 'axe-playwright';

const CRITICAL_AND_SERIOUS = ['critical', 'serious'] as const;

async function expectNoCriticalOrSeriousViolations(
	path: string,
	page: Parameters<typeof test>[0]['page']
) {
	await page.goto(path);
	await page.waitForLoadState('networkidle');
	await page.waitForTimeout(1400);
	await injectAxe(page);
	const violations = await getViolations(page);
	const blocking = violations.filter((violation) =>
		CRITICAL_AND_SERIOUS.includes((violation.impact ?? '') as (typeof CRITICAL_AND_SERIOUS)[number])
	);
	expect(blocking).toEqual([]);
}

test.describe('Accessibility Smoke', () => {
	test('landing page has no critical/serious axe violations', async ({ page }) => {
		await expectNoCriticalOrSeriousViolations('/', page);
	});

	test('login page has no critical/serious axe violations', async ({ page }) => {
		await expectNoCriticalOrSeriousViolations('/auth/login', page);
	});
});
