import { expect, test } from '@playwright/test';

const PERF_BUDGET_MS = {
	ttfb: 2000,
	fcp: 3000,
	lcp: 4500,
	domComplete: 6000
} as const;

const CLS_BUDGET = 0.1;

test.describe('Performance Budgets', () => {
	test('landing page meets baseline Web Vitals budgets', async ({ page }) => {
		await page.addInitScript(() => {
			(window as Window & { __valdrixPerf?: { cls: number; lcp: number } }).__valdrixPerf = {
				cls: 0,
				lcp: 0
			};

			new PerformanceObserver((entryList) => {
				const state = (window as Window & { __valdrixPerf?: { cls: number; lcp: number } })
					.__valdrixPerf;
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
				const state = (window as Window & { __valdrixPerf?: { cls: number; lcp: number } })
					.__valdrixPerf;
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

		const metrics = await page.evaluate(() => {
			const nav = performance.getEntriesByType('navigation')[0] as
				| PerformanceNavigationTiming
				| undefined;
			const fcp = performance.getEntriesByName('first-contentful-paint')[0]?.startTime ?? null;
			const perfState = (window as Window & { __valdrixPerf?: { cls: number; lcp: number } })
				.__valdrixPerf;
			return {
				ttfb: nav?.responseStart ?? null,
				domComplete: nav?.domComplete ?? null,
				fcp,
				lcp: perfState?.lcp ?? null,
				cls: perfState?.cls ?? null
			};
		});

		expect(metrics.ttfb).not.toBeNull();
		expect(metrics.fcp).not.toBeNull();
		expect(metrics.lcp).not.toBeNull();
		expect(metrics.domComplete).not.toBeNull();
		expect(metrics.cls).not.toBeNull();

		expect(metrics.ttfb!).toBeLessThan(PERF_BUDGET_MS.ttfb);
		expect(metrics.fcp!).toBeLessThan(PERF_BUDGET_MS.fcp);
		expect(metrics.lcp!).toBeLessThan(PERF_BUDGET_MS.lcp);
		expect(metrics.domComplete!).toBeLessThan(PERF_BUDGET_MS.domComplete);
		expect(metrics.cls!).toBeLessThan(CLS_BUDGET);
	});
});
