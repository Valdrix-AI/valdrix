import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/svelte';
import type { Snippet } from 'svelte';
import Layout from './+layout.svelte';

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
	const pageStore = createPageStore({ url: new URL('https://example.com/') });
	return {
		pageStore,
		uiState: {
			toasts: [],
			isSidebarOpen: true,
			isCommandPaletteOpen: false,
			toggleSidebar: vi.fn()
		},
		jobStore: {
			activeJobsCount: 0,
			init: vi.fn(),
			disconnect: vi.fn()
		},
		invalidate: vi.fn()
	};
});

vi.mock('$app/stores', () => ({
	page: mocks.pageStore
}));

vi.mock('$app/paths', () => ({
	base: ''
}));

vi.mock('$app/navigation', () => ({
	invalidate: mocks.invalidate
}));

vi.mock('$app/environment', () => ({
	browser: true
}));

vi.mock('$lib/supabase', () => ({
	createSupabaseBrowserClient: () => ({
		auth: {
			onAuthStateChange: () => ({
				data: {
					subscription: {
						unsubscribe: vi.fn()
					}
				}
			})
		}
	})
}));

vi.mock('$lib/stores/ui.svelte', () => ({
	uiState: mocks.uiState
}));

vi.mock('$lib/stores/jobs.svelte', () => ({
	jobStore: mocks.jobStore
}));

describe('public layout mobile menu', () => {
	const emptySnippet = (() => '') as unknown as Snippet;

	function getMenuToggle(): HTMLButtonElement {
		return screen.getAllByRole('button', { name: /toggle menu/i })[0] as HTMLButtonElement;
	}

	function renderPublicLayout() {
		return render(Layout, {
			data: {
				user: null,
				session: null,
				profile: null,
				subscription: { tier: 'free', status: 'active' }
			},
			children: emptySnippet
		});
	}

	it('opens, traps focus, and closes with escape/backdrop', async () => {
		renderPublicLayout();

		const toggle = getMenuToggle();
		await fireEvent.click(toggle);

		const dialog = await screen.findByRole('dialog', { name: /public navigation menu/i });
		expect(dialog).toBeTruthy();
		expect(document.body.style.overflow).toBe('hidden');

		await waitFor(() => {
			const active = document.activeElement as HTMLElement | null;
			expect(active?.textContent?.trim()).toMatch(/talk to sales/i);
		});

		await fireEvent.keyDown(window, { key: 'Tab', shiftKey: true });
		await waitFor(() => {
			const active = document.activeElement as HTMLElement | null;
			expect(active?.textContent?.trim()).toMatch(/^pricing$/i);
		});

		await fireEvent.keyDown(window, { key: 'Tab' });
		await waitFor(() => {
			const active = document.activeElement as HTMLElement | null;
			expect(active?.textContent?.trim()).toMatch(/talk to sales/i);
		});

		await fireEvent.keyDown(window, { key: 'Escape' });
		await waitFor(() => {
			expect(screen.queryByRole('dialog', { name: /public navigation menu/i })).toBeNull();
		});
		expect(document.body.style.overflow).toBe('');

		await fireEvent.click(toggle);
		await screen.findByRole('dialog', { name: /public navigation menu/i });
		const backdropClose = screen.getByRole('button', { name: /close navigation menu/i });
		await fireEvent.click(backdropClose);
		await waitFor(() => {
			expect(screen.queryByRole('dialog', { name: /public navigation menu/i })).toBeNull();
		});
	});

	it('closes when route changes', async () => {
		renderPublicLayout();

		await fireEvent.click(getMenuToggle());
		await screen.findByRole('dialog', { name: /public navigation menu/i });

		mocks.pageStore.set({ url: new URL('https://example.com/pricing') });
		await waitFor(() => {
			expect(screen.queryByRole('dialog', { name: /public navigation menu/i })).toBeNull();
		});
	});

	it('closes when user scrolls after opening the menu', async () => {
		renderPublicLayout();

		await fireEvent.click(getMenuToggle());
		await screen.findByRole('dialog', { name: /public navigation menu/i });

		Object.defineProperty(window, 'scrollY', {
			value: 96,
			writable: true,
			configurable: true
		});
		await fireEvent.scroll(window);

		await waitFor(() => {
			expect(screen.queryByRole('dialog', { name: /public navigation menu/i })).toBeNull();
		});
	});
});
