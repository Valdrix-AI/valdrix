import { createHash } from 'node:crypto';
import { env } from '$env/dynamic/private';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const MAX_EMAIL_LENGTH = 254;
const MAX_TEXT_LENGTH = 120;
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX_REQUESTS = 8;

type SubscriptionBody = {
	email: string;
	company?: string;
	role?: string;
	referrer?: string;
	honey?: string;
};

const requestTimestampsByClient = new Map<string, number[]>();

function pruneOldTimestamps(nowMs: number, timestamps: number[]): number[] {
	return timestamps.filter((value) => nowMs - value < RATE_LIMIT_WINDOW_MS);
}

function resolveClientKey(request: Request, getClientAddress?: () => string): string {
	const forwardedFor = request.headers.get('x-forwarded-for')?.trim();
	if (forwardedFor) {
		const firstHop = forwardedFor.split(',')[0]?.trim();
		if (firstHop) return firstHop;
	}
	if (typeof getClientAddress === 'function') {
		try {
			const candidate = getClientAddress().trim();
			if (candidate) return candidate;
		} catch {
			// ignore adapter-specific address lookup failures
		}
	}
	return 'unknown';
}

function canAcceptRequest(clientKey: string, nowMs: number): boolean {
	const prior = requestTimestampsByClient.get(clientKey) ?? [];
	const fresh = pruneOldTimestamps(nowMs, prior);
	if (fresh.length >= RATE_LIMIT_MAX_REQUESTS) {
		requestTimestampsByClient.set(clientKey, fresh);
		return false;
	}
	fresh.push(nowMs);
	requestTimestampsByClient.set(clientKey, fresh);
	return true;
}

function hashEmail(email: string): string {
	return createHash('sha256').update(email).digest('hex');
}

function normalizeBody(payload: unknown): SubscriptionBody | null {
	if (!payload || typeof payload !== 'object') return null;
	const candidate = payload as Record<string, unknown>;
	const email = String(candidate.email ?? '').trim().toLowerCase();
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

async function notifyWebhook(payload: SubscriptionBody): Promise<void> {
	const webhookUrl = String(
		env.MARKETING_SUBSCRIBE_WEBHOOK_URL || process.env.MARKETING_SUBSCRIBE_WEBHOOK_URL || ''
	).trim();
	if (!webhookUrl) {
		return;
	}

	const controller = new AbortController();
	const timeout = setTimeout(() => controller.abort(), 2500);
	try {
		const response = await fetch(webhookUrl, {
			method: 'POST',
			headers: { 'content-type': 'application/json' },
			body: JSON.stringify({
				email: payload.email,
				company: payload.company ?? null,
				role: payload.role ?? null,
				referrer: payload.referrer ?? null,
				timestamp: new Date().toISOString()
			}),
			signal: controller.signal
		});
		if (!response.ok) {
			throw new Error(`webhook_rejected_${response.status}`);
		}
	} finally {
		clearTimeout(timeout);
	}
}

export function _resetMarketingSubscribeRateLimitForTests(): void {
	requestTimestampsByClient.clear();
}

export const POST: RequestHandler = async ({ request, getClientAddress }) => {
	const nowMs = Date.now();
	const clientKey = resolveClientKey(request, getClientAddress);
	if (!canAcceptRequest(clientKey, nowMs)) {
		return json({ ok: false, error: 'rate_limited' }, { status: 429 });
	}

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
		await notifyWebhook(body);
	} catch (error) {
		console.error('marketing_subscribe_webhook_failed', {
			emailHash: hashEmail(body.email),
			clientKey,
			error: error instanceof Error ? error.message : 'unknown'
		});
		return json({ ok: false, error: 'delivery_failed' }, { status: 503 });
	}

	return json(
		{
			ok: true,
			accepted: true,
			emailHash: hashEmail(body.email)
		},
		{ status: 202 }
	);
};
