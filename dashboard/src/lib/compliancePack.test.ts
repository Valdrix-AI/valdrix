import { describe, expect, it } from 'vitest';

import { buildCompliancePackPath } from './compliancePack';

describe('buildCompliancePackPath', () => {
	it('returns base path when no options set', () => {
		expect(buildCompliancePackPath()).toBe('/audit/compliance-pack');
	});

	it('includes focus export options when enabled', () => {
		expect(
			buildCompliancePackPath({
				includeFocusExport: true,
				focusStartDate: '2026-01-01',
				focusEndDate: '2026-01-31',
				focusProvider: 'aws',
				focusIncludePreliminary: true,
				focusMaxRows: 123
			})
		).toBe(
			'/audit/compliance-pack?include_focus_export=true&focus_provider=aws&focus_include_preliminary=true&focus_max_rows=123&focus_start_date=2026-01-01&focus_end_date=2026-01-31'
		);
	});

	it('includes savings + close add-ons when enabled', () => {
		expect(
			buildCompliancePackPath({
				includeSavingsProof: true,
				savingsStartDate: '2026-01-01',
				savingsEndDate: '2026-01-31',
				savingsProvider: 'gcp',
				includeClosePackage: true,
				closeStartDate: '2026-01-01',
				closeEndDate: '2026-01-31',
				closeProvider: 'aws',
				closeEnforceFinalized: false,
				closeMaxRestatements: 0
			})
		).toBe(
			'/audit/compliance-pack?include_savings_proof=true&savings_provider=gcp&savings_start_date=2026-01-01&savings_end_date=2026-01-31&include_close_package=true&close_provider=aws&close_start_date=2026-01-01&close_end_date=2026-01-31&close_enforce_finalized=false&close_max_restatements=0'
		);
	});
});
