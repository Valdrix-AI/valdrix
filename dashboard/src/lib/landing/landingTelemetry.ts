export interface LandingTelemetryEvent {
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
}

const MAX_TOKEN_LENGTH = 96;
const LANDING_EVENT_TYPE = 'valdrix:landing_event';
const DATA_LAYER_EVENT_NAME = 'valdrix_landing_event';

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

	return payload;
}
