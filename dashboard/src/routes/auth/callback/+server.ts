import { base } from '$app/paths';
import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

function _safeRedirectTarget(value: string | null): string {
	if (!value) return '/';
	return value.startsWith('/') ? value : '/';
}

export const GET: RequestHandler = async ({ url, locals }) => {
	const next = _safeRedirectTarget(url.searchParams.get('next'));
	const code = url.searchParams.get('code');
	if (!code) {
		const reason = url.searchParams.get('error_description') || url.searchParams.get('error') || 'Missing auth code.';
		throw redirect(303, `${base}/auth/login?error=${encodeURIComponent(reason)}`);
	}

	const { error } = await locals.supabase.auth.exchangeCodeForSession(code);
	if (error) {
		throw redirect(303, `${base}/auth/login?error=${encodeURIComponent(error.message)}`);
	}

	throw redirect(303, `${base}${next}`);
};
