// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from 'vitest';

describe('turnstile helper', () => {
	afterEach(() => {
		vi.resetModules();
		vi.clearAllMocks();
		delete (window as Window & { turnstile?: unknown }).turnstile;
		delete (window as Window & { __VALDRICS_TURNSTILE_SITE_KEY__?: string })
			.__VALDRICS_TURNSTILE_SITE_KEY__;
	});

	it('returns null when site key is not configured', async () => {
		vi.doMock('$app/environment', () => ({ browser: true }));
		vi.doMock('$env/dynamic/public', () => ({ env: {} }));

		const module = await import('./turnstile');
		expect(module.isTurnstileConfigured()).toBe(false);
		await expect(module.getTurnstileToken('sso_discovery')).resolves.toBeNull();
	});

	it('caches tokens per action to avoid duplicate execute calls', async () => {
		vi.doMock('$app/environment', () => ({ browser: true }));
		vi.doMock('$env/dynamic/public', () => ({
			env: {}
		}));
		(
			window as Window & {
				__VALDRICS_TURNSTILE_SITE_KEY__?: string;
			}
		).__VALDRICS_TURNSTILE_SITE_KEY__ = 'site-key';

		let callback: ((token: string) => void) | null = null;
		const executeMock = vi.fn(() => {
			callback?.('token-123');
		});
		(window as Window & { turnstile?: unknown }).turnstile = {
			render: (_container: string | HTMLElement, options: { callback?: (token: string) => void }) => {
				callback = options.callback || null;
				return 'widget-1';
			},
			execute: executeMock,
			reset: vi.fn(),
			remove: vi.fn()
		};

		const module = await import('./turnstile');
		expect(module.isTurnstileConfigured()).toBe(true);

		const first = await module.getTurnstileToken('sso_discovery');
		const second = await module.getTurnstileToken('sso_discovery');

		expect(first).toBe('token-123');
		expect(second).toBe('token-123');
		expect(executeMock).toHaveBeenCalledTimes(1);
	});
});
