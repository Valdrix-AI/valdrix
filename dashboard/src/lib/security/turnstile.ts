import { browser } from '$app/environment';
import { env } from '$env/dynamic/public';

type TurnstileRenderOptions = {
	sitekey: string;
	size?: 'normal' | 'compact' | 'invisible';
	action?: string;
	callback?: (token: string) => void;
	'expired-callback'?: () => void;
	'error-callback'?: () => void;
};

type TurnstileApi = {
	render: (container: string | HTMLElement, options: TurnstileRenderOptions) => string;
	execute: (widgetId: string, options?: { action?: string }) => void;
	reset: (widgetId?: string) => void;
	remove: (widgetId?: string) => void;
};

declare global {
	interface Window {
		turnstile?: TurnstileApi;
		__VALDRICS_TURNSTILE_SITE_KEY__?: string;
	}
}

const TURNSTILE_SCRIPT_SRC = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
const TURNSTILE_TOKEN_TTL_MS = 2 * 60 * 1000;

let scriptLoadPromise: Promise<void> | null = null;
let widgetId: string | null = null;
const tokenCache = new Map<string, { token: string; expiresAt: number }>();

function siteKey(): string {
	if (browser && typeof window.__VALDRICS_TURNSTILE_SITE_KEY__ === 'string') {
		const override = window.__VALDRICS_TURNSTILE_SITE_KEY__.trim();
		if (override.length > 0) {
			return override;
		}
	}
	return String(env.PUBLIC_TURNSTILE_SITE_KEY || '').trim();
}

export function isTurnstileConfigured(): boolean {
	return siteKey().length > 0;
}

function resolveContainer(): HTMLElement {
	const id = 'valdrics-turnstile-container';
	let container = document.getElementById(id);
	if (container) return container;

	container = document.createElement('div');
	container.id = id;
	container.setAttribute('aria-hidden', 'true');
	container.style.position = 'fixed';
	container.style.left = '-9999px';
	container.style.bottom = '0';
	container.style.width = '1px';
	container.style.height = '1px';
	container.style.overflow = 'hidden';
	document.body.appendChild(container);
	return container;
}

async function ensureTurnstileScript(): Promise<void> {
	if (!browser) return;
	if (!isTurnstileConfigured()) return;
	if (window.turnstile) return;
	if (scriptLoadPromise) {
		await scriptLoadPromise;
		return;
	}

	scriptLoadPromise = new Promise<void>((resolve, reject) => {
		const existing = document.querySelector<HTMLScriptElement>(
			`script[src="${TURNSTILE_SCRIPT_SRC}"]`
		);
		if (existing) {
			existing.addEventListener('load', () => resolve(), { once: true });
			existing.addEventListener('error', () => reject(new Error('turnstile_script_load_failed')), {
				once: true
			});
			return;
		}

		const script = document.createElement('script');
		script.src = TURNSTILE_SCRIPT_SRC;
		script.async = true;
		script.defer = true;
		script.onload = () => resolve();
		script.onerror = () => reject(new Error('turnstile_script_load_failed'));
		document.head.appendChild(script);
	});

	try {
		await scriptLoadPromise;
	} finally {
		scriptLoadPromise = null;
	}
}

export async function getTurnstileToken(action: string): Promise<string | null> {
	if (!browser) return null;
	if (!isTurnstileConfigured()) return null;

	const normalizedAction = String(action || '').trim().toLowerCase();
	if (!normalizedAction) {
		throw new Error('turnstile_action_required');
	}

	const cached = tokenCache.get(normalizedAction);
	const now = Date.now();
	if (cached && cached.expiresAt > now) {
		return cached.token;
	}

	await ensureTurnstileScript();
	const turnstile = window.turnstile;
	if (!turnstile) {
		throw new Error('turnstile_unavailable');
	}

	const container = resolveContainer();
	const token = await new Promise<string>((resolve, reject) => {
		const options: TurnstileRenderOptions = {
			sitekey: siteKey(),
			size: 'invisible',
			action: normalizedAction,
			callback: (issuedToken: string) => {
				if (!issuedToken) {
					reject(new Error('turnstile_empty_token'));
					return;
				}
				resolve(issuedToken);
			},
			'expired-callback': () => reject(new Error('turnstile_token_expired')),
			'error-callback': () => reject(new Error('turnstile_verification_failed'))
		};

		if (!widgetId) {
			widgetId = turnstile.render(container, options);
		} else {
			turnstile.reset(widgetId);
		}
		turnstile.execute(widgetId, { action: normalizedAction });
	});

	tokenCache.set(normalizedAction, {
		token,
		expiresAt: now + TURNSTILE_TOKEN_TTL_MS
	});
	return token;
}
