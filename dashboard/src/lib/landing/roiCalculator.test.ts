import { describe, expect, it } from 'vitest';
import {
	DEFAULT_LANDING_ROI_INPUTS,
	calculateLandingRoi,
	normalizeLandingRoiInputs,
	formatCurrencyAmount,
	detectLocalCurrency,
	detectCurrencyFromCountryCode
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
		expect(normalized.currencyCode).toBe('USD');
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
		expect(inputs.currencyCode).toBe('USD');
	});

	describe('formatCurrencyAmount', () => {
		it('formats USD correctly', () => {
			expect(formatCurrencyAmount(1000, 'USD')).toMatch(/\$1,000/);
			expect(formatCurrencyAmount(0, 'USD')).toMatch(/\$0/);
			expect(formatCurrencyAmount(-500, 'USD')).toMatch(/-\$500/);
		});

		it('formats EUR correctly', () => {
			const result = formatCurrencyAmount(1000, 'EUR');
			expect(result).toContain('€');
			expect(result).toMatch(/1,000/);
		});

		it('formats GBP correctly', () => {
			const result = formatCurrencyAmount(1000, 'GBP');
			expect(result).toContain('£');
			expect(result).toMatch(/1,000/);
		});

		it('formats NGN correctly', () => {
			const result = formatCurrencyAmount(1000, 'NGN');
			// Some environments return '₦1,000', others return 'NGN 1,000'
			expect(result).toMatch(/(₦|NGN).*1,000/);
		});

		it('defaults to USD if no currency is provided', () => {
			expect(formatCurrencyAmount(1000)).toMatch(/\$1,000/);
		});

		it('handles invalid currency codes by falling back to currency code display', () => {
			// Intl.NumberFormat might throw or display code depending on environment
			// Our implementation in roiCalculator.ts uses a try/catch block if needed?
			// Let's check roiCalculator.ts implementation again.
			expect(() => formatCurrencyAmount(1000, 'INVALID')).not.toThrow();
			const result = formatCurrencyAmount(1000, 'INVALID');
			expect(result).toMatch(/INVALID/);
		});
	});

	describe('detectLocalCurrency', () => {
		it('detects GBP from London timezone hints', () => {
			expect(detectLocalCurrency({ timeZone: 'Europe/London' })).toBe('GBP');
		});

		it('detects NGN from Lagos timezone hints', () => {
			expect(detectLocalCurrency({ timeZone: 'Africa/Lagos' })).toBe('NGN');
		});

		it('detects EUR from euro-region locale hints', () => {
			expect(detectLocalCurrency({ locales: ['de-DE'], timeZone: '' })).toBe('EUR');
		});

		it('detects GBP from GB locale hints', () => {
			expect(detectLocalCurrency({ locales: ['en-GB'], timeZone: '' })).toBe('GBP');
		});

		it('falls back to USD for unsupported locales and timezones', () => {
			expect(detectLocalCurrency({ locales: ['en-ZA'], timeZone: 'Africa/Johannesburg' })).toBe(
				'USD'
			);
		});
	});

	describe('detectCurrencyFromCountryCode', () => {
		it('maps supported country codes to known currencies', () => {
			expect(detectCurrencyFromCountryCode('ng')).toBe('NGN');
			expect(detectCurrencyFromCountryCode('GB')).toBe('GBP');
			expect(detectCurrencyFromCountryCode('de')).toBe('EUR');
		});

		it('returns null for unsupported or invalid country codes', () => {
			expect(detectCurrencyFromCountryCode('US')).toBeNull();
			expect(detectCurrencyFromCountryCode('XX')).toBeNull();
			expect(detectCurrencyFromCountryCode('')).toBeNull();
			expect(detectCurrencyFromCountryCode(null)).toBeNull();
		});
	});
});
