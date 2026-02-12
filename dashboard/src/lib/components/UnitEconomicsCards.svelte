<script lang="ts">
	interface UnitEconomicsMetric {
		metric_key: string;
		label: string;
		cost_per_unit: number;
		baseline_cost_per_unit: number;
		delta_percent: number;
		is_anomalous: boolean;
	}

	interface UnitEconomicsData {
		threshold_percent: number;
		anomaly_count: number;
		metrics: UnitEconomicsMetric[];
	}

	export let unitEconomics: UnitEconomicsData | null | undefined;

	function formatCurrency(value: number): string {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: 'USD',
			maximumFractionDigits: 4
		}).format(value || 0);
	}

	function formatDelta(value: number): string {
		const prefix = value > 0 ? '+' : '';
		return `${prefix}${value.toFixed(2)}%`;
	}

	function deltaClass(metric: UnitEconomicsMetric): string {
		if (metric.is_anomalous || metric.delta_percent > 0) return 'text-danger-400';
		if (metric.delta_percent < 0) return 'text-success-400';
		return 'text-ink-300';
	}
</script>

<div class="space-y-3">
	<div class="flex items-center justify-between">
		<h2 class="text-sm font-semibold uppercase tracking-wide text-ink-400">Unit Economics</h2>
		{#if unitEconomics}
			<span class="text-xs text-ink-500">
				Threshold: {unitEconomics.threshold_percent.toFixed(2)}%
			</span>
		{/if}
	</div>

	{#if unitEconomics && unitEconomics.metrics.length > 0}
		<div class="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
			<div class="card card-stat stagger-enter" style="animation-delay: 0ms;">
				<p class="text-sm text-ink-400 mb-1">Anomalies</p>
				<p
					class={`text-3xl font-bold ${unitEconomics.anomaly_count > 0 ? 'text-danger-400' : 'text-success-400'}`}
				>
					{unitEconomics.anomaly_count}
				</p>
				<p class="text-xs text-ink-500 mt-2">Cost-per-unit alerts</p>
			</div>

			{#each unitEconomics.metrics as metric, i (metric.metric_key)}
				<div class="card card-stat stagger-enter" style="animation-delay: {(i + 1) * 40}ms;">
					<p class="text-sm text-ink-400 mb-1">{metric.label}</p>
					<p class="text-2xl font-bold text-accent-400">{formatCurrency(metric.cost_per_unit)}</p>
					<p class={`text-xs mt-2 ${deltaClass(metric)}`}>
						{formatDelta(metric.delta_percent)} vs baseline ({formatCurrency(metric.baseline_cost_per_unit)})
					</p>
				</div>
			{/each}
		</div>
	{:else}
		<div class="card text-sm text-ink-500">
			Unit economics is not available yet for this date range.
		</div>
	{/if}
</div>
