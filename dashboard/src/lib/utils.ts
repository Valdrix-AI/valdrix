import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
	return twMerge(clsx(inputs));
}

/**
 * Extract a safe filename from a `Content-Disposition` header.
 *
 * Supports:
 * - `filename="report.csv"`
 * - `filename*=UTF-8''report.csv`
 */
export function filenameFromContentDispositionHeader(
	header: string | null,
	fallback: string
): string {
	if (!header) return fallback;

	const parts = header
		.split(';')
		.map((part) => part.trim())
		.filter(Boolean);

	const filenameStar = parts.find((part) => part.toLowerCase().startsWith('filename*='));
	const filename = parts.find((part) => part.toLowerCase().startsWith('filename='));

	const raw = filenameStar
		? filenameStar.slice('filename*='.length)
		: filename
			? filename.slice('filename='.length)
			: null;

	if (!raw) return fallback;

	const unquoted = raw.replace(/^["']|["']$/g, '').trim();
	const rfc5987 = unquoted.replace(/^UTF-8''/i, '');

	try {
		return decodeURIComponent(rfc5987) || fallback;
	} catch {
		return rfc5987 || fallback;
	}
}

/**
 * Normalize and validate a checkout redirect URL before client-side navigation.
 * Blocks non-http(s) schemes (for example javascript:).
 */
export function normalizeCheckoutUrl(rawUrl: unknown, baseUrl: string): string {
	if (typeof rawUrl !== 'string' || rawUrl.trim().length === 0) {
		throw new Error('Checkout URL is missing or invalid.');
	}

	let parsed: URL;
	try {
		parsed = new URL(rawUrl, baseUrl);
	} catch {
		throw new Error('Checkout URL is malformed.');
	}

	if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
		throw new Error('Checkout URL must use http(s).');
	}

	return parsed.toString();
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChild<T> = T extends { child?: any } ? Omit<T, 'child'> : T;
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type WithoutChildren<T> = T extends { children?: any } ? Omit<T, 'children'> : T;
export type WithoutChildrenOrChild<T> = WithoutChildren<WithoutChild<T>>;
export type WithElementRef<T, U extends HTMLElement = HTMLElement> = T & { ref?: U | null };
