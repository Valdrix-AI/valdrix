import { describe, expect, it } from 'vitest';
import {
	DEFAULT_LANDING_ROI_INPUTS,
	calculateLandingRoi,
	normalizeLandingRoiInputs
} from './roiCalculator';

describe('roiCalculator', () => {
	it('normalizes and clamps invalid inputs', () => {
		const normalized = normalizeLandingRoiInputs({
			monthlySpendUsd: -10,
			expectedReductionPct: 200,
			rolloutDays: 1,
			teamMembers: 99,
			blendedHourlyUsd: 1,
			platformAnnualCostUsd: -300
		});

		expect(normalized.monthlySpendUsd).toBe(5000);
		expect(normalized.expectedReductionPct).toBe(60);
		expect(normalized.rolloutDays).toBe(7);
		expect(normalized.teamMembers).toBe(12);
		expect(normalized.blendedHourlyUsd).toBe(50);
		expect(normalized.platformAnnualCostUsd).toBe(0);
	});

	it('calculates deterministic ROI outputs for default inputs', () => {
		const result = calculateLandingRoi(DEFAULT_LANDING_ROI_INPUTS);
		expect(result.monthlySavingsUsd).toBe(14400);
		expect(result.annualGrossSavingsUsd).toBe(172800);
		expect(result.implementationCostUsd).toBe(79200);
		expect(result.annualNetSavingsUsd).toBe(93600);
		expect(result.paybackDays).toBe(165);
		expect(result.roiMultiple).toBe(2.18);
	});

	it('returns zero ROI and no payback when savings are zero', () => {
		const inputs = normalizeLandingRoiInputs({
			monthlySpendUsd: 5000,
			expectedReductionPct: 1,
			rolloutDays: 180,
			teamMembers: 12,
			blendedHourlyUsd: 400,
			platformAnnualCostUsd: 100000
		});
		const result = calculateLandingRoi(inputs);
		expect(result.monthlySavingsUsd).toBe(50);
		expect(result.annualGrossSavingsUsd).toBe(600);
		expect(result.implementationCostUsd).toBe(7012000);
		expect(result.annualNetSavingsUsd).toBeLessThan(0);
		expect(result.paybackDays).toBeGreaterThan(1000);
		expect(result.roiMultiple).toBe(0);
	});
});
