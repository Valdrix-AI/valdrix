import { env as privateEnv } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';
import { error } from '@sveltejs/kit';

export function resolveBackendOrigin(): string {
	const privateOrigin = String(privateEnv.PRIVATE_API_ORIGIN || '').trim();
	if (privateOrigin) {
		return privateOrigin.replace(/\/+$/, '');
	}

	const publicApiUrl = String(publicEnv.PUBLIC_API_URL || '').trim();
	try {
		return new URL(publicApiUrl).origin;
	} catch {
		throw error(
			500,
			'Edge proxy is misconfigured. Set PRIVATE_API_ORIGIN (preferred) or PUBLIC_API_URL.'
		);
	}
}
