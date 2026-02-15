import { describe, expect, it, vi } from 'vitest';

import { fetchWithTimeout, TimeoutError } from './fetchWithTimeout';

describe('fetchWithTimeout', () => {
	it('aborts and throws TimeoutError once the timeout elapses', async () => {
		vi.useFakeTimers();

		const fetchFn = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
			return new Promise<Response>((_resolve, reject) => {
				const signal = init?.signal;
				if (!signal) return reject(new Error('Missing signal'));
				signal.addEventListener('abort', () => {
					const err = new Error('Aborted');
					(err as { name: string }).name = 'AbortError';
					reject(err);
				});
			});
		});

		const promise = fetchWithTimeout(
			fetchFn as unknown as typeof fetch,
			'https://example.com',
			{},
			1000
		);

		const expectation = expect(promise).rejects.toBeInstanceOf(TimeoutError);
		await vi.advanceTimersByTimeAsync(1000);
		await expectation;

		vi.useRealTimers();
	});

	it('propagates caller abort errors without converting to TimeoutError', async () => {
		vi.useFakeTimers();

		const outer = new AbortController();
		const fetchFn = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
			return new Promise<Response>((_resolve, reject) => {
				const signal = init?.signal;
				if (!signal) return reject(new Error('Missing signal'));
				signal.addEventListener('abort', () => {
					const err = new Error('Aborted');
					(err as { name: string }).name = 'AbortError';
					reject(err);
				});
			});
		});

		const promise = fetchWithTimeout(
			fetchFn as unknown as typeof fetch,
			'https://example.com',
			{ signal: outer.signal },
			1000
		);

		const expectation = expect(promise).rejects.toMatchObject({ name: 'AbortError' });
		outer.abort();
		await expectation;

		vi.useRealTimers();
	});

	it('returns the response when it resolves before the timeout', async () => {
		vi.useFakeTimers();

		const fetchFn = vi.fn(() => {
			return new Promise<Response>((resolve) => {
				setTimeout(() => resolve(new Response('ok', { status: 200 })), 500);
			});
		});

		const promise = fetchWithTimeout(
			fetchFn as unknown as typeof fetch,
			'https://example.com',
			{},
			1000
		);

		await vi.advanceTimersByTimeAsync(500);
		await expect(promise).resolves.toBeInstanceOf(Response);

		vi.useRealTimers();
	});
});
