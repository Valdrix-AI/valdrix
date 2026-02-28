import { describe, expect, it, vi, beforeEach } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/svelte';

import LoginPage from './+page.svelte';

type PageState = { url: URL };

function createPageStore(initial: PageState) {
	let value = initial;
	const subscribers = new Set<(next: PageState) => void>();
	return {
		subscribe(run: (next: PageState) => void) {
			run(value);
			subscribers.add(run);
			return () => subscribers.delete(run);
		},
		set(next: PageState) {
			value = next;
			for (const subscriber of subscribers) {
				subscriber(next);
			}
		}
	};
}

const mocks = vi.hoisted(() => {
	const pageStore = createPageStore({ url: new URL('https://example.com/auth/login') });
	const signInWithPassword = vi.fn();
	const signUp = vi.fn();
	const signInWithOtp = vi.fn();
	const signInWithSSO = vi.fn();
	return {
		pageStore,
		signInWithPassword,
		signUp,
		signInWithOtp,
		signInWithSSO,
		goto: vi.fn(),
		invalidateAll: vi.fn()
	};
});

vi.mock('$app/stores', () => ({
	page: mocks.pageStore
}));

vi.mock('$app/navigation', () => ({
	goto: mocks.goto,
	invalidateAll: mocks.invalidateAll
}));

vi.mock('$app/paths', () => ({
	base: ''
}));

vi.mock('$lib/edgeProxy', () => ({
	edgeApiPath: (path: string) => `/api/edge${path}`
}));

vi.mock('$lib/supabase', () => ({
	createSupabaseBrowserClient: () => ({
		auth: {
			signInWithPassword: mocks.signInWithPassword,
			signUp: mocks.signUp,
			signInWithOtp: mocks.signInWithOtp,
			signInWithSSO: mocks.signInWithSSO
		}
	})
}));

describe('auth login page conversion flow', () => {
	beforeEach(() => {
		cleanup();
		mocks.pageStore.set({ url: new URL('https://example.com/auth/login') });
		mocks.signInWithPassword.mockReset();
		mocks.signUp.mockReset();
		mocks.signInWithOtp.mockReset();
		mocks.signInWithSSO.mockReset();
		mocks.goto.mockReset();
		mocks.invalidateAll.mockReset();

		mocks.signInWithPassword.mockResolvedValue({ error: null });
		mocks.signUp.mockResolvedValue({ error: null });
		mocks.signInWithOtp.mockResolvedValue({ error: null });
		mocks.signInWithSSO.mockResolvedValue({ data: { url: 'https://idp.example' }, error: null });
	});

	it('auto-enters signup mode and surfaces intent/persona context from landing params', () => {
		mocks.pageStore.set({
			url: new URL(
				'https://example.com/auth/login?intent=roi_assessment&persona=cfo&utm_source=google'
			)
		});
		render(LoginPage);

		expect(screen.getByRole('heading', { level: 1, name: /create your account/i })).toBeTruthy();
		expect(screen.getByText(/Starting with/i)).toBeTruthy();
		expect(screen.getByText(/ROI Assessment/i)).toBeTruthy();
		expect(screen.getByText(/CFO/i)).toBeTruthy();
		expect(screen.getByRole('button', { name: /send secure signup link/i })).toBeTruthy();
	});

	it('logs in with password and redirects to onboarding context when intent is present', async () => {
		mocks.pageStore.set({
			url: new URL('https://example.com/auth/login?mode=login&intent=engineering_control&persona=cto')
		});
		render(LoginPage);

		const emailInput = screen.getByLabelText(/email address/i) as HTMLInputElement;
		const passwordInput = screen.getByLabelText(/password/i) as HTMLInputElement;
		await fireEvent.input(emailInput, { target: { value: 'user@example.com' } });
		await fireEvent.input(passwordInput, { target: { value: 'TopSecret123' } });

		await fireEvent.click(screen.getByRole('button', { name: /^sign in$/i }));

		await waitFor(() => {
			expect(mocks.signInWithPassword).toHaveBeenCalledWith({
				email: 'user@example.com',
				password: 'TopSecret123'
			});
			expect(mocks.invalidateAll).toHaveBeenCalledOnce();
			expect(mocks.goto).toHaveBeenCalledWith('/onboarding?intent=engineering_control&persona=cto');
		});
	});

	it('sends secure magic links with callback redirect and context-preserving next path', async () => {
		mocks.pageStore.set({
			url: new URL(
				'https://example.com/auth/login?intent=roi_assessment&persona=cfo&utm_source=google&utm_medium=cpc'
			)
		});
		render(LoginPage);

		const emailInput = screen.getByLabelText(/email address/i) as HTMLInputElement;
		await fireEvent.input(emailInput, { target: { value: 'FOUNDER@EXAMPLE.COM' } });

		await fireEvent.click(screen.getByRole('button', { name: /send secure signup link/i }));

		await waitFor(() => {
			expect(mocks.signInWithOtp).toHaveBeenCalledTimes(1);
		});
		const payload = mocks.signInWithOtp.mock.calls[0]?.[0] as {
			email: string;
			options: { shouldCreateUser?: boolean; emailRedirectTo?: string };
		};
		expect(payload.email).toBe('founder@example.com');
		expect(payload.options.shouldCreateUser).toBe(true);
		expect(payload.options.emailRedirectTo).toContain('/auth/callback?next=%2Fonboarding%3Fintent%3Droi_assessment');
		expect(screen.getByRole('status').textContent).toMatch(/Secure sign-in link sent/i);
	});
});
