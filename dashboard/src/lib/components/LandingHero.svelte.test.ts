import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import LandingHero from './LandingHero.svelte';

vi.mock('$env/dynamic/public', () => ({
	env: {
		PUBLIC_API_URL: 'https://example.com/api/v1'
	}
}));

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
	it(
		'renders control-plane messaging, evidence, map a11y wiring, and cloud-hook toggles',
		async () => {
			const dataLayer: unknown[] = [];
			(window as Window & { dataLayer?: unknown[] }).dataLayer = dataLayer;
			const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
			window.localStorage.setItem('valdrics.cookie_consent.v1', 'accepted');

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
			screen.getByRole('heading', { name: /need the full 12-month roi planner/i })
		).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /proof from teams reducing spend waste/i })
		).toBeTruthy();
		expect(screen.getByText(/Valdrics helps teams catch overspend early/i)).toBeTruthy();
		expect(
			screen.getByText(/The problem is not visibility\. The problem is delayed action\./i)
		).toBeTruthy();
		expect(screen.getByRole('link', { name: /run the spend scenario simulator/i })).toBeTruthy();
		const talkToSalesLinks = screen.getAllByRole('link', { name: /talk to sales/i });
		expect(talkToSalesLinks.length).toBeGreaterThan(0);
		expect(talkToSalesLinks[0]?.getAttribute('href') || '').toContain('/talk-to-sales?');
		const copyModeToggle = screen.getByRole('button', { name: /switch to plain english/i });
		expect(copyModeToggle).toBeTruthy();
		await fireEvent.click(copyModeToggle);
		expect(screen.getByRole('button', { name: /switch to expert copy/i })).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /realtime spend scenario simulator/i })
		).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /choose a plan and launch in one sprint/i })
		).toBeTruthy();
		expect(screen.getAllByText(/permanent free tier/i).length).toBeGreaterThan(0);
		expect(screen.getByText(/start free\. upgrade only when ready\./i)).toBeTruthy();

		expect(screen.getByText(/20-second guided control walkthrough/i)).toBeTruthy();
		expect(screen.getByLabelText(/reactive waste rate/i)).toBeTruthy();
		expect(screen.getByLabelText(/managed waste rate/i)).toBeTruthy();
		expect(screen.getByLabelText(/decision window \(months\)/i)).toBeTruthy();
		expect(screen.getByText(/Scenario Delta/i)).toBeTruthy();
		expect(screen.getByRole('link', { name: /Open Full ROI Planner/i })).toBeTruthy();
		expect(screen.getByText(/Example 12-month model snapshot/i)).toBeTruthy();
		expect(screen.getByText(/Projected annual spend/i)).toBeTruthy();
		expect(screen.getByText(/Modeled payback window/i)).toBeTruthy();
		expect(screen.getByRole('heading', { name: /not ready to sign up today\?/i })).toBeTruthy();
		expect(screen.getByRole('link', { name: /open resources/i })).toBeTruthy();
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
		expect(screen.getByText(/Cost Intelligence and Forecasting/i)).toBeTruthy();
		expect(screen.getByText(/GreenOps Execution/i)).toBeTruthy();
		expect(screen.getByText(/Cloud Hygiene and Remediation/i)).toBeTruthy();
		expect(screen.getByText(/SaaS and ITAM License Control/i)).toBeTruthy();
		expect(screen.queryByText(/Platform Tooling/i)).toBeNull();
		expect(screen.queryByText(/Operational Integrations/i)).toBeNull();
		const technicalValidationLink = screen.getByRole('link', {
			name: /open technical validation/i
		});
		expect(technicalValidationLink.getAttribute('href')).toBe('/docs/technical-validation');

		expect(
			screen.queryByText(/go deeper without turning the homepage into an audit log/i)
		).toBeNull();
		const namedReferenceLink = screen.getByRole('link', { name: /request named references/i });
		expect(namedReferenceLink.getAttribute('href') || '').toContain('intent=named_references');
		const onePagerLink = screen.getByRole('link', { name: /download executive one-pager/i });
		expect(onePagerLink.getAttribute('href')).toBe('/resources/valdrics-enterprise-one-pager.md');
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
		expect(payload.event).toBe('valdrics_landing_event');
		expect(payload.funnelStage).toBeTruthy();
		expect(payload.experiment).toBeTruthy();

			dispatchSpy.mockRestore();
			window.localStorage.removeItem('valdrics.cookie_consent.v1');
			delete (window as Window & { dataLayer?: unknown[] }).dataLayer;
		},
		15000
	);

	it('shows cookie consent controls before analytics is accepted', async () => {
		window.localStorage.removeItem('valdrics.cookie_consent.v1');
		render(LandingHero);

		expect(screen.getByRole('dialog', { name: /cookie preferences/i })).toBeTruthy();
		const declineButton = screen.getByRole('button', { name: /decline analytics/i });
		await fireEvent.click(declineButton);
		expect(window.localStorage.getItem('valdrics.cookie_consent.v1')).toBe('rejected');
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
