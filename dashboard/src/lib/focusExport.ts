export type FocusExportParams = {
	startDate: string;
	endDate: string;
	provider?: string;
	includePreliminary?: boolean;
};

export function buildFocusExportPath(params: FocusExportParams): string {
	const qp = new URLSearchParams({
		start_date: params.startDate,
		end_date: params.endDate
	});
	if (params.provider) {
		const trimmed = params.provider.trim();
		if (trimmed) qp.set('provider', trimmed);
	}
	if (params.includePreliminary) {
		qp.set('include_preliminary', 'true');
	}
	return `/costs/export/focus?${qp.toString()}`;
}
