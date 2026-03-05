import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';

vi.mock('$app/paths', () => ({
	base: ''
}));

describe('talk-to-sales page', () => {
	it('renders enterprise sales paths and CTAs', () => {
		render(Page);

		expect(screen.getByRole('heading', { level: 1, name: /talk to sales/i })).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /starter\/growth\/pro onboarding and rollout/i })
		).toBeTruthy();
		expect(screen.getByRole('heading', { name: /security and governance review/i })).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /commercial and procurement diligence/i })
		).toBeTruthy();

		const emailSalesLink = screen.getByRole('link', { name: /email sales/i });
		expect(emailSalesLink.getAttribute('href') || '').toContain(
			'mailto:enterprise@valdrics.com'
		);
		expect(emailSalesLink.getAttribute('href') || '').toContain('cc=sales@valdrics.com');

		const resourcesLink = screen.getByRole('link', { name: /open sales resources/i });
		expect(resourcesLink.getAttribute('href')).toBe('/resources');

		const enterpriseOverviewLink = screen.getByRole('link', {
			name: /explore enterprise overview/i
		});
		expect(enterpriseOverviewLink.getAttribute('href')).toBe('/enterprise');

		const startFreeLink = screen.getByRole('link', { name: /start free instead/i });
		expect(startFreeLink.getAttribute('href')).toContain('/auth/login?intent=talk_to_sales');
	});
});
