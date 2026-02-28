import { describe, expect, it, vi } from 'vitest';

import { GET } from './+server';

vi.mock('$app/paths', () => ({
	base: ''
}));

type ExchangeResult = { error: { message: string } | null };

function createEvent(url: string, exchange: ExchangeResult = { error: null }) {
	return {
		url: new URL(url),
		locals: {
			supabase: {
				auth: {
					exchangeCodeForSession: vi.fn().mockResolvedValue(exchange)
				}
			}
		}
	} as unknown as Parameters<typeof GET>[0];
}

describe('auth callback redirect safety', () => {
	it('redirects to login with error when code is missing', async () => {
		await expect(GET(createEvent('https://example.com/auth/callback'))).rejects.toMatchObject({
			status: 303,
			location: '/auth/login?error=Missing%20auth%20code.'
		});
	});

	it('uses safe same-origin next target after successful exchange', async () => {
		await expect(
			GET(createEvent('https://example.com/auth/callback?code=ok&next=%2Fops%3Ftab%3Dsignals'))
		).rejects.toMatchObject({
			status: 303,
			location: '/ops?tab=signals'
		});
	});

	it('drops protocol-relative next target to prevent open redirects', async () => {
		await expect(
			GET(createEvent('https://example.com/auth/callback?code=ok&next=%2F%2Fevil.example'))
		).rejects.toMatchObject({
			status: 303,
			location: '/'
		});
	});

	it('redirects to login when code exchange fails', async () => {
		await expect(
			GET(
				createEvent('https://example.com/auth/callback?code=bad', {
					error: { message: 'Invalid auth code' }
				})
			)
		).rejects.toMatchObject({
			status: 303,
			location: '/auth/login?error=Invalid%20auth%20code'
		});
	});
});
