import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';

vi.mock('$app/paths', () => ({
	base: ''
}));

describe('docs page', () => {
	it('renders core documentation sections and links', () => {
		render(Page);

		const heading = screen.getByRole('heading', { level: 1, name: /documentation/i });
		expect(heading).toBeTruthy();

		const apiLink = screen.getByRole('link', { name: /open api docs/i });
		expect(apiLink.getAttribute('href')).toBe('/docs/api');

		const validationLink = screen.getByRole('link', { name: /open technical validation/i });
		expect(validationLink.getAttribute('href')).toBe('/docs/technical-validation');

		const pricingLink = screen.getByRole('link', { name: /view pricing/i });
		expect(pricingLink.getAttribute('href')).toBe('/pricing');

		const repoLink = screen.getByRole('link', { name: /browse github docs/i });
		expect(repoLink.getAttribute('href')).toBe(
			'https://github.com/Valdrix-AI/valdrix/tree/main/docs'
		);
	});
});
