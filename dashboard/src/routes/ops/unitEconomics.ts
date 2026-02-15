export type UnitEconomicsMetricView = {
	delta_percent: number;
	is_anomalous: boolean;
};

export function toIsoDate(value: Date): string {
	return value.toISOString().slice(0, 10);
}

export function defaultDateWindow(
	days: number,
	now: Date = new Date()
): { start: string; end: string } {
	const end = new Date(now);
	end.setUTCHours(0, 0, 0, 0);

	const start = new Date(end);
	start.setUTCDate(start.getUTCDate() - Math.max(days - 1, 0));
	return { start: toIsoDate(start), end: toIsoDate(end) };
}

export function hasInvalidUnitWindow(startDate: string, endDate: string): boolean {
	return startDate > endDate;
}

export function formatDelta(delta: number): string {
	const sign = delta > 0 ? '+' : '';
	return `${sign}${delta.toFixed(2)}%`;
}

export function unitDeltaClass(metric: UnitEconomicsMetricView): string {
	if (metric.is_anomalous || metric.delta_percent > 0) return 'text-danger-400 font-semibold';
	if (metric.delta_percent < 0) return 'text-success-400 font-semibold';
	return 'text-ink-300';
}

export function buildUnitEconomicsUrl(
	apiBaseUrl: string,
	startDate: string,
	endDate: string,
	alertOnAnomaly: boolean
): string {
	const params = new URLSearchParams({
		start_date: startDate,
		end_date: endDate,
		alert_on_anomaly: alertOnAnomaly ? 'true' : 'false'
	});
	return `${apiBaseUrl}/costs/unit-economics?${params.toString()}`;
}
