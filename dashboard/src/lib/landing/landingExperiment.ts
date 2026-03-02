export type BuyerPersona = 'cto' | 'finops' | 'security' | 'cfo';
export type HeroVariant = 'control_every_dollar' | 'from_metrics_to_control';
export type CtaVariant = 'start_free' | 'book_briefing';
export type SectionOrderVariant = 'problem_first' | 'workflow_first';

export interface LandingExperimentAssignments {
	buyerPersonaDefault: BuyerPersona;
	heroVariant: HeroVariant;
	ctaVariant: CtaVariant;
	sectionOrderVariant: SectionOrderVariant;
	seed: string;
}

export interface StorageLike {
	getItem(key: string): string | null;
	setItem(key: string, value: string): void;
}

const VISITOR_ID_STORAGE_KEY = 'valdrics.landing.visitor_id.v1';
const BUYER_PERSONAS: readonly BuyerPersona[] = ['cto', 'finops', 'security', 'cfo'];
const HERO_VARIANTS: readonly HeroVariant[] = ['control_every_dollar', 'from_metrics_to_control'];
const CTA_VARIANTS: readonly CtaVariant[] = ['start_free', 'book_briefing'];
const SECTION_ORDER_VARIANTS: readonly SectionOrderVariant[] = ['problem_first', 'workflow_first'];

const DEFAULT_ASSIGNMENTS: LandingExperimentAssignments = Object.freeze({
	buyerPersonaDefault: 'cto',
	heroVariant: 'control_every_dollar',
	ctaVariant: 'start_free',
	sectionOrderVariant: 'problem_first',
	seed: 'default'
});

function normalizeToken(input: string | null | undefined): string {
	return (input || '').trim().toLowerCase();
}

function parseBuyerPersona(raw: string | null): BuyerPersona | null {
	const token = normalizeToken(raw);
	return (
		(BUYER_PERSONAS.find((candidate) => candidate === token) as BuyerPersona | undefined) ?? null
	);
}

function parseHeroVariant(raw: string | null): HeroVariant | null {
	const token = normalizeToken(raw);
	return (
		(HERO_VARIANTS.find((candidate) => candidate === token) as HeroVariant | undefined) ?? null
	);
}

function parseCtaVariant(raw: string | null): CtaVariant | null {
	const token = normalizeToken(raw);
	return (CTA_VARIANTS.find((candidate) => candidate === token) as CtaVariant | undefined) ?? null;
}

function parseSectionOrderVariant(raw: string | null): SectionOrderVariant | null {
	const token = normalizeToken(raw);
	return (
		(SECTION_ORDER_VARIANTS.find((candidate) => candidate === token) as
			| SectionOrderVariant
			| undefined) ?? null
	);
}

function createVisitorId(now: Date): string {
	const random = Math.floor(Math.random() * 0xffffffff)
		.toString(16)
		.padStart(8, '0');
	const epoch = Math.floor(now.getTime() / 1000)
		.toString(16)
		.padStart(8, '0');
	return `vldx-${epoch}-${random}`;
}

export function resolveOrCreateLandingVisitorId(
	storage?: StorageLike,
	now: Date = new Date()
): string {
	if (storage) {
		const existing = normalizeToken(storage.getItem(VISITOR_ID_STORAGE_KEY));
		if (existing.length >= 10) {
			return existing;
		}
	}

	const created = createVisitorId(now);
	storage?.setItem(VISITOR_ID_STORAGE_KEY, created);
	return created;
}

export function resolveLandingExperiments(
	url: URL,
	visitorId: string
): LandingExperimentAssignments {
	const seed = normalizeToken(visitorId) || DEFAULT_ASSIGNMENTS.seed;

	const buyerPersonaDefault =
		parseBuyerPersona(url.searchParams.get('buyer')) || DEFAULT_ASSIGNMENTS.buyerPersonaDefault;

	const heroVariant =
		parseHeroVariant(url.searchParams.get('exp_hero')) || DEFAULT_ASSIGNMENTS.heroVariant;

	const ctaVariant =
		parseCtaVariant(url.searchParams.get('exp_cta')) || DEFAULT_ASSIGNMENTS.ctaVariant;

	const sectionOrderVariant =
		parseSectionOrderVariant(url.searchParams.get('exp_order')) ||
		DEFAULT_ASSIGNMENTS.sectionOrderVariant;

	return {
		buyerPersonaDefault,
		heroVariant,
		ctaVariant,
		sectionOrderVariant,
		seed
	};
}

export function shouldIncludeExperimentQueryParams(url: URL, isDevBuild = false): boolean {
	if (isDevBuild) return true;
	const token = normalizeToken(url.searchParams.get('qa_exp'));
	return token === '1' || token === 'true';
}
