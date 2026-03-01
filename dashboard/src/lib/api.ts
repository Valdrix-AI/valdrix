/**
 * Valdrics Resilient API Client
 *
 * Provides a wrapper around the native fetch API to:
 * 1. Automatically handle 429 (Rate Limit) errors via uiState
 * 2. Standardize error handling for 500s
 * 3. Future-proof for multi-cloud adapters
 * 4. Inject CSRF tokens for state-changing requests
 */

import { uiState } from './stores/ui.svelte';
import { createSupabaseBrowserClient } from './supabase';
import { fetchWithTimeout } from './fetchWithTimeout';
import { edgeApiPath } from './edgeProxy';

export type ResilientRequestInit = RequestInit & {
	/**
	 * Per-request timeout applied to the underlying fetch (aborts on expiry).
	 * Defaults to 30s.
	 */
	timeoutMs?: number;
};

/**
 * Utility to get a cookie value by name
 */
function getCookie(name: string): string | undefined {
	if (typeof document === 'undefined') return undefined;
	for (const cookiePart of document.cookie.split(';')) {
		const [rawName, ...rawValue] = cookiePart.split('=');
		if (!rawName) continue;
		try {
			const cookieName = decodeURIComponent(rawName.trim());
			if (cookieName !== name) continue;
			return decodeURIComponent(rawValue.join('='));
		} catch {
			continue;
		}
	}
	return undefined;
}

let csrfPromise: Promise<string | undefined> | null = null;
const DEV_TENANT_ID_CACHE_TTL_MS = 30000;
let cachedTenantId: string | null = null;
let cachedTenantIdExpiresAt = 0;

function checkTenantIsolation(payload: unknown, tenantId: string): void {
	const stack: unknown[] = [payload];
	while (stack.length > 0) {
		const current = stack.pop();
		if (!current || typeof current !== 'object') continue;
		if (Array.isArray(current)) {
			for (const item of current) stack.push(item);
			continue;
		}
		const record = current as Record<string, unknown>;
		const payloadTenantId = record.tenant_id;
		if (typeof payloadTenantId === 'string' && payloadTenantId !== tenantId) {
			throw new Error('Security Error: Unauthorized data access');
		}
		for (const value of Object.values(record)) {
			if (value && typeof value === 'object') {
				stack.push(value);
			}
		}
	}
}

async function getDevTenantId(): Promise<string | null> {
	if (typeof window === 'undefined') return null;
	const now = Date.now();
	if (now < cachedTenantIdExpiresAt) return cachedTenantId;
	const session = (await createSupabaseBrowserClient().auth.getSession()).data.session;
	cachedTenantId =
		typeof session?.user?.user_metadata?.tenant_id === 'string'
			? session.user.user_metadata.tenant_id
			: null;
	cachedTenantIdExpiresAt = now + DEV_TENANT_ID_CACHE_TTL_MS;
	return cachedTenantId;
}

async function validateTenantPayloadInDev(response: Response): Promise<void> {
	if (!import.meta.env.DEV) return;
	const contentType = response.headers.get('content-type') || '';
	if (!contentType.toLowerCase().includes('application/json')) return;

	const userTenantId = await getDevTenantId();
	if (!userTenantId) return;

	const clone = response.clone();
	const data = await clone.json();
	if (!data || typeof data !== 'object') return;
	checkTenantIsolation(data, userTenantId);
}

