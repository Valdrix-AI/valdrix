import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';

vi.mock('$app/paths', () => ({
	base: ''
}));

describe('enterprise page', () => {
	it('renders enterprise governance narrative with dual-track actions', () => {
		render(Page);

		expect(screen.getByRole('heading', { level: 1 })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /enterprise-critical control pillars/i })).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /formal diligence and procurement workflows/i })
		).toBeTruthy();

		const briefingLink = screen.getByRole('link', { name: /request enterprise briefing/i });
		const briefingHref = briefingLink.getAttribute('href') || '';
		expect(briefingHref).toContain('mailto:enterprise@valdrics.com');
		expect(briefingHref).toContain('cc=sales@valdrics.com');

		expect(screen.getByRole('link', { name: /talk to sales/i }).getAttribute('href')).toBe(
			'/talk-to-sales'
		);
		expect(screen.getByRole('link', { name: /view plans/i }).getAttribute('href')).toBe('/pricing');
		expect(
			screen.getByRole('link', { name: /download executive one-pager/i }).getAttribute('href')
		).toBe('/resources/valdrics-enterprise-one-pager.md');
		expect(
			screen.getByRole('link', { name: /download compliance checklist/i }).getAttribute('href')
		).toBe('/resources/global-finops-compliance-workbook.md');
	});
});
