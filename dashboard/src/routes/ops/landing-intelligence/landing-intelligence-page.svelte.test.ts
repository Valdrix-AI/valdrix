import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';
import { incrementLandingWeeklyStage } from '$lib/landing/landingFunnel';

vi.mock('$app/environment', () => ({
	browser: true
}));

describe('landing intelligence page', () => {
	beforeEach(() => {
		window.localStorage.clear();
	});

	it('renders weekly conversion metrics and trend checks', async () => {
		incrementLandingWeeklyStage('view', window.localStorage, new Date('2026-02-16T10:00:00.000Z'));
		incrementLandingWeeklyStage(
			'engaged',
			window.localStorage,
			new Date('2026-02-16T10:05:00.000Z')
		);
		incrementLandingWeeklyStage('view', window.localStorage, new Date('2026-02-23T10:00:00.000Z'));
		incrementLandingWeeklyStage(
			'engaged',
			window.localStorage,
			new Date('2026-02-23T10:05:00.000Z')
		);
		incrementLandingWeeklyStage('cta', window.localStorage, new Date('2026-02-23T10:10:00.000Z'));
		incrementLandingWeeklyStage(
			'signup_intent',
			window.localStorage,
			new Date('2026-02-23T10:15:00.000Z')
		);

		render(Page);

		expect(
			screen.getByRole('heading', { level: 1, name: /landing conversion dashboard/i })
		).toBeTruthy();
		expect(screen.getByText(/all-time views/i)).toBeTruthy();
		expect(screen.getByText(/weekly funnel detail/i)).toBeTruthy();
		expect(screen.getByText('2026-02-16')).toBeTruthy();
		expect(screen.getByText('2026-02-23')).toBeTruthy();
		expect(screen.getByText(/ctaRate/i)).toBeTruthy();
		expect(screen.getByText(/signupIntentRate/i)).toBeTruthy();
	});
});
