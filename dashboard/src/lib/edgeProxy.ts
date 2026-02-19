import { PUBLIC_API_URL } from '$env/static/public';

const EDGE_PROXY_PREFIX = '/api/edge';

function resolveApiPathPrefix(apiBaseUrl: string): string {
	try {
		const parsed = new URL(apiBaseUrl);
		const pathname = parsed.pathname || '/';
		return pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
	} catch {
		const normalized = apiBaseUrl.startsWith('/') ? apiBaseUrl : `/${apiBaseUrl}`;
		return normalized.endsWith('/') ? normalized.slice(0, -1) : normalized;
	}
}

/**
 * Pure helper for building edge-proxy paths from any API base URL.
 */
export function buildEdgeApiPath(apiBaseUrl: string, pathAndQuery: string): string {
	const apiPathPrefix = resolveApiPathPrefix(apiBaseUrl);
	const normalized = pathAndQuery.startsWith('/') ? pathAndQuery : `/${pathAndQuery}`;
	return `${EDGE_PROXY_PREFIX}${apiPathPrefix}${normalized}`;
}

/**
 * Build an edge-proxy URL while preserving the API path prefix from PUBLIC_API_URL.
 *
 * Example:
 * - PUBLIC_API_URL=https://api.example.com/api/v1
 * - edgeApiPath('/costs?start=...') => /api/edge/api/v1/costs?start=...
 */
export function edgeApiPath(pathAndQuery: string): string {
	return buildEdgeApiPath(PUBLIC_API_URL, pathAndQuery);
}
