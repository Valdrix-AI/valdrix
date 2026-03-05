import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
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
	it('renders simplified hero plus progressive detail sections with telemetry and map a11y', async () => {
		const dataLayer: unknown[] = [];
		(window as Window & { dataLayer?: unknown[] }).dataLayer = dataLayer;
		const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
		window.localStorage.setItem('valdrics.cookie_consent.v1', 'accepted');

		render(LandingHero);
		const landingRoot = document.querySelector('.landing');
		expect(landingRoot?.className).toContain('landing-motion-subtle');

		const mainHeading = screen.getByRole('heading', { level: 1 });
		expect(mainHeading).toBeTruthy();
		expect(mainHeading.textContent?.length).toBeGreaterThan(12);
		expect(screen.getByText(/one control loop/i)).toBeTruthy();
		expect(screen.getByText(/start free\. upgrade only when ready\./i)).toBeTruthy();

		const primaryCandidates = screen.getAllByRole('link', {
			name: /Start Free|Book Executive Briefing/i
		});
		const primaryCta = primaryCandidates.find((element) =>
			(element.getAttribute('class') || '').includes('pulse-glow')
		);
		expect(primaryCta).toBeTruthy();
		expect(primaryCta?.getAttribute('href')).toContain('/auth/login?');
		if (primaryCta) {
			await fireEvent.click(primaryCta);
		}

		const heroSection = document.querySelector('#hero');
		expect(heroSection).toBeTruthy();
		const heroView = within(heroSection as HTMLElement);
		const secondaryCta = heroView.getByRole('link', { name: /see enterprise path/i });
		expect(secondaryCta).toBeTruthy();
		const secondaryHref = secondaryCta?.getAttribute('href') || '';
		expect(secondaryHref).toContain('/enterprise?');
		expect(secondaryHref).toContain('source=hero_secondary');
		if (secondaryCta) {
			await fireEvent.click(secondaryCta);
		}
		const demoLink = heroView.getByRole('link', { name: /see live signal map/i });
		expect(demoLink.getAttribute('href')).toBe('#signal-map');
		expect(heroView.getByText(/evidence snapshot · february 28, 2026/i)).toBeTruthy();
		expect(heroView.getByText(/285 validation packs passed/i)).toBeTruthy();

		expect(
			screen.getByRole('heading', { name: /visibility alone does not control cloud spend/i })
		).toBeTruthy();
		expect(screen.getByRole('heading', { name: /see it in action/i })).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /realtime spend scenario simulator/i })
		).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /choose a plan and launch in one sprint/i })
		).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /proof and trust/i })
		).toBeTruthy();

		expect(
			screen.queryByRole('heading', { name: /what each team gets in the first 30 days/i })
		).toBeNull();
		expect(
			screen.queryByRole('heading', {
				name: /one platform for cloud, saas, and license spend/i
			})
		).toBeNull();
		expect(screen.queryByRole('heading', { name: /not ready to sign up today\?/i })).toBeNull();
		expect(screen.queryByRole('button', { name: /switch to plain english/i })).toBeNull();
		expect(screen.queryByRole('link', { name: /run the spend scenario simulator/i })).toBeNull();

		const withoutToggle = screen.getByRole('button', { name: /^without valdrics$/i });
		const withToggle = screen.getByRole('button', { name: /^with valdrics$/i });
		expect(withoutToggle.getAttribute('aria-pressed')).toBe('true');
		expect(withToggle.getAttribute('aria-pressed')).toBe('false');
		await fireEvent.click(withToggle);
		expect(withToggle.getAttribute('aria-pressed')).toBe('true');
		expect(screen.getByText(/guardrailed/i)).toBeTruthy();

		const summary = screen.getByText(/signal map summary for snapshot a/i);
		const signalMap = summary.closest('.signal-map');
		expect(signalMap).toBeTruthy();
		const signalGraphic = signalMap?.querySelector('svg[role="img"]');
		expect(signalGraphic).toBeTruthy();
		expect(signalGraphic?.getAttribute('aria-labelledby')).toBe('signal-map-summary');
		expect(summary.getAttribute('id')).toBe('signal-map-summary');

		await fireEvent.click(screen.getByRole('button', { name: /explore control details/i }));
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

		expect(screen.getByLabelText(/reactive waste rate/i)).toBeTruthy();
		expect(screen.getByLabelText(/managed waste rate/i)).toBeTruthy();
		expect(screen.getByLabelText(/decision window \(months\)/i)).toBeTruthy();
		expect(screen.getByText(/Scenario Delta/i)).toBeTruthy();
		expect(screen.getByRole('link', { name: /Open Full ROI Planner/i })).toBeTruthy();

		const freePlanCta = screen.getByRole('link', { name: /start on free tier/i });
		expect(freePlanCta.getAttribute('href') || '').toContain('plan=free');
		await fireEvent.click(freePlanCta);

		const trustSection = document.querySelector('#trust');
		expect(trustSection).toBeTruthy();
		const trustView = within(trustSection as HTMLElement);
		const validationBriefingLink = trustView.getByRole('link', {
			name: /talk to sales for validation/i
		});
		const validationHref = validationBriefingLink.getAttribute('href') || '';
		expect(validationHref).toContain('/talk-to-sales?');
		expect(validationHref).toContain('source=trust_validation');
		const onePagerLink = screen.getByRole('link', {
			name: /download executive one-pager/i
		});
		expect(onePagerLink.getAttribute('href')).toBe('/resources/valdrics-enterprise-one-pager.md');

		expect(dispatchSpy).toHaveBeenCalled();
		expect(dataLayer.length).toBeGreaterThan(0);
		const payload = dataLayer[dataLayer.length - 1] as Record<string, unknown>;
		expect(payload.event).toBe('valdrics_landing_event');
		expect(payload.funnelStage).toBeTruthy();
		expect(payload.experiment).toBeTruthy();

		dispatchSpy.mockRestore();
		window.localStorage.removeItem('valdrics.cookie_consent.v1');
		delete (window as Window & { dataLayer?: unknown[] }).dataLayer;
	}, 15000);

	it('shows cookie consent controls before analytics is accepted', async () => {
		window.localStorage.removeItem('valdrics.cookie_consent.v1');
		render(LandingHero);

		expect(screen.getByRole('dialog', { name: /cookie preferences/i })).toBeTruthy();
		const declineButton = screen.getByRole('button', { name: /decline analytics/i });
		await fireEvent.click(declineButton);
		expect(window.localStorage.getItem('valdrics.cookie_consent.v1')).toBe('rejected');
	});

	it('disables auto-rotation when reduced motion is preferred', () => {
		vi.useFakeTimers();
		const setIntervalSpy = vi.spyOn(globalThis, 'setInterval');
		const originalMatchMedia = window.matchMedia;
		const matchMediaStub = vi.fn().mockReturnValue({
			matches: true,
			addEventListener: vi.fn(),
			removeEventListener: vi.fn()
		});
		Object.defineProperty(window, 'matchMedia', {
			writable: true,
			value: matchMediaStub
		});

		const { unmount } = render(LandingHero);
		const intervalDurationsMs = setIntervalSpy.mock.calls.map((call) => Number(call[1]));
		expect(intervalDurationsMs).not.toContain(4400);
		expect(intervalDurationsMs).not.toContain(3200);

		unmount();
		setIntervalSpy.mockRestore();
		Object.defineProperty(window, 'matchMedia', {
			writable: true,
			value: originalMatchMedia
		});
		vi.useRealTimers();
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
