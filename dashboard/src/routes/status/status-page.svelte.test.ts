import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';

describe('status page', () => {
	it('renders service health cards', () => {
		render(Page);

		const heading = screen.getByRole('heading', { level: 1, name: /system status/i });
		expect(heading).toBeTruthy();
		expect(screen.getByText(/dashboard web app/i)).toBeTruthy();
		expect(screen.getByText(/edge api proxy/i)).toBeTruthy();
		expect(screen.getAllByText(/operational/i).length).toBeGreaterThan(0);
	});
});
