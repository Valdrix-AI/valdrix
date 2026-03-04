export interface LandingRoiInputs {
	monthlySpendUsd: number;
	expectedReductionPct: number;
	rolloutDays: number;
	teamMembers: number;
	blendedHourlyUsd: number;
	platformAnnualCostUsd: number;
	currencyCode: string;
}

export interface LandingRoiResult {
	monthlySavingsUsd: number;
	annualGrossSavingsUsd: number;
	implementationCostUsd: number;
	annualNetSavingsUsd: number;
	paybackDays: number | null;
	roiMultiple: number;
}

export const DEFAULT_LANDING_ROI_INPUTS: LandingRoiInputs = Object.freeze({
	monthlySpendUsd: 120000,
	expectedReductionPct: 12,
	rolloutDays: 30,
	teamMembers: 2,
	blendedHourlyUsd: 145,
	platformAnnualCostUsd: 9600,
	currencyCode: 'USD'
});

export const SUPPORTED_CURRENCIES = Object.freeze([
	{ code: 'USD', label: 'USD ($)', symbol: '$' },
	{ code: 'EUR', label: 'EUR (€)', symbol: '€' },
	{ code: 'GBP', label: 'GBP (£)', symbol: '£' },
	{ code: 'NGN', label: 'NGN (₦)', symbol: '₦' }
]);

const EURO_REGION_CODES = new Set([
	'AT',
	'BE',
	'CY',
	'DE',
	'EE',
	'ES',
	'FI',
	'FR',
	'GR',
	'HR',
	'IE',
	'IT',
	'LT',
	'LU',
	'LV',
	'MT',
	'NL',
	'PT',
	'SI',
	'SK'
]);

function dedupeStrings(values: readonly string[]): string[] {
	return [...new Set(values.map((value) => value.trim()).filter(Boolean))];
}

function regionFromLocale(locale: string): string | null {
	const normalized = locale.trim();
	if (!normalized) return null;
	const parts = normalized.split('-');
	if (parts.length < 2) return null;
	const region = parts[parts.length - 1];
	if (!region) return null;
	return region.toUpperCase();
}

function currencyFromRegion(region: string | null): string | null {
	if (!region) return null;
	if (region === 'NG') return 'NGN';
	if (region === 'GB') return 'GBP';
	if (EURO_REGION_CODES.has(region)) return 'EUR';
	return null;
}

export function detectCurrencyFromCountryCode(countryCode: string | null | undefined): string | null {
	if (!countryCode) return null;
	const normalizedCountryCode = countryCode.trim().toUpperCase();
	if (!normalizedCountryCode || normalizedCountryCode === 'XX') return null;
	return currencyFromRegion(normalizedCountryCode);
}

function currencyFromTimeZone(timeZone: string): string | null {
	const normalized = timeZone.trim();
	if (!normalized) return null;
	if (normalized === 'Europe/London') return 'GBP';
	if (normalized === 'Africa/Lagos') return 'NGN';
	if (normalized.startsWith('Europe/')) return 'EUR';
	return null;
}

export function detectLocalCurrency(hints?: {
	locales?: readonly string[];
	timeZone?: string | null;
}): string {
	const supportedCurrencyCodes = new Set(SUPPORTED_CURRENCIES.map((currency) => currency.code));
	const defaultCurrency = 'USD';

	const resolvedTimeZone =
		hints?.timeZone ??
		(typeof Intl !== 'undefined' && typeof Intl.DateTimeFormat === 'function'
			? Intl.DateTimeFormat().resolvedOptions().timeZone
			: '');
	const timeZoneCurrency = currencyFromTimeZone(String(resolvedTimeZone || ''));
	if (timeZoneCurrency && supportedCurrencyCodes.has(timeZoneCurrency)) {
		return timeZoneCurrency;
	}

	const localeCandidates: string[] = [];
	if (hints?.locales?.length) {
		localeCandidates.push(...hints.locales);
	}
	if (typeof navigator !== 'undefined') {
		if (Array.isArray(navigator.languages) && navigator.languages.length > 0) {
			localeCandidates.push(...navigator.languages);
		}
		if (typeof navigator.language === 'string' && navigator.language) {
			localeCandidates.push(navigator.language);
		}
	}
	if (typeof Intl !== 'undefined' && typeof Intl.NumberFormat === 'function') {
		try {
			localeCandidates.push(new Intl.NumberFormat().resolvedOptions().locale);
		} catch {
			// Continue with other hints.
		}
	}

	for (const locale of dedupeStrings(localeCandidates)) {
		const regionCurrency = detectCurrencyFromCountryCode(regionFromLocale(locale));
		if (regionCurrency && supportedCurrencyCodes.has(regionCurrency)) {
			return regionCurrency;
		}
	}

	return defaultCurrency;
}

