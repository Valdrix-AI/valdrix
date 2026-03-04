import { json } from '@sveltejs/kit';
import { detectCurrencyFromCountryCode } from '$lib/landing/roiCalculator';
import type { RequestHandler } from './$types';

function normalizeCountryCode(value: string | null): string | null {
	if (!value) return null;
	const normalized = value.trim().toUpperCase();
	if (!normalized || normalized === 'XX') return null;
	return normalized;
}

function resolveCountryCode(request: Request): string | null {
	return (
		normalizeCountryCode(request.headers.get('cf-ipcountry')) ||
		normalizeCountryCode(request.headers.get('x-vercel-ip-country')) ||
		null
	);
}

export const GET: RequestHandler = async ({ request }) => {
	const countryCode = resolveCountryCode(request);
	const currencyCode = detectCurrencyFromCountryCode(countryCode) ?? 'USD';
	const source = countryCode ? 'ip_country_header' : 'default';

	return json(
		{
			currencyCode,
			countryCode,
			source
		},
		{
			headers: {
				'cache-control': 'private, max-age=300, stale-while-revalidate=900'
			}
		}
	);
};
