import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';
import type { PageData } from './$types';

vi.mock('$app/paths', () => ({
	base: ''
}));

describe('ROI planner page', () => {
	it('renders gated ROI planner workspace for signed-in users', () => {
		const data = {
			user: {
				id: 'user-1',
				app_metadata: {},
				user_metadata: {},
				aud: 'authenticated',
				created_at: '2026-03-01T00:00:00.000Z'
			},
			session: null,
			subscription: { tier: 'free', status: 'active' },
			profile: null
		} as unknown as PageData;
		render(Page, {
			data
		});

		expect(screen.getByRole('heading', { level: 1, name: /roi planner workspace/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /build your 12-month roi plan/i })).toBeTruthy();
		expect(screen.getByRole('link', { name: /continue to guided setup/i }).getAttribute('href')).toBe(
			'/onboarding?intent=roi_assessment'
		);
	});

	it('prompts unauthenticated users to sign in', () => {
		const data = {
			user: null,
			session: null,
			subscription: { tier: 'free', status: 'active' },
			profile: null
		} as unknown as PageData;
		render(Page, {
			data
		});

		expect(screen.getByText(/please/i)).toBeTruthy();
		expect(screen.getByRole('link', { name: /sign in/i }).getAttribute('href')).toBe('/auth/login');
	});
});
