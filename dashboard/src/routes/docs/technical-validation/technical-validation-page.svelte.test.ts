import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';

vi.mock('$app/paths', () => ({
	base: ''
}));

describe('technical validation page', () => {
	it('renders buyer-safe validation matrix and public links', () => {
		render(Page);

		expect(screen.getByRole('heading', { level: 1, name: /public capability validation summary/i })).toBeTruthy();
		expect(screen.getByText(/Cost Intelligence and Forecasting/i)).toBeTruthy();
		expect(screen.getByText(/GreenOps Execution/i)).toBeTruthy();
		expect(screen.getByText(/Security and Identity/i)).toBeTruthy();
		expect(screen.getByText(/it does not expose internal incident data/i)).toBeTruthy();

		expect(screen.getByRole('link', { name: /API Reference/i }).getAttribute('href')).toBe('/docs/api');
		expect(screen.getByRole('link', { name: /Back to Landing/i }).getAttribute('href')).toBe('/');
		expect(screen.queryByText(/docs\/ops\//i)).toBeNull();
		expect(screen.queryByText(/TRC-/i)).toBeNull();
	});
});
