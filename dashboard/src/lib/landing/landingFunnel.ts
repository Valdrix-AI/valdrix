import type {
	CtaVariant,
	HeroVariant,
	SectionOrderVariant,
	StorageLike
} from './landingExperiment';

export type FunnelStage = 'view' | 'engaged' | 'cta' | 'signup_intent';

export interface LandingUtmParams {
	source?: string;
	medium?: string;
	campaign?: string;
	term?: string;
	content?: string;
}

export interface LandingAttribution {
	utm: LandingUtmParams;
	firstTouchAt?: string;
	lastTouchAt?: string;
}

export interface LandingFunnelCounts {
	view: number;
	engaged: number;
	cta: number;
	signup_intent: number;
}

export interface LandingFunnelSummary {
	counts: LandingFunnelCounts;
	conversion: {
		engagementRate: number;
		ctaRate: number;
		signupIntentRate: number;
	};
}

export interface LandingWeeklyFunnelSummary {
	weekStart: string;
	counts: LandingFunnelCounts;
	conversion: LandingFunnelSummary['conversion'];
}

export interface LandingWeeklyTrendCheck {
	metric: 'engagementRate' | 'ctaRate' | 'signupIntentRate';
	latest: number;
	previous: number;
	delta: number;
	direction: 'up' | 'down' | 'flat';
}

export interface LandingFunnelTelemetryContext {
	visitorId?: string;
	persona?: string;
	referrer?: string;
	pagePath?: string;
	stage?: FunnelStage;
	experiments?: {
		hero?: HeroVariant;
		cta?: CtaVariant;
		order?: SectionOrderVariant;
	};
	utm?: LandingUtmParams;
}

const ATTRIBUTION_STORAGE_KEY = 'valdrics.landing.attribution.v1';
const FUNNEL_STORAGE_KEY = 'valdrics.landing.funnel.v1';
const WEEKLY_FUNNEL_STORAGE_KEY = 'valdrics.landing.weekly_funnel.v1';

const EMPTY_COUNTS: LandingFunnelCounts = Object.freeze({
	view: 0,
	engaged: 0,
	cta: 0,
	signup_intent: 0
});

function normalizeToken(input: string | null | undefined): string | undefined {
	const trimmed = (input || '').trim();
	if (!trimmed) {
		return undefined;
	}
	return trimmed.slice(0, 120);
}

function readJson<T>(storage: StorageLike | undefined, key: string): T | null {
	if (!storage) return null;

	try {
		const raw = storage.getItem(key);
		if (!raw) return null;
		return JSON.parse(raw) as T;
	} catch {
		return null;
	}
}

function writeJson(storage: StorageLike | undefined, key: string, value: unknown): void {
	if (!storage) return;
	storage.setItem(key, JSON.stringify(value));
}

function parseUtmFromUrl(url: URL): LandingUtmParams {
	return {
		source: normalizeToken(url.searchParams.get('utm_source')),
		medium: normalizeToken(url.searchParams.get('utm_medium')),
		campaign: normalizeToken(url.searchParams.get('utm_campaign')),
		term: normalizeToken(url.searchParams.get('utm_term')),
		content: normalizeToken(url.searchParams.get('utm_content'))
	};
}

function hasAnyUtm(utm: LandingUtmParams): boolean {
	return Boolean(utm.source || utm.medium || utm.campaign || utm.term || utm.content);
}

function withRate(numerator: number, denominator: number): number {
	if (denominator <= 0) {
		return 0;
	}
	return Number((numerator / denominator).toFixed(4));
}

function normalizeCounts(value: Partial<LandingFunnelCounts> | undefined): LandingFunnelCounts {
	return {
		view: Math.max(0, value?.view || 0),
		engaged: Math.max(0, value?.engaged || 0),
		cta: Math.max(0, value?.cta || 0),
		signup_intent: Math.max(0, value?.signup_intent || 0)
	};
}

function summarizeFunnel(counts: LandingFunnelCounts): LandingFunnelSummary {
	return {
		counts,
		conversion: {
			engagementRate: withRate(counts.engaged, counts.view),
			ctaRate: withRate(counts.cta, counts.view),
			signupIntentRate: withRate(counts.signup_intent, counts.view)
		}
	};
}

function isoWeekStart(date: Date): string {
	const utc = new Date(
		Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), 0, 0, 0, 0)
	);
	const weekday = utc.getUTCDay();
	const dayOffset = weekday === 0 ? -6 : 1 - weekday;
	utc.setUTCDate(utc.getUTCDate() + dayOffset);
	return utc.toISOString().slice(0, 10);
}

type WeeklyFunnelStore = Record<string, LandingFunnelCounts>;

function readWeeklyStore(storage?: StorageLike): WeeklyFunnelStore {
	const parsed = readJson<WeeklyFunnelStore>(storage, WEEKLY_FUNNEL_STORAGE_KEY) || {};
	const normalized: WeeklyFunnelStore = {};
	for (const [weekStart, counts] of Object.entries(parsed)) {
		if (!/^\d{4}-\d{2}-\d{2}$/.test(weekStart)) continue;
		normalized[weekStart] = normalizeCounts(counts);
	}
	return normalized;
}