export async function resilientFetch(
	url: string | URL,
	options: ResilientRequestInit = {}
): Promise<Response> {
	const { timeoutMs: timeoutMsOverride, ...optionsRest } = options;
	const timeoutMs = timeoutMsOverride ?? 30000; // 30 seconds (Requirement FE-M7)
	const requestOptions: RequestInit = {
		...optionsRest,
		credentials: optionsRest.credentials ?? 'include'
	};

	// Automatic CSRF Protection (SEC-01)
	const method = requestOptions.method?.toUpperCase() || 'GET';
	if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
		let csrfToken = getCookie('fastapi-csrf-token');

		// SEC-06: Prevent CSRF Race Condition with Singleton Promise
		if (!csrfToken) {
			if (!csrfPromise) {
				csrfPromise = (async () => {
					try {
						const csrfRes = await fetchWithTimeout(
							fetch,
							edgeApiPath('/public/csrf'),
							{ credentials: requestOptions.credentials },
							Math.min(5000, timeoutMs)
						);
						if (csrfRes.ok) {
							const data = await csrfRes.json();
							return data.csrf_token;
						}
					} catch {
						// Silent fail for token pre-fetch
					} finally {
						// Allow subsequent retries if some requests still fail
						setTimeout(() => {
							csrfPromise = null;
						}, 1000);
					}
					return undefined;
				})();
			}
			csrfToken = await csrfPromise;
		}

		if (csrfToken) {
			const headers = new Headers(requestOptions.headers);
			headers.set('X-CSRF-Token', csrfToken);
			requestOptions.headers = headers;
		}
	}

	let response = await fetchWithTimeout(fetch, url, requestOptions, timeoutMs);

	if (response.status === 401) {
		// FE-M8: Token Refresh Logic
		const supabase = createSupabaseBrowserClient();
		const {
			data: { session }
		} = await supabase.auth.refreshSession();

		if (session?.access_token) {
			// Retry once with new token
			const headers = new Headers(requestOptions.headers);
			headers.set('Authorization', `Bearer ${session.access_token}`);
			requestOptions.headers = headers;
			response = await fetchWithTimeout(fetch, url, requestOptions, timeoutMs);
		} else {
			// Session expired
		}
	}

	if (response.status === 429) {
		uiState.showRateLimitWarning();
	}

	if (response.ok) {
		try {
			await validateTenantPayloadInDev(response);
		} catch (e: unknown) {
			if (e instanceof Error && e.message.startsWith('Security Error')) throw e;
			// Ignore non-JSON and malformed payloads in this defense-in-depth check.
		}
	}

	if (!response.ok) {
		if (response.status >= 500) {
			// FE-H1: Sanitize error messages globally
			const errorData = await response.json().catch(() => ({}));
			const safeMessage =
				errorData.message ||
				errorData.detail ||
				'An internal server error occurred. Please contact support.';
			// We return a new response with safe message for 5xx
			return new Response(
				JSON.stringify({
					error: 'Internal Server Error',
					message: safeMessage.includes('Traceback')
						? 'A system error occurred. Our engineers have been notified.'
						: safeMessage,
					code: 'SERVER_ERROR'
				}),
				{ status: response.status, headers: { 'Content-Type': 'application/json' } }
			);
		}
	}

	return response;
}

/**
 * Enhanced fetch with exponential backoff for 503s
 */
export async function resilientFetchWithRetry(
	url: string | URL,
	options: ResilientRequestInit = {},
	maxRetries = 3
): Promise<Response> {
	let lastError: Error | null = null;
	for (let i = 0; i < maxRetries; i++) {
		try {
			const response = await resilientFetch(url, options);

			// Handle 503 Service Unavailable with backoff
			if (response.status === 503 && i < maxRetries - 1) {
				const delay = Math.pow(2, i) * 1000;
				await new Promise((resolve) => setTimeout(resolve, delay));
				continue;
			}

			// Handle 403 Forbidden specifically
			if (response.status === 403) {
				uiState.addToast(
					'Access Restricted: You do not have permission to perform this action.',
					'error',
					7000
				);
			}

			return response;
		} catch (e: unknown) {
			lastError = e as Error;
			if (i < maxRetries - 1) {
				const delay = Math.pow(2, i) * 1000;
				await new Promise((resolve) => setTimeout(resolve, delay));
			}
		}
	}
	throw lastError || new Error(`Failed to fetch ${url} after ${maxRetries} attempts`);
}

export const api = {
	get: (url: string, options: ResilientRequestInit = {}) =>
		resilientFetchWithRetry(url, { ...options, method: 'GET' }),
	post: (url: string, body?: unknown, options: ResilientRequestInit = {}) => {
		const headers = new Headers(options.headers);
		const requestOptions: ResilientRequestInit = { ...options, method: 'POST', headers };
		if (body !== undefined) {
			headers.set('Content-Type', 'application/json');
			requestOptions.body = JSON.stringify(body);
		}
		return resilientFetchWithRetry(url, requestOptions);
	},
	put: (url: string, body?: unknown, options: ResilientRequestInit = {}) => {
		const headers = new Headers(options.headers);
		const requestOptions: ResilientRequestInit = { ...options, method: 'PUT', headers };
		if (body !== undefined) {
			headers.set('Content-Type', 'application/json');
			requestOptions.body = JSON.stringify(body);
		}
		return resilientFetchWithRetry(url, requestOptions);
	},
	delete: (url: string, options: ResilientRequestInit = {}) =>
		resilientFetchWithRetry(url, { ...options, method: 'DELETE' })
};
