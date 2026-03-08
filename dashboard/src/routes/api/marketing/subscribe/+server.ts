import { createHash } from 'node:crypto';
import { json } from '@sveltejs/kit';
import { resolveBackendOrigin } from '$lib/server/backend-origin';
import { serverLogger } from '$lib/logging/server';
import type { RequestHandler } from './$types';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_EMAIL_LENGTH = 254;
const MAX_TEXT_LENGTH = 120;
type SubscriptionBody = {
	email: string;
	company?: string;
	role?: string;
	referrer?: string;
	honey?: string;
};

function hashEmail(email: string): string {
	return createHash('sha256').update(email).digest('hex');
}

function normalizeBody(payload: unknown): SubscriptionBody | null {
	if (!payload || typeof payload !== 'object') return null;
	const candidate = payload as Record<string, unknown>;
	const email = String(candidate.email ?? '')
		.trim()
		.toLowerCase();
	const company = String(candidate.company ?? '').trim();
	const role = String(candidate.role ?? '').trim();
	const referrer = String(candidate.referrer ?? '').trim();
	const honey = String(candidate.honey ?? '').trim();

	if (!email || email.length > MAX_EMAIL_LENGTH || !EMAIL_REGEX.test(email)) return null;
	if (company.length > MAX_TEXT_LENGTH || role.length > MAX_TEXT_LENGTH) return null;
	if (referrer.length > 200) return null;

	return {
		email,
		company: company || undefined,
		role: role || undefined,
		referrer: referrer || undefined,
		honey: honey || undefined
	};
}

export function _resetMarketingSubscribeRateLimitForTests(): void {
	// No-op: rate limiting is enforced on the backend public API.
}

export const POST: RequestHandler = async ({ request, fetch }) => {
	let payload: unknown;
	try {
		payload = await request.json();
	} catch {
		return json({ ok: false, error: 'invalid_json' }, { status: 400 });
	}

	const body = normalizeBody(payload);
	if (!body) {
		return json({ ok: false, error: 'invalid_payload' }, { status: 400 });
	}

	// Honeypot: silently accept bot submissions without downstream calls.
	if (body.honey) {
		return json({ ok: true, accepted: true }, { status: 202 });
	}

	try {
		const response = await fetch(`${resolveBackendOrigin()}/api/v1/public/marketing/subscribe`, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify(body)
		});
		const responsePayload = await response.json().catch(() => ({ ok: false, error: 'delivery_failed' }));
		if (!response.ok) {
			if (response.status === 422) {
				return json({ ok: false, error: 'invalid_payload' }, { status: 400 });
			}
			return json(responsePayload, { status: response.status });
		}
		return json(responsePayload, { status: response.status });
	} catch (error) {
		serverLogger.error('marketing_subscribe_proxy_failed', {
			emailHash: hashEmail(body.email),
			error: error instanceof Error ? error.message : 'unknown'
		});
		return json({ ok: false, error: 'delivery_failed' }, { status: 503 });
	}
};
