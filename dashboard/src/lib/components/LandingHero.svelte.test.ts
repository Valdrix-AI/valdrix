import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
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
	it('renders key sections and login CTAs with base-safe links', () => {
		render(LandingHero);

		const mainHeading = screen.getByRole('heading', { level: 1, name: /cloud cost intelligence/i });
		expect(mainHeading).toBeTruthy();

		expect(screen.getByRole('heading', { name: /how it works/i })).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /ai-powered analysis you can control/i })
		).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /works where your operators already work/i })
		).toBeTruthy();
		expect(screen.getByRole('heading', { name: /frequently asked questions/i })).toBeTruthy();

		const ctas = screen.getAllByRole('link', { name: /get started free/i });
		expect(ctas.length).toBeGreaterThanOrEqual(2);
		for (const cta of ctas) {
			expect(cta.getAttribute('href')).toBe('/auth/login');
		}

		const summary = screen.getByText(/signal map summary/i);
		const signalMap = summary.closest('.signal-map');
		expect(signalMap).toBeTruthy();
		expect(signalMap?.getAttribute('role')).toBeNull();

		const signalGraphic = signalMap?.querySelector('svg[role="img"]');
		expect(signalGraphic).toBeTruthy();
		expect(signalGraphic?.getAttribute('aria-labelledby')).toBe('signal-map-summary');
		expect(summary.getAttribute('id')).toBe('signal-map-summary');
	});
});
