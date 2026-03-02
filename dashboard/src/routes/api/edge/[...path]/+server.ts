import { env as privateEnv } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';
import { error, type RequestHandler } from '@sveltejs/kit';

const CACHEABLE_GET_PREFIXES = ['/health/live', '/api/v1/billing/plans'];
const EDGE_CACHE_S_MAXAGE_SECONDS = 30;
const EDGE_CACHE_STALE_WHILE_REVALIDATE_SECONDS = 30;
const EDGE_CACHE_NAMESPACE = 'valdrics-edge-proxy';
const JOB_STREAM_SUFFIX = '/jobs/stream';

function resolveBackendOrigin(): string {
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

function isSafeCacheableRequest(
	method: string,
	pathname: string,
	headers: Headers,
	responseHeaders?: Headers
): boolean {
	if (method !== 'GET') return false;
	if (headers.has('authorization')) return false;
	if (headers.has('cookie')) return false;
	if (!CACHEABLE_GET_PREFIXES.some((prefix) => pathname.startsWith(prefix))) return false;
	if (responseHeaders?.has('set-cookie')) return false;
	return true;
}

function buildUpstreamHeaders(requestHeaders: Headers): Headers {
	const headers = new Headers();
	const allowed = [
		'accept',
		'accept-language',
		'authorization',
		'content-type',
		'cookie',
		'user-agent',
		'x-csrf-token',
		'x-requested-with'
	];

	for (const key of allowed) {
		const value = requestHeaders.get(key);
		if (value) {
			headers.set(key, value);
		}
	}

	headers.set('x-valdrics-edge-proxy', '1');
	return headers;
}

async function proxyRequest(event: Parameters<RequestHandler>[0]): Promise<Response> {
	const backendOrigin = resolveBackendOrigin();
	const requestUrl = new URL(event.request.url);
	const rawPath = String(event.params.path || '').replace(/^\/+/, '');
	const targetPath = `/${rawPath}`;
	const targetUrl = new URL(`${targetPath}${requestUrl.search}`, `${backendOrigin}/`);

	const method = event.request.method.toUpperCase();
	const requestHeaders = buildUpstreamHeaders(event.request.headers);
	if (targetPath.endsWith(JOB_STREAM_SUFFIX) && !requestHeaders.has('authorization')) {
		const { session } = await event.locals.safeGetSession();
		if (session?.access_token) {
			requestHeaders.set('authorization', `Bearer ${session.access_token}`);
		}
	}

	const shouldAttemptCache = isSafeCacheableRequest(method, targetPath, event.request.headers);
	const cacheApi = typeof caches === 'undefined' ? null : await caches.open(EDGE_CACHE_NAMESPACE);
	const cacheKey = shouldAttemptCache
		? new Request(targetUrl.toString(), {
				method: 'GET',
				headers: new Headers({ Accept: event.request.headers.get('accept') || '*/*' })
			})
		: null;

	if (cacheApi && cacheKey) {
		const cached = await cacheApi.match(cacheKey);
		if (cached) {
			const headers = new Headers(cached.headers);
			headers.set('x-valdrics-edge-cache', 'HIT');
			headers.set('x-valdrics-edge-proxy', '1');
			return new Response(cached.body, { status: cached.status, headers });
		}
	}

	let body: BodyInit | undefined;
	if (!['GET', 'HEAD'].includes(method)) {
		body = await event.request.arrayBuffer();
	}

	let upstreamResponse: Response;
	try {
		upstreamResponse = await fetch(targetUrl.toString(), {
			method,
			headers: requestHeaders,
			body,
			redirect: 'manual'
		});
	} catch (exc) {
		const message = exc instanceof Error ? exc.message : 'Unknown upstream error';
		throw error(502, `Edge proxy upstream request failed: ${message}`);
	}

	const responseHeaders = new Headers(upstreamResponse.headers);
	responseHeaders.set('x-valdrics-edge-proxy', '1');

	const isCacheable = isSafeCacheableRequest(
		method,
		targetPath,
		event.request.headers,
		upstreamResponse.headers
	);

	if (isCacheable) {
		responseHeaders.set(
			'Cache-Control',
			`public, s-maxage=${EDGE_CACHE_S_MAXAGE_SECONDS}, stale-while-revalidate=${EDGE_CACHE_STALE_WHILE_REVALIDATE_SECONDS}`
		);
		responseHeaders.set('x-valdrics-edge-cache', 'MISS');
	} else if (!responseHeaders.has('Cache-Control')) {
		responseHeaders.set('Cache-Control', 'no-store');
	}

	const response = new Response(upstreamResponse.body, {
		status: upstreamResponse.status,
		headers: responseHeaders
	});

	if (cacheApi && cacheKey && isCacheable && response.status >= 200 && response.status < 400) {
		const platformContext = (
			event.platform as { context?: { waitUntil?: (p: Promise<unknown>) => void } } | undefined
		)?.context;
		platformContext?.waitUntil?.(cacheApi.put(cacheKey, response.clone()));
	}

	return response;
}

export const GET: RequestHandler = proxyRequest;
export const HEAD: RequestHandler = proxyRequest;
export const POST: RequestHandler = proxyRequest;
export const PUT: RequestHandler = proxyRequest;
export const PATCH: RequestHandler = proxyRequest;
export const DELETE: RequestHandler = proxyRequest;
export const OPTIONS: RequestHandler = proxyRequest;
