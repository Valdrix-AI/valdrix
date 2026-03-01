import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import LandingHero from './LandingHero.svelte';

vi.mock('$app/paths', () => ({
	assets: '',
	base: ''
}));

vi.mock('$app/stores', () => ({
	page: readable({
		url: new URL('https://example.com/')
	})
}));

describe('LandingHero', () => {
	it('renders control-plane messaging, evidence, map a11y wiring, and cloud-hook toggles', async () => {
		const dataLayer: unknown[] = [];
		(window as Window & { dataLayer?: unknown[] }).dataLayer = dataLayer;
		const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

		render(LandingHero);

		const mainHeading = screen.getByRole('heading', { level: 1 });
		expect(mainHeading).toBeTruthy();
		expect(mainHeading.textContent?.length).toBeGreaterThan(12);

		expect(
			screen.getByRole('heading', { name: /why teams switch from dashboards to control/i })
		).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /visibility alone does not control cloud spend/i })
		).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /what each team gets in the first 30 days/i })
		).toBeTruthy();
		expect(
			screen.getByRole('heading', {
				name: /one platform for cloud, saas, and license spend/i
			})
		).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /see your 12-month control roi before you commit/i })
		).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /proof from teams reducing spend waste/i })
		).toBeTruthy();
		expect(screen.getByText(/Valdrics helps teams catch overspend early/i)).toBeTruthy();
		expect(
			screen.getByText(/The problem is not visibility\. The problem is delayed action\./i)
		).toBeTruthy();
		expect(screen.getByRole('link', { name: /run the spend scenario simulator/i })).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /realtime spend scenario simulator/i })
		).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /choose a plan and launch in one sprint/i })
		).toBeTruthy();
		expect(screen.getAllByText(/permanent free tier/i).length).toBeGreaterThan(0);
		expect(screen.getByText(/start free\. upgrade only when ready\./i)).toBeTruthy();

		expect(screen.getByText(/20-second Cloud Control Demo/i)).toBeTruthy();
		expect(screen.getByLabelText(/reactive waste rate/i)).toBeTruthy();
		expect(screen.getByLabelText(/managed waste rate/i)).toBeTruthy();
		expect(screen.getByLabelText(/decision window \(months\)/i)).toBeTruthy();
		expect(screen.getByText(/Projected 12-Month Impact/i)).toBeTruthy();
		expect(screen.getByRole('link', { name: /Run This In Your Environment/i })).toBeTruthy();
		expect(
			screen.getByText(/Realtime cloud anomaly is detected and scoped to impacted workloads\./i)
		).toBeTruthy();
		expect(screen.queryByText(/Session Funnel/i)).toBeNull();

		const withoutToggle = screen.getByRole('button', { name: /^without valdrics$/i });
		const withToggle = screen.getByRole('button', { name: /^with valdrics$/i });
		expect(withoutToggle.getAttribute('aria-pressed')).toBe('true');
		expect(withToggle.getAttribute('aria-pressed')).toBe('false');
		expect(
			screen.getByText(
				/Anomalies surface late, ownership is unclear, and teams react under pressure\./i
			)
		).toBeTruthy();
		expect(screen.getByText(/After invoice close/i)).toBeTruthy();

		await fireEvent.click(withToggle);
		expect(withoutToggle.getAttribute('aria-pressed')).toBe('false');
		expect(withToggle.getAttribute('aria-pressed')).toBe('true');
		expect(
			screen.getByText(
				/Anomaly detected, owner assigned, risk checked, and action approved in one flow\./i
			)
		).toBeTruthy();
		expect(screen.getByText(/Guardrailed/i)).toBeTruthy();
		expect(screen.getByText(/Recoverable waste \/ month/i)).toBeTruthy();

		const starterPlanCta = screen.getByRole('link', { name: /start with starter/i });
		expect(starterPlanCta.getAttribute('href') || '').toContain('plan=starter');
		await fireEvent.click(starterPlanCta);
		const freePlanCta = screen.getByRole('link', { name: /start on free tier/i });
		expect(freePlanCta.getAttribute('href') || '').toContain('plan=free');
		await fireEvent.click(freePlanCta);

		const buyerTabs = screen.getAllByRole('tab');
		expect(buyerTabs.length).toBeGreaterThanOrEqual(4);
		expect(buyerTabs.some((tab) => tab.getAttribute('aria-selected') === 'true')).toBe(true);
		const buyerCfo = screen.getByRole('tab', { name: /^cfo$/i });
		expect(
			screen.getByRole('heading', {
				level: 3,
				name: /Keep roadmap velocity|Move from reporting|Enforce controls|Protect gross margin/i
			})
		).toBeTruthy();

		await fireEvent.click(buyerCfo);
		expect(buyerCfo.getAttribute('aria-selected')).toBe('true');
		expect(
			screen.getByRole('heading', {
				level: 3,
				name: /Protect gross margin with predictable spend decisions/i
			})
		).toBeTruthy();

		const primaryCandidates = screen.getAllByRole('link', {
			name: /Start Free|Book Executive Briefing/i
		});
		const primaryCta = primaryCandidates.find((element) =>
			(element.getAttribute('class') || '').includes('pulse-glow')
		);
		expect(primaryCta).toBeTruthy();
		expect(primaryCta?.getAttribute('href')).toContain('/auth/login?');
		expect(primaryCta?.getAttribute('href') || '').not.toContain('exp_hero=');
		expect(primaryCta?.getAttribute('href') || '').not.toContain('exp_cta=');
		expect(primaryCta?.getAttribute('href') || '').not.toContain('exp_order=');
		if (primaryCta) {
			await fireEvent.click(primaryCta);
		}

		const secondaryCandidates = screen.getAllByRole('link', { name: /See Plans/i });
		const secondaryCta = secondaryCandidates.find((element) =>
			(element.getAttribute('class') || '').includes('btn-secondary')
		);
		expect(secondaryCta).toBeTruthy();
		const secondaryHref = secondaryCta?.getAttribute('href') || '';
		expect(secondaryHref.startsWith('#plans')).toBe(true);
		if (secondaryCta) {
			await fireEvent.click(secondaryCta);
		}

		const summary = screen.getByText(/signal map summary for snapshot a/i);
		const signalMap = summary.closest('.signal-map');
		expect(signalMap).toBeTruthy();

		const signalGraphic = signalMap?.querySelector('svg[role="img"]');
		expect(signalGraphic).toBeTruthy();
		expect(signalGraphic?.getAttribute('aria-labelledby')).toBe('signal-map-summary');
		expect(summary.getAttribute('id')).toBe('signal-map-summary');

		const snapshotButtons = screen.getAllByRole('button', { name: /snapshot [abc]/i });
		expect(snapshotButtons).toHaveLength(3);
		expect(snapshotButtons[0]?.getAttribute('aria-pressed')).toBe('true');
		await fireEvent.click(snapshotButtons[1] as HTMLButtonElement);
		expect(snapshotButtons[1]?.getAttribute('aria-pressed')).toBe('true');

		const laneTabs = screen.getAllByRole('tab');
		expect(laneTabs.length).toBeGreaterThanOrEqual(4);
		const economicVisibilityTab = screen.getByRole('tab', { name: /Economic Visibility/i });
		await fireEvent.click(economicVisibilityTab);
		expect(screen.getByText(/Current metric:/i)).toBeTruthy();

		expect(
			screen.getByText(/owners, approvals, and safety checks are built into every action path/i)
		).toBeTruthy();
		expect(screen.getByText(/Cloud Infrastructure/i)).toBeTruthy();
		expect(screen.getByText(/GreenOps and Carbon/i)).toBeTruthy();
		expect(screen.getByText(/SaaS Spend/i)).toBeTruthy();
		expect(screen.getByText(/ITAM and License/i)).toBeTruthy();
		expect(screen.getByText(/Platform Tooling/i)).toBeTruthy();
		expect(
			screen.getByRole('heading', {
				name: /what valdrics already runs across your operations/i
			})
		).toBeTruthy();
		expect(screen.getByText(/GreenOps Execution/i)).toBeTruthy();
		expect(screen.getByText(/Operational Integrations/i)).toBeTruthy();
		const technicalValidationLink = screen.getByRole('link', {
			name: /open technical validation/i
		});
		expect(technicalValidationLink.getAttribute('href')).toBe('/docs/technical-validation');

		expect(
			screen.queryByText(/go deeper without turning the homepage into an audit log/i)
		).toBeNull();
		expect(screen.queryByRole('link', { name: /explore docs/i })).toBeNull();
		expect(screen.queryByRole('link', { name: /review api surfaces/i })).toBeNull();
		expect(screen.queryByText(/http_retry\.py/i)).toBeNull();
		expect(screen.queryByText(/license_config\.py/i)).toBeNull();
		expect(screen.queryByText(/Backend validation is passing/i)).toBeNull();
		expect(screen.queryByText(/233 passed/i)).toBeNull();
		expect(screen.queryByText(/52 passed/i)).toBeNull();
		expect(screen.queryByText(/285 passed, 0 failed/i)).toBeNull();
		expect(screen.queryByText(/Runtime Coverage/i)).toBeNull();
		expect(screen.queryByText(/Launch policy gates passing/i)).toBeNull();
		expect(screen.queryByText(/Telemetry Window/i)).toBeNull();
		expect(screen.queryByText(/Capture:/i)).toBeNull();
		expect(screen.queryByText(/Trace:/i)).toBeNull();
		expect(screen.queryByText(/February 28, 2026/i)).toBeNull();
		expect(screen.queryByText(/4 \/ 4/i)).toBeNull();
		expect(screen.queryByText(/docs\/ops\//i)).toBeNull();

		expect(dispatchSpy).toHaveBeenCalled();
		expect(dataLayer.length).toBeGreaterThan(0);
		const payload = dataLayer[dataLayer.length - 1] as Record<string, unknown>;
		expect(payload.event).toBe('valdrix_landing_event');
		expect(payload.funnelStage).toBeTruthy();
		expect(payload.experiment).toBeTruthy();

		dispatchSpy.mockRestore();
		delete (window as Window & { dataLayer?: unknown[] }).dataLayer;
	});

	it('cleans rotating intervals on unmount for concurrency safety', () => {
		vi.useFakeTimers();
		const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
		const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval');

		const { unmount } = render(LandingHero);
		expect(setIntervalSpy).toHaveBeenCalled();

		unmount();
		expect(clearIntervalSpy).toHaveBeenCalled();

		setIntervalSpy.mockRestore();
		clearIntervalSpy.mockRestore();
		vi.useRealTimers();
	});
});
