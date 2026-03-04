import { env } from '$env/dynamic/private';
import { json } from '@sveltejs/kit';
import { appendCustomerComment, listCustomerComments } from '$lib/server/customerCommentsStore';
import type { User } from '@supabase/supabase-js';
import type { RequestHandler } from './$types';

function resolveEmailAllowlist(): Set<string> {
	const raw = String(
		env.CUSTOMER_COMMENTS_ADMIN_EMAIL_ALLOWLIST ||
			process.env.CUSTOMER_COMMENTS_ADMIN_EMAIL_ALLOWLIST ||
			''
	).trim();
	if (!raw) return new Set();
	return new Set(
		raw
			.split(',')
			.map((entry) => entry.trim().toLowerCase())
			.filter(Boolean)
	);
}

function isAuthorizedAdmin(user: User | null): boolean {
	if (!user?.email) return false;
	const allowlist = resolveEmailAllowlist();
	if (allowlist.size === 0) {
		return true;
	}
	return allowlist.has(user.email.trim().toLowerCase());
}

async function requireAdmin(
	locals: App.Locals
): Promise<{ ok: true } | { ok: false; response: Response }> {
	const { session, user } = await locals.safeGetSession();
	if (!session || !user) {
		return {
			ok: false,
			response: json({ ok: false, error: 'unauthenticated' }, { status: 401 })
		};
	}
	if (!isAuthorizedAdmin(user)) {
		return {
			ok: false,
			response: json({ ok: false, error: 'forbidden' }, { status: 403 })
		};
	}
	return { ok: true };
}

export const GET: RequestHandler = async ({ locals }) => {
	const auth = await requireAdmin(locals);
	if (!auth.ok) return auth.response;
	const items = await listCustomerComments();
	return json(
		{
			ok: true,
			items,
			meta: {
				total: items.length,
				hasLiveCustomerEvidence: items.some((item) => item.stage === 'customer')
			}
		},
		{
			headers: {
				'cache-control': 'no-store'
			}
		}
	);
};

export const POST: RequestHandler = async ({ locals, request }) => {
	const auth = await requireAdmin(locals);
	if (!auth.ok) return auth.response;

	let payload: unknown;
	try {
		payload = await request.json();
	} catch {
		return json({ ok: false, error: 'invalid_json' }, { status: 400 });
	}

	if (!payload || typeof payload !== 'object') {
		return json({ ok: false, error: 'invalid_payload' }, { status: 400 });
	}
	const candidate = payload as Record<string, unknown>;
	const quote = String(candidate.quote ?? '').trim();
	const attribution = String(candidate.attribution ?? '').trim();
	const stage = candidate.stage === 'customer' ? 'customer' : 'design_partner';
	if (!quote || !attribution) {
		return json({ ok: false, error: 'invalid_payload' }, { status: 400 });
	}

	try {
		const items = await appendCustomerComment({ quote, attribution, stage });
		return json(
			{
				ok: true,
				items,
				meta: {
					total: items.length,
					hasLiveCustomerEvidence: items.some((item) => item.stage === 'customer')
				}
			},
			{ status: 201 }
		);
	} catch {
		return json({ ok: false, error: 'invalid_payload' }, { status: 400 });
	}
};
