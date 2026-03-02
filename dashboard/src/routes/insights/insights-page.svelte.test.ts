import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';

vi.mock('$app/paths', () => ({
	base: ''
}));

describe('insights page', () => {
	it('renders insight cards and content CTAs', () => {
		render(Page);

		expect(screen.getByRole('heading', { level: 1, name: /insights/i })).toBeTruthy();
		expect(
			screen.getByRole('heading', {
				name: /how engineering and finance run one weekly spend review/i
			})
		).toBeTruthy();
		expect(
			screen.getByRole('heading', {
				name: /greenops decision framework for cost, carbon, and risk/i
			})
		).toBeTruthy();
		expect(
			screen.getByRole('heading', { name: /cfo brief: building a procurement-ready tco narrative/i })
		).toBeTruthy();

		expect(screen.getByRole('link', { name: /open playbook/i }).getAttribute('href')).toBe(
			'/resources'
		);
		expect(screen.getByRole('link', { name: /open greenops guide/i }).getAttribute('href')).toBe(
			'/greenops'
		);
		expect(
			screen.getByRole('link', { name: /download roi worksheet/i }).getAttribute('href')
		).toBe('/resources/valdrics-roi-assumptions.csv');
	});
});
