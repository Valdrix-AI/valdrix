import { expect, test } from '@playwright/test';

const DESKTOP_BUDGET_MS = {
	ttfb: 1800,
	fcp: 2600,
	lcp: 3800,
	domComplete: 5600
} as const;

const MOBILE_BUDGET_MS = {
	ttfb: 2200,
	fcp: 3400,
	lcp: 4800,
	domComplete: 7000
} as const;

const CLS_BUDGET = 0.1;

async function collectLandingMetrics(page: Parameters<typeof test>[0]['page']) {
	await page.addInitScript(() => {
		(window as Window & { __valdricsPerf?: { cls: number; lcp: number } }).__valdricsPerf = {
			cls: 0,
			lcp: 0
		};

		new PerformanceObserver((entryList) => {
			const state = (window as Window & { __valdricsPerf?: { cls: number; lcp: number } })
				.__valdricsPerf;
			if (!state) return;
			for (const entry of entryList.getEntries()) {
				const layoutShift = entry as PerformanceEntry & {
					value?: number;
					hadRecentInput?: boolean;
				};
				if (!layoutShift.hadRecentInput) {
					state.cls += layoutShift.value ?? 0;
				}
			}
		}).observe({ type: 'layout-shift', buffered: true });

		new PerformanceObserver((entryList) => {
			const state = (window as Window & { __valdricsPerf?: { cls: number; lcp: number } })
				.__valdricsPerf;
			if (!state) return;
			const entries = entryList.getEntries();
			const latest = entries[entries.length - 1];
			if (latest) {
				state.lcp = latest.startTime;
			}
		}).observe({ type: 'largest-contentful-paint', buffered: true });
	});

	await page.goto('/');
	await page.waitForLoadState('networkidle');
	await page.waitForTimeout(1200);

	return await page.evaluate(() => {
		const nav = performance.getEntriesByType('navigation')[0] as
			| PerformanceNavigationTiming
			| undefined;
		const fcp = performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null;
		const perfState = (window as Window & { __valdricsPerf?: { cls: number; lcp: number } })
			.__valdricsPerf;
		return {
			ttfb: nav?.responseStart ?? null,
			domComplete: nav?.domComplete ?? null,
			fcp,
			lcp: perfState?.lcp ?? null,
			cls: perfState?.cls ?? null
		};
	});
}

function assertBudget(
	metrics: {
		ttfb: number | null;
		fcp: number | null;
		lcp: number | null;
		domComplete: number | null;
		cls: number | null;
	},
	budget: { ttfb: number; fcp: number; lcp: number; domComplete: number }
) {
	expect(metrics.ttfb).not.toBeNull();
	expect(metrics.fcp).not.toBeNull();
	expect(metrics.lcp).not.toBeNull();
	expect(metrics.domComplete).not.toBeNull();
	expect(metrics.cls).not.toBeNull();

	expect(metrics.ttfb!).toBeLessThan(budget.ttfb);
	expect(metrics.fcp!).toBeLessThan(budget.fcp);
	expect(metrics.lcp!).toBeLessThan(budget.lcp);
	expect(metrics.domComplete!).toBeLessThan(budget.domComplete);
	expect(metrics.cls!).toBeLessThan(CLS_BUDGET);
}

test.describe('Performance Budgets', () => {
	test.describe('Desktop baseline (Lighthouse-aligned budgets)', () => {
		test.use({ viewport: { width: 1440, height: 900 } });

		test('landing page meets desktop web-vitals budgets', async ({ page }) => {
			const metrics = await collectLandingMetrics(page);
			assertBudget(metrics, DESKTOP_BUDGET_MS);
		});
	});

	test.describe('Mobile baseline (Lighthouse-aligned budgets)', () => {
		test.use({ viewport: { width: 390, height: 844 } });

		test('landing page meets mobile web-vitals budgets', async ({ page }) => {
			const metrics = await collectLandingMetrics(page);
			assertBudget(metrics, MOBILE_BUDGET_MS);
		});
	});
});
