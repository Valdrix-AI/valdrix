import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';

vi.mock('$app/paths', () => ({
	base: ''
}));

describe('resources page', () => {
	it('renders resource cards and guided signup CTA', () => {
		render(Page);

		expect(screen.getByRole('heading', { level: 1, name: /resources/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /cloud waste review checklist/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /greenops decision framework/i })).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /saas and license governance starter pack/i })
		).toBeTruthy();
		expect(screen.getByRole('heading', { name: /executive one-pager/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /roi assumptions worksheet/i })).toBeTruthy();

		const startFreeLink = screen.getByRole('link', { name: /start free/i });
		expect(startFreeLink.getAttribute('href')).toContain('/auth/login?intent=resource_signup');
		const talkToSalesLink = screen.getByRole('link', { name: /talk to sales/i });
		expect(talkToSalesLink.getAttribute('href')).toContain('/talk-to-sales');
		const insightsLink = screen.getByRole('link', { name: /open insights/i });
		expect(insightsLink.getAttribute('href')).toBe('/insights');
		const onePagerLink = screen.getByRole('link', { name: /download one-pager/i });
		expect(onePagerLink.getAttribute('href')).toBe('/resources/valdrics-enterprise-one-pager.md');
		const worksheetLink = screen.getByRole('link', { name: /download worksheet/i });
		expect(worksheetLink.getAttribute('href')).toBe('/resources/valdrics-roi-assumptions.csv');
	});
});
