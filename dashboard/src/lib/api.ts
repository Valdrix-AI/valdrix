/**
 * Valdrix Resilient API Client
 *
 * Provides a wrapper around the native fetch API to:
 * 1. Automatically handle 429 (Rate Limit) errors via uiState
 * 2. Standardize error handling for 500s
 * 3. Future-proof for multi-cloud adapters
 * 4. Inject CSRF tokens for state-changing requests
 */

import { PUBLIC_API_URL } from '$env/static/public';
import { uiState } from './stores/ui.svelte';
import { createSupabaseBrowserClient } from './supabase';

/**
 * Utility to get a cookie value by name
 */
function getCookie(name: string): string | undefined {
	if (typeof document === 'undefined') return undefined;
	const value = `; ${document.cookie}`;
	const parts = value.split(`; ${name}=`);
	if (parts.length === 2) return parts.pop()?.split(';').shift();
	return undefined;
}

export async function resilientFetch(
	url: string | URL,
	options: RequestInit = {}
): Promise<Response> {
	const timeout = 30000; // 30 seconds (Requirement FE-M7)
	const controller = new AbortController();
	const id = setTimeout(() => controller.abort(), timeout);

	try {
		const requestOptions: RequestInit = {
			...options,
			signal: controller.signal,
			credentials: options.credentials ?? 'include'
		};

		// Automatic CSRF Protection (SEC-01)
		const method = requestOptions.method?.toUpperCase() || 'GET';
		if (!['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
			let csrfToken = getCookie('fastapi-csrf-token');

			// If token missing, try to fetch it from the unified CSRF endpoint
			if (!csrfToken) {
				try {
					const csrfRes = await fetch(`${PUBLIC_API_URL}/public/csrf`, {
						credentials: requestOptions.credentials
					});
					if (csrfRes.ok) {
						const data = await csrfRes.json();
						csrfToken = data.csrf_token;
					}
				} catch (e) {
					console.warn('[CSRF] Failed to pre-fetch token', e);
				}
			}

			if (csrfToken) {
				const headers = new Headers(requestOptions.headers);
				headers.set('X-CSRF-Token', csrfToken);
				requestOptions.headers = headers;
			}
		}

		let response = await fetch(url, requestOptions);
		clearTimeout(id);

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
				response = await fetch(url, requestOptions);
			} else {
				console.warn('[API Auth] 401 Unauthorized and Refresh failed. Session expired.');
			}
		}

		if (response.status === 429) {
			uiState.showRateLimitWarning();
		}

		if (response.ok) {
			// FE-H6: Client-side Tenant Data Validation
			// Extra layer of safety to ensure no data leakage
			try {
				const clone = response.clone();
				const data = await clone.json();
				const session = (await createSupabaseBrowserClient().auth.getSession()).data.session;
				const userTenantId = session?.user?.user_metadata?.tenant_id;

				if (userTenantId && data && typeof data === 'object') {
					const checkTenant = (obj: Record<string, unknown> | Array<unknown>) => {
						if (Array.isArray(obj)) {
							obj.forEach((item) => {
								if (item && typeof item === 'object') checkTenant(item as Record<string, unknown>);
							});
							return;
						}

						if (obj.tenant_id && userTenantId && obj.tenant_id !== userTenantId) {
							console.error('[Security] Tenant Data Leakage Detected!', {
								expected: userTenantId,
								actual: obj.tenant_id
							});
							throw new Error('Security Error: Unauthorized data access');
						}
						for (const k in obj) {
							const val = obj[k];
							if (val && typeof val === 'object') checkTenant(val as Record<string, unknown>);
						}
					};
					checkTenant(data as Record<string, unknown> | Array<unknown>);
				}
			} catch (e: unknown) {
				if (e instanceof Error && e.message.startsWith('Security Error')) throw e;
				// Ignore parsing errors for non-JSON responses
			}
		}

		if (!response.ok) {
			if (response.status >= 500) {
				console.error(`[API Error] ${response.status} at ${url}`);
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
	} catch (error) {
		console.error(`[Network Error] at ${url}`, error);
		throw error;
	}
}

/**
 * Enhanced fetch with exponential backoff for 503s
 */
export async function resilientFetchWithRetry(
	url: string | URL,
	options: RequestInit = {},
	maxRetries = 3
): Promise<Response> {
	let lastError: Error | null = null;
	for (let i = 0; i < maxRetries; i++) {
		try {
			const response = await resilientFetch(url, options);

			// Handle 503 Service Unavailable with backoff
			if (response.status === 503 && i < maxRetries - 1) {
				const delay = Math.pow(2, i) * 1000;
				console.warn(
					`[API] 503 detected. Retrying in ${delay}ms... (Attempt ${i + 1}/${maxRetries})`
				);
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
	get: (url: string, options: RequestInit = {}) =>
		resilientFetchWithRetry(url, { ...options, method: 'GET' }),
	post: (url: string, body?: unknown, options: RequestInit = {}) => {
		const headers = new Headers(options.headers);
		const requestOptions: RequestInit = { ...options, method: 'POST', headers };
		if (body !== undefined) {
			headers.set('Content-Type', 'application/json');
			requestOptions.body = JSON.stringify(body);
		}
		return resilientFetchWithRetry(url, requestOptions);
	},
	put: (url: string, body?: unknown, options: RequestInit = {}) => {
		const headers = new Headers(options.headers);
		const requestOptions: RequestInit = { ...options, method: 'PUT', headers };
		if (body !== undefined) {
			headers.set('Content-Type', 'application/json');
			requestOptions.body = JSON.stringify(body);
		}
		return resilientFetchWithRetry(url, requestOptions);
	},
	delete: (url: string, options: RequestInit = {}) =>
		resilientFetchWithRetry(url, { ...options, method: 'DELETE' })
};