function clamp(value: number, min: number, max: number): number {
	if (!Number.isFinite(value)) return min;
	return Math.min(max, Math.max(min, value));
}

function roundCurrency(value: number): number {
	if (!Number.isFinite(value)) return 0;
	return Math.round(value * 100) / 100;
}

/**
 * Deterministically formats currency values based on supported FX Engine locales.
 * Defaults to USD. Fallbacks properly if an unknown currency is passed.
 *
 * Supported currencies reflect the backend ExchangeRateService targets.
 */
export function formatCurrencyAmount(amount: number, currencyCode: string = 'USD'): string {
	const safeAmount = Number.isFinite(amount) ? amount : 0;

	try {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: currencyCode,
			maximumFractionDigits: 0,
			minimumFractionDigits: 0
		}).format(safeAmount);
	} catch (e) {
		// Fallback for unsupported currency codes, deterministic
		return `${currencyCode} ${safeAmount.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
	}
}

export function normalizeLandingRoiInputs(
	inputs: Partial<LandingRoiInputs> | undefined
): LandingRoiInputs {
	return {
		monthlySpendUsd: clamp(
			Number(inputs?.monthlySpendUsd ?? DEFAULT_LANDING_ROI_INPUTS.monthlySpendUsd),
			5000,
			5000000
		),
		expectedReductionPct: clamp(
			Number(inputs?.expectedReductionPct ?? DEFAULT_LANDING_ROI_INPUTS.expectedReductionPct),
			1,
			60
		),
		rolloutDays: clamp(
			Number(inputs?.rolloutDays ?? DEFAULT_LANDING_ROI_INPUTS.rolloutDays),
			7,
			180
		),
		teamMembers: clamp(
			Number(inputs?.teamMembers ?? DEFAULT_LANDING_ROI_INPUTS.teamMembers),
			1,
			12
		),
		blendedHourlyUsd: clamp(
			Number(inputs?.blendedHourlyUsd ?? DEFAULT_LANDING_ROI_INPUTS.blendedHourlyUsd),
			50,
			400
		),
		platformAnnualCostUsd: clamp(
			Number(inputs?.platformAnnualCostUsd ?? DEFAULT_LANDING_ROI_INPUTS.platformAnnualCostUsd),
			0,
			100000
		),
		currencyCode: inputs?.currencyCode || DEFAULT_LANDING_ROI_INPUTS.currencyCode
	};
}

export function calculateLandingRoi(inputs: LandingRoiInputs): LandingRoiResult {
	const monthlySavingsUsd = roundCurrency(
		(inputs.monthlySpendUsd * inputs.expectedReductionPct) / 100
	);
	const annualGrossSavingsUsd = roundCurrency(monthlySavingsUsd * 12);
	const implementationCostUsd = roundCurrency(
		inputs.platformAnnualCostUsd +
			inputs.rolloutDays * 8 * inputs.teamMembers * inputs.blendedHourlyUsd
	);
	const annualNetSavingsUsd = roundCurrency(annualGrossSavingsUsd - implementationCostUsd);
	const paybackDays =
		monthlySavingsUsd > 0 ? Math.ceil((implementationCostUsd / monthlySavingsUsd) * 30) : null;
	const roiMultiple =
		implementationCostUsd > 0 ? roundCurrency(annualGrossSavingsUsd / implementationCostUsd) : 0;

	return {
		monthlySavingsUsd,
		annualGrossSavingsUsd,
		implementationCostUsd,
		annualNetSavingsUsd,
		paybackDays,
		roiMultiple
	};
}
