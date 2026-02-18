import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';
import { render } from 'vitest-browser-svelte';
import Page from './+page.svelte';

describe('/+page.svelte', () => {
	it('should render h1', async () => {
		render(Page, {
			data: {
				user: null,
				session: null,
				subscription: { tier: 'free', status: 'active' },
				profile: null,
				costs: null,
				carbon: null,
				zombies: null,
				analysis: null,
				allocation: null,
				unitEconomics: null,
				freshness: null,
				startDate: '',
				endDate: '',
				error: ''
			}
		});

		const heading = page.getByRole('heading', { level: 1 });
		await expect.element(heading).toBeInTheDocument();
	});
});
