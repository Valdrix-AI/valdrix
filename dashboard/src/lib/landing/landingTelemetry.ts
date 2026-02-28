import { edgeApiPath } from '$lib/edgeProxy';

export interface LandingTelemetryEvent {
	eventId: string;
	name: string;
	section: string;
	value?: string;
	visitorId?: string;
	persona?: string;
	funnelStage?: string;
	pagePath?: string;
	referrer?: string;
	experiment?: {
		hero?: string;
		cta?: string;
		order?: string;
	};
	utm?: {
		source?: string;
		medium?: string;
		campaign?: string;
		term?: string;
		content?: string;
	};
	timestamp: string;
}

export interface LandingTelemetryContext {
	visitorId?: string;
	persona?: string;
	funnelStage?: string;
	pagePath?: string;
	referrer?: string;
	experiment?: {
		hero?: string;
		cta?: string;
		order?: string;
	};
	utm?: {
		source?: string;
		medium?: string;
		campaign?: string;
		term?: string;
		content?: string;
	};
}

export interface LandingTelemetryTarget {
	dispatchEvent?: (event: Event) => boolean;
	dataLayer?: unknown[];
	createCustomEvent?: (
		type: string,
		init: CustomEventInit<LandingTelemetryEvent>
	) => Event;
	sendToBackend?: (payload: LandingTelemetryEvent) => void | Promise<void>;
}

const MAX_TOKEN_LENGTH = 96;
const LANDING_EVENT_TYPE = 'valdrix:landing_event';
const DATA_LAYER_EVENT_NAME = 'valdrix_landing_event';
const LANDING_BACKEND_PATH = '/public/landing/events';

function normalizeToken(input: string | null | undefined, fallback: string): string {
	const trimmed = (input || '').trim();
	if (!trimmed) {
		return fallback;
	}
	return trimmed.slice(0, MAX_TOKEN_LENGTH);
}

function normalizeOptionalToken(input: string | null | undefined): string | undefined {
	const normalized = normalizeToken(input, '');
	return normalized || undefined;
}

function resolveDefaultTarget(): LandingTelemetryTarget {
	if (typeof window === 'undefined') {
		return {};
	}

	const maybeWindow = window as Window & { dataLayer?: unknown[] };
	const layer = Array.isArray(maybeWindow.dataLayer) ? maybeWindow.dataLayer : undefined;
	return {
		dispatchEvent: maybeWindow.dispatchEvent.bind(maybeWindow),
		dataLayer: layer,
		createCustomEvent: (type, init) => new CustomEvent<LandingTelemetryEvent>(type, init)
	};
}

function createEventId(now: Date): string {
	const timestamp = now.getTime().toString(36);
	const random =
		typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
			? crypto.randomUUID().slice(0, 8)
			: Math.random().toString(36).slice(2, 10);
	return `evt-${timestamp}-${random}`;
}

function defaultSendToBackend(payload: LandingTelemetryEvent): void {
	if (typeof window === 'undefined' || typeof fetch !== 'function') {
		return;
	}

	const endpoint = edgeApiPath(LANDING_BACKEND_PATH);
	const body = JSON.stringify(payload);
	const contentType = 'application/json';
	try {
		const nav = window.navigator;
		if (typeof nav.sendBeacon === 'function') {
			const blob = new Blob([body], { type: contentType });
			if (nav.sendBeacon(endpoint, blob)) {
				return;
			}
		}
	} catch {
		// Non-fatal fallback to keepalive fetch below.
	}

	void fetch(endpoint, {
		method: 'POST',
		headers: { 'Content-Type': contentType },
		body,
		keepalive: true
	}).catch(() => {
		// Non-fatal: telemetry should never block user flow.
	});
}

export function buildLandingTelemetryEvent(
	name: string,
	section: string,
	value?: string,
	context: LandingTelemetryContext = {},
	now: Date = new Date()
): LandingTelemetryEvent {
	const normalizedName = normalizeToken(name, 'unknown_action');
	const normalizedSection = normalizeToken(section, 'unknown_section');
	const normalizedValue = normalizeToken(value, '');

	return {
		eventId: createEventId(now),
		name: normalizedName,
		section: normalizedSection,
		value: normalizedValue || undefined,
		visitorId: normalizeOptionalToken(context.visitorId),
		persona: normalizeOptionalToken(context.persona),
		funnelStage: normalizeOptionalToken(context.funnelStage),
		pagePath: normalizeOptionalToken(context.pagePath),
		referrer: normalizeOptionalToken(context.referrer),
		experiment: context.experiment
			? {
					hero: normalizeOptionalToken(context.experiment.hero),
					cta: normalizeOptionalToken(context.experiment.cta),
					order: normalizeOptionalToken(context.experiment.order)
				}
			: undefined,
		utm: context.utm
			? {
					source: normalizeOptionalToken(context.utm.source),
					medium: normalizeOptionalToken(context.utm.medium),
					campaign: normalizeOptionalToken(context.utm.campaign),
					term: normalizeOptionalToken(context.utm.term),
					content: normalizeOptionalToken(context.utm.content)
				}
			: undefined,
		timestamp: now.toISOString()
	};
}

function isTelemetryTarget(value: unknown): value is LandingTelemetryTarget {
	if (!value || typeof value !== 'object') {
		return false;
	}
	const candidate = value as LandingTelemetryTarget;
	return Boolean(
		candidate.dispatchEvent || candidate.createCustomEvent || Array.isArray(candidate.dataLayer)
	);
}

export function emitLandingTelemetry(
	name: string,
	section: string,
	value?: string,
	contextOrTarget: LandingTelemetryContext | LandingTelemetryTarget = resolveDefaultTarget(),
	targetOverride?: LandingTelemetryTarget
): LandingTelemetryEvent {
	const hasTargetAsFourthArg = isTelemetryTarget(contextOrTarget);
	const context = hasTargetAsFourthArg ? {} : (contextOrTarget as LandingTelemetryContext);
	const target = (hasTargetAsFourthArg
		? (contextOrTarget as LandingTelemetryTarget)
		: targetOverride) || resolveDefaultTarget();

	const payload = buildLandingTelemetryEvent(name, section, value, context);

	const eventFactory =
		target.createCustomEvent ||
		((type: string, init: CustomEventInit<LandingTelemetryEvent>) =>
			new CustomEvent<LandingTelemetryEvent>(type, init));

	try {
		target.dispatchEvent?.(eventFactory(LANDING_EVENT_TYPE, { detail: payload }));
	} catch {
		// Intentionally non-fatal: telemetry should never break user interaction.
	}

	if (Array.isArray(target.dataLayer)) {
		target.dataLayer.push({
			event: DATA_LAYER_EVENT_NAME,
			...payload
		});
	}

	const sendToBackend = target.sendToBackend || defaultSendToBackend;
	try {
		void Promise.resolve(sendToBackend(payload));
	} catch {
		// Non-fatal: telemetry backend ingestion must not impact UX.
	}

	return payload;
}
