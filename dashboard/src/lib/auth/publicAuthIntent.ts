export type PublicAuthMode = 'login' | 'signup';

export type PublicAuthIntent =
	| 'engineering_control'
	| 'finops_governance'
	| 'security_governance'
	| 'executive_briefing'
	| 'roi_assessment';

export type PublicAuthPersona = 'cto' | 'finops' | 'security' | 'cfo';

export interface PublicAuthUtm {
	source?: string;
	medium?: string;
	campaign?: string;
	term?: string;
	content?: string;
}

export interface PublicAuthContext {
	mode: PublicAuthMode;
	intent?: PublicAuthIntent;
	persona?: PublicAuthPersona;
	nextPath?: string;
	utm: PublicAuthUtm;
}

const VALID_MODES: readonly PublicAuthMode[] = ['login', 'signup'];
const VALID_INTENTS: readonly PublicAuthIntent[] = [
	'engineering_control',
	'finops_governance',
	'security_governance',
	'executive_briefing',
	'roi_assessment'
];
const VALID_PERSONAS: readonly PublicAuthPersona[] = ['cto', 'finops', 'security', 'cfo'];
const SAFE_NEXT_PATH_PATTERN = /^\/(?!\/)(?!\\)[^\s]*$/;
const MAX_TOKEN_LENGTH = 96;

const INTENT_LABELS: Record<PublicAuthIntent, string> = Object.freeze({
	engineering_control: 'Engineering Control',
	finops_governance: 'FinOps Governance',
	security_governance: 'Security Governance',
	executive_briefing: 'Executive Briefing',
	roi_assessment: 'ROI Assessment'
});

const PERSONA_LABELS: Record<PublicAuthPersona, string> = Object.freeze({
	cto: 'CTO',
	finops: 'FinOps',
	security: 'Security',
	cfo: 'CFO'
});

function normalizeToken(value: string | null | undefined): string {
	return (value || '').trim().toLowerCase();
}

function normalizeOptionalToken(value: string | null | undefined): string | undefined {
	const normalized = normalizeToken(value);
	if (!normalized) {
		return undefined;
	}
	return normalized.slice(0, MAX_TOKEN_LENGTH);
}

function parseMode(raw: string | null): PublicAuthMode | null {
	const token = normalizeToken(raw);
	return (VALID_MODES.find((mode) => mode === token) as PublicAuthMode | undefined) ?? null;
}

function parseIntent(raw: string | null): PublicAuthIntent | null {
	const token = normalizeToken(raw);
	return (VALID_INTENTS.find((intent) => intent === token) as PublicAuthIntent | undefined) ?? null;
}

function parsePersona(raw: string | null): PublicAuthPersona | null {
	const token = normalizeToken(raw);
	return (
		(VALID_PERSONAS.find((persona) => persona === token) as PublicAuthPersona | undefined) ?? null
	);
}

function sanitizeNextPath(raw: string | null): string | null {
	const token = (raw || '').trim();
	if (!token) {
		return null;
	}
	if (!SAFE_NEXT_PATH_PATTERN.test(token)) {
		return null;
	}
	try {
		const parsed = new URL(token, 'https://example.com');
		return `${parsed.pathname}${parsed.search}${parsed.hash}`;
	} catch {
		return null;
	}
}

function parseUtm(url: URL): PublicAuthUtm {
	return {
		source: normalizeOptionalToken(url.searchParams.get('utm_source')),
		medium: normalizeOptionalToken(url.searchParams.get('utm_medium')),
		campaign: normalizeOptionalToken(url.searchParams.get('utm_campaign')),
		term: normalizeOptionalToken(url.searchParams.get('utm_term')),
		content: normalizeOptionalToken(url.searchParams.get('utm_content'))
	};
}

export function parsePublicAuthContext(url: URL): PublicAuthContext {
	const explicitMode = parseMode(url.searchParams.get('mode'));
	const intent = parseIntent(url.searchParams.get('intent')) ?? undefined;
	const persona = parsePersona(url.searchParams.get('persona')) ?? undefined;
	const nextPath = sanitizeNextPath(url.searchParams.get('next')) ?? undefined;

	return {
		mode: explicitMode ?? (intent ? 'signup' : 'login'),
		intent,
		persona,
		nextPath,
		utm: parseUtm(url)
	};
}

export function buildPostAuthRedirectPath(context: PublicAuthContext): string {
	if (context.nextPath) {
		return context.nextPath;
	}
	if (!context.intent) {
		return '/';
	}

	const params = new URLSearchParams({ intent: context.intent });
	if (context.persona) {
		params.set('persona', context.persona);
	}
	if (context.utm.source) {
		params.set('utm_source', context.utm.source);
	}
	if (context.utm.medium) {
		params.set('utm_medium', context.utm.medium);
	}
	if (context.utm.campaign) {
		params.set('utm_campaign', context.utm.campaign);
	}
	if (context.utm.term) {
		params.set('utm_term', context.utm.term);
	}
	if (context.utm.content) {
		params.set('utm_content', context.utm.content);
	}
	return `/onboarding?${params.toString()}`;
}

export function buildAuthCallbackPath(context: PublicAuthContext): string {
	const next = buildPostAuthRedirectPath(context);
	const params = new URLSearchParams({ next });
	return `/auth/callback?${params.toString()}`;
}

export function describePublicIntent(intent: PublicAuthIntent | undefined): string | null {
	if (!intent) {
		return null;
	}
	return INTENT_LABELS[intent] ?? null;
}

export function describePublicPersona(persona: PublicAuthPersona | undefined): string | null {
	if (!persona) {
		return null;
	}
	return PERSONA_LABELS[persona] ?? null;
}
