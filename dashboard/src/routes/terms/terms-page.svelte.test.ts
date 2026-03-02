import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';

describe('terms page', () => {
	it('renders production service terms sections', () => {
		render(Page);

		expect(screen.getByRole('heading', { level: 1, name: /terms of service/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /service scope/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /billing and subscription/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /limitation of liability/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /governing law and disputes/i })).toBeTruthy();
		const legalMailLink = screen.getByRole('link', { name: /legal@valdrics.ai/i });
		expect(legalMailLink.getAttribute('href')).toBe('mailto:legal@valdrics.ai');
	});
});
