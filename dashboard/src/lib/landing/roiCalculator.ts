export interface LandingRoiInputs {
	monthlySpendUsd: number;
	expectedReductionPct: number;
	rolloutDays: number;
	teamMembers: number;
	blendedHourlyUsd: number;
	platformAnnualCostUsd: number;
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
	platformAnnualCostUsd: 9600
});

function clamp(value: number, min: number, max: number): number {
	if (!Number.isFinite(value)) return min;
	return Math.min(max, Math.max(min, value));
}

function roundCurrency(value: number): number {
	if (!Number.isFinite(value)) return 0;
	return Math.round(value * 100) / 100;
}

export function normalizeLandingRoiInputs(
	inputs: Partial<LandingRoiInputs> | undefined
): LandingRoiInputs {
	return {
		monthlySpendUsd: clamp(Number(inputs?.monthlySpendUsd ?? DEFAULT_LANDING_ROI_INPUTS.monthlySpendUsd), 5000, 5000000),
		expectedReductionPct: clamp(
			Number(inputs?.expectedReductionPct ?? DEFAULT_LANDING_ROI_INPUTS.expectedReductionPct),
			1,
			60
		),
		rolloutDays: clamp(Number(inputs?.rolloutDays ?? DEFAULT_LANDING_ROI_INPUTS.rolloutDays), 7, 180),
		teamMembers: clamp(Number(inputs?.teamMembers ?? DEFAULT_LANDING_ROI_INPUTS.teamMembers), 1, 12),
		blendedHourlyUsd: clamp(
			Number(inputs?.blendedHourlyUsd ?? DEFAULT_LANDING_ROI_INPUTS.blendedHourlyUsd),
			50,
			400
		),
		platformAnnualCostUsd: clamp(
			Number(inputs?.platformAnnualCostUsd ?? DEFAULT_LANDING_ROI_INPUTS.platformAnnualCostUsd),
			0,
			100000
		)
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
		implementationCostUsd > 0
			? roundCurrency(annualGrossSavingsUsd / implementationCostUsd)
			: 0;

	return {
		monthlySavingsUsd,
		annualGrossSavingsUsd,
		implementationCostUsd,
		annualNetSavingsUsd,
		paybackDays,
		roiMultiple
	};
}
