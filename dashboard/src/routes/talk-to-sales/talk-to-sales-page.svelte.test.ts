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
		expect(screen.getByRole('heading', { name: /compliance and security review/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /rollout and ownership model/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /tco and roi planning/i })).toBeTruthy();

		const emailSalesLink = screen.getByRole('link', { name: /email sales/i });
		expect(emailSalesLink.getAttribute('href') || '').toContain('mailto:sales@valdrics.ai');

		const resourcesLink = screen.getByRole('link', { name: /open sales resources/i });
		expect(resourcesLink.getAttribute('href')).toBe('/resources');

		const startFreeLink = screen.getByRole('link', { name: /start free instead/i });
		expect(startFreeLink.getAttribute('href')).toContain('/auth/login?intent=talk_to_sales');
	});
});
