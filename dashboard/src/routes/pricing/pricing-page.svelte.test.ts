import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import { readable } from 'svelte/store';
import Page from './+page.svelte';
import { DEFAULT_PRICING_PLANS } from './plans';

vi.mock('$env/dynamic/public', () => ({
	env: {
		PUBLIC_API_URL: 'https://api.test/api/v1'
	}
}));

vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'https://api.test/api/v1'
}));

vi.mock('$app/paths', () => ({
	assets: '',
	base: ''
}));

vi.mock('$app/navigation', () => ({
	goto: vi.fn()
}));

vi.mock('$app/stores', () => {
	return {
		page: readable({
			url: new URL('https://example.com/pricing')
		})
	};
});

describe('pricing page public messaging', () => {
	it('keeps Starter/Growth/Pro self-serve messaging while isolating enterprise lane copy', () => {
		render(Page, {
			props: {
				data: {
					user: null,
					session: null,
					plans: DEFAULT_PRICING_PLANS
				}
			}
		});

		expect(screen.getByRole('heading', { level: 1, name: /simple, transparent pricing/i })).toBeTruthy();
		expect(screen.getByText(/permanent free tier/i)).toBeTruthy();
		expect(screen.getByRole('heading', { name: /^starter$/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /^growth$/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /^pro$/i })).toBeTruthy();

		expect(screen.getByRole('heading', { name: /enterprise governance/i })).toBeTruthy();
		expect(screen.getByText(/optional advanced path/i)).toBeTruthy();

		const enterpriseCta = screen.getByRole('link', { name: /contact sales/i });
		expect(enterpriseCta.getAttribute('href') || '').toContain('mailto:enterprise@valdrics.com');
		expect(enterpriseCta.getAttribute('href') || '').toContain('cc=sales@valdrics.com');

		const heroSubtitle = screen.getByText(/permanent free tier/i).closest('.hero-subtitle');
		expect(heroSubtitle?.textContent?.toLowerCase()).toContain('start with a');
		expect(heroSubtitle?.textContent?.toLowerCase()).not.toContain('procurement workflows');
	});
});
