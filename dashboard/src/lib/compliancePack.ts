export type CompliancePackOptions = {
	includeFocusExport?: boolean;
	focusProvider?: string;
	focusIncludePreliminary?: boolean;
	focusMaxRows?: number;
	focusStartDate?: string;
	focusEndDate?: string;

	includeSavingsProof?: boolean;
	savingsProvider?: string;
	savingsStartDate?: string;
	savingsEndDate?: string;

	includeClosePackage?: boolean;
	closeProvider?: string;
	closeStartDate?: string;
	closeEndDate?: string;
	closeEnforceFinalized?: boolean;
	closeMaxRestatements?: number;
};

function setIfPresent(params: URLSearchParams, key: string, value: string | undefined) {
	if (typeof value !== 'string') return;
	const trimmed = value.trim();
	if (!trimmed) return;
	params.set(key, trimmed);
}

export function buildCompliancePackPath(options: CompliancePackOptions = {}): string {
	const params = new URLSearchParams();

	if (options.includeFocusExport) {
		params.set('include_focus_export', 'true');
		setIfPresent(params, 'focus_provider', options.focusProvider);
		if (options.focusIncludePreliminary) params.set('focus_include_preliminary', 'true');
		if (typeof options.focusMaxRows === 'number' && Number.isFinite(options.focusMaxRows)) {
			params.set('focus_max_rows', String(Math.max(1, Math.floor(options.focusMaxRows))));
		}
		setIfPresent(params, 'focus_start_date', options.focusStartDate);
		setIfPresent(params, 'focus_end_date', options.focusEndDate);
	}

	if (options.includeSavingsProof) {
		params.set('include_savings_proof', 'true');
		setIfPresent(params, 'savings_provider', options.savingsProvider);
		setIfPresent(params, 'savings_start_date', options.savingsStartDate);
		setIfPresent(params, 'savings_end_date', options.savingsEndDate);
	}

	if (options.includeClosePackage) {
		params.set('include_close_package', 'true');
		setIfPresent(params, 'close_provider', options.closeProvider);
		setIfPresent(params, 'close_start_date', options.closeStartDate);
		setIfPresent(params, 'close_end_date', options.closeEndDate);
		if (options.closeEnforceFinalized === false) params.set('close_enforce_finalized', 'false');
		if (
			typeof options.closeMaxRestatements === 'number' &&
			Number.isFinite(options.closeMaxRestatements)
		) {
			params.set(
				'close_max_restatements',
				String(Math.max(0, Math.floor(options.closeMaxRestatements)))
			);
		}
	}

	const query = params.toString();
	return query ? `/audit/compliance-pack?${query}` : '/audit/compliance-pack';
}