function writeWeeklyStore(storage: StorageLike | undefined, store: WeeklyFunnelStore): void {
	writeJson(storage, WEEKLY_FUNNEL_STORAGE_KEY, store);
}

export function captureLandingAttribution(
	url: URL,
	storage?: StorageLike,
	now: Date = new Date()
): LandingAttribution {
	const existing = readJson<LandingAttribution>(storage, ATTRIBUTION_STORAGE_KEY) || { utm: {} };
	const incomingUtm = parseUtmFromUrl(url);
	const incomingHasUtm = hasAnyUtm(incomingUtm);

	const updated: LandingAttribution = {
		utm: incomingHasUtm ? incomingUtm : existing.utm || {}
	};

	if (!existing.firstTouchAt && incomingHasUtm) {
		updated.firstTouchAt = now.toISOString();
	} else if (existing.firstTouchAt) {
		updated.firstTouchAt = existing.firstTouchAt;
	}

	if (incomingHasUtm || existing.lastTouchAt) {
		updated.lastTouchAt = incomingHasUtm ? now.toISOString() : existing.lastTouchAt;
	}

	writeJson(storage, ATTRIBUTION_STORAGE_KEY, updated);
	return updated;
}

export function readLandingAttribution(storage?: StorageLike): LandingAttribution {
	return readJson<LandingAttribution>(storage, ATTRIBUTION_STORAGE_KEY) || { utm: {} };
}

export function incrementLandingFunnelStage(
	stage: FunnelStage,
	storage?: StorageLike,
	now: Date = new Date()
): LandingFunnelSummary {
	const current = normalizeCounts(
		readJson<LandingFunnelCounts>(storage, FUNNEL_STORAGE_KEY) || EMPTY_COUNTS
	);
	const next: LandingFunnelCounts = { ...current };
	next[stage] += 1;
	writeJson(storage, FUNNEL_STORAGE_KEY, next);
	incrementLandingWeeklyStage(stage, storage, now);
	return summarizeFunnel(next);
}

export function incrementLandingWeeklyStage(
	stage: FunnelStage,
	storage?: StorageLike,
	now: Date = new Date()
): LandingWeeklyFunnelSummary {
	const weeklyStore = readWeeklyStore(storage);
	const weekStart = isoWeekStart(now);
	const counts = normalizeCounts(weeklyStore[weekStart]);
	counts[stage] += 1;
	weeklyStore[weekStart] = counts;
	writeWeeklyStore(storage, weeklyStore);
	return {
		weekStart,
		...summarizeFunnel(counts)
	};
}

export function readLandingFunnelReport(storage?: StorageLike): LandingFunnelSummary {
	const counts = normalizeCounts(
		readJson<LandingFunnelCounts>(storage, FUNNEL_STORAGE_KEY) || EMPTY_COUNTS
	);
	return summarizeFunnel(counts);
}

export function readLandingWeeklyFunnelReport(
	storage?: StorageLike,
	weeks = 8
): LandingWeeklyFunnelSummary[] {
	const safeWeeks = Math.min(52, Math.max(1, Math.floor(weeks)));
	const weeklyStore = readWeeklyStore(storage);
	const starts = Object.keys(weeklyStore).sort().slice(-safeWeeks);
	return starts.map((weekStart) => {
		const counts = normalizeCounts(weeklyStore[weekStart]);
		return {
			weekStart,
			...summarizeFunnel(counts)
		};
	});
}

export function buildLandingWeeklyTrendChecks(
	weekly: LandingWeeklyFunnelSummary[]
): LandingWeeklyTrendCheck[] {
	if (weekly.length === 0) {
		return [
			{
				metric: 'engagementRate',
				latest: 0,
				previous: 0,
				delta: 0,
				direction: 'flat'
			},
			{
				metric: 'ctaRate',
				latest: 0,
				previous: 0,
				delta: 0,
				direction: 'flat'
			},
			{
				metric: 'signupIntentRate',
				latest: 0,
				previous: 0,
				delta: 0,
				direction: 'flat'
			}
		];
	}

	const latest = weekly[weekly.length - 1];
	const previous = weekly.length > 1 ? weekly[weekly.length - 2] : undefined;

	const metrics: Array<{
		key: LandingWeeklyTrendCheck['metric'];
		latest: number;
		previous: number;
	}> = [
		{
			key: 'engagementRate',
			latest: latest?.conversion.engagementRate ?? 0,
			previous: previous?.conversion.engagementRate ?? 0
		},
		{
			key: 'ctaRate',
			latest: latest?.conversion.ctaRate ?? 0,
			previous: previous?.conversion.ctaRate ?? 0
		},
		{
			key: 'signupIntentRate',
			latest: latest?.conversion.signupIntentRate ?? 0,
			previous: previous?.conversion.signupIntentRate ?? 0
		}
	];

	return metrics.map((entry) => {
		const rawDelta = Number((entry.latest - entry.previous).toFixed(4));
		const direction: LandingWeeklyTrendCheck['direction'] =
			rawDelta > 0 ? 'up' : rawDelta < 0 ? 'down' : 'flat';
		return {
			metric: entry.key,
			latest: entry.latest,
			previous: entry.previous,
			delta: rawDelta,
			direction
		};
	});
}
