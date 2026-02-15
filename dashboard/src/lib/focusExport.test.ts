import { describe, expect, it } from 'vitest';

import { buildFocusExportPath } from './focusExport';

describe('buildFocusExportPath', () => {
	it('builds required params', () => {
		expect(
			buildFocusExportPath({
				startDate: '2026-01-01',
				endDate: '2026-01-31'
			})
		).toBe('/costs/export/focus?start_date=2026-01-01&end_date=2026-01-31');
	});

	it('includes provider and include_preliminary when set', () => {
		expect(
			buildFocusExportPath({
				startDate: '2026-01-01',
				endDate: '2026-01-31',
				provider: 'aws',
				includePreliminary: true
			})
		).toBe(
			'/costs/export/focus?start_date=2026-01-01&end_date=2026-01-31&provider=aws&include_preliminary=true'
		);
	});
});
