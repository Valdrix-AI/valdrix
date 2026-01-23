<script lang="ts">
	/**
	 * AllocationBreakdown Component
	 * Displays cost allocation by team/bucket with pie chart and table
	 * Series-A Due Diligence: Dashboard visualization for attribution
	 */
	import PieChart from './PieChart.svelte';
	import { Users, AlertTriangle } from '@lucide/svelte';

	interface AllocationBucket {
		name: string;
		total_amount: number;
		record_count: number;
		color?: string;
		percentage?: number;
	}

	interface AllocationData {
		buckets: AllocationBucket[];
		total: number;
	}

	let {
		data,
		loading = false,
		error = null
	}: {
		data: AllocationData | null;
		loading?: boolean;
		error?: string | null;
	} = $props();

	// Calculate percentages for each bucket
	let bucketsWithPercentage = $derived(() => {
		if (!data?.buckets) return [];
		return data.buckets.map((bucket) => ({
			...bucket,
			percentage: data.total > 0 ? (bucket.total_amount / data.total) * 100 : 0
		}));
	});

	// Separate allocated vs unallocated for summary
	let allocatedTotal = $derived(() => {
		if (!data?.buckets) return 0;
		return data.buckets
			.filter((b) => b.name !== 'Unallocated')
			.reduce((sum, b) => sum + b.total_amount, 0);
	});

	let unallocatedTotal = $derived(() => {
		if (!data?.buckets) return 0;
		const unallocated = data.buckets.find((b) => b.name === 'Unallocated');
		return unallocated?.total_amount || 0;
	});

	let unallocatedPercentage = $derived(() => {
		if (!data?.total || data.total === 0) return 0;
		return (unallocatedTotal() / data.total) * 100;
	});

	// Format chart data
	let chartData = $derived(() => {
		if (!data?.buckets) return [];
		return data.buckets.map((bucket) => ({
			label: bucket.name,
			value: bucket.total_amount,
			color: bucket.color
		}));
	});

	function formatCurrency(amount: number): string {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: 'USD',
			minimumFractionDigits: 2,
			maximumFractionDigits: 2
		}).format(amount);
	}
</script>

<div class="allocation-breakdown">
	<div class="header">
		<h2>
			<Users class="icon" />
			Cost Allocation by Team
		</h2>
		{#if unallocatedPercentage() > 5}
			<div class="warning-badge">
				<AlertTriangle class="icon-sm" />
				{unallocatedPercentage().toFixed(1)}% Unallocated
			</div>
		{/if}
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<span>Loading allocation data...</span>
		</div>
	{:else if error}
		<div class="error-state">
			<AlertTriangle class="icon" />
			<span>{error}</span>
		</div>
	{:else if !data || data.buckets.length === 0}
		<div class="empty-state">
			<Users class="icon-lg" />
			<h3>No Allocation Data</h3>
			<p>Create attribution rules to see cost breakdown by team.</p>
		</div>
	{:else}
		<div class="content-grid">
			<!-- Pie Chart -->
			<div class="chart-section">
				<PieChart data={chartData()} title="Allocated vs Unallocated" height={280} />
			</div>

			<!-- Summary Cards -->
			<div class="summary-section">
				<div class="summary-card allocated">
					<div class="summary-label">Allocated</div>
					<div class="summary-value">{formatCurrency(allocatedTotal())}</div>
					<div class="summary-percent">{(100 - unallocatedPercentage()).toFixed(1)}%</div>
				</div>

				<div class="summary-card unallocated" class:warning={unallocatedPercentage() > 5}>
					<div class="summary-label">Unallocated</div>
					<div class="summary-value">{formatCurrency(unallocatedTotal())}</div>
					<div class="summary-percent">{unallocatedPercentage().toFixed(1)}%</div>
				</div>
			</div>

			<!-- Breakdown Table -->
			<div class="table-section">
				<h3>Team Breakdown</h3>
				<table>
					<thead>
						<tr>
							<th>Team / Bucket</th>
							<th>Amount</th>
							<th>Records</th>
							<th>% of Total</th>
						</tr>
					</thead>
					<tbody>
						{#each bucketsWithPercentage() as bucket (bucket.name)}
							<tr class:unallocated={bucket.name === 'Unallocated'}>
								<td class="bucket-name">
									<span class="color-dot" style="background: {bucket.color || '#64748b'}"></span>
									{bucket.name}
								</td>
								<td class="amount">{formatCurrency(bucket.total_amount)}</td>
								<td class="count">{bucket.record_count.toLocaleString()}</td>
								<td class="percent">
									<div class="percent-bar">
										<div class="percent-fill" style="width: {bucket.percentage}%"></div>
										<span>{bucket.percentage?.toFixed(1)}%</span>
									</div>
								</td>
							</tr>
						{/each}
					</tbody>
					<tfoot>
						<tr>
							<td>Total</td>
							<td class="amount">{formatCurrency(data.total)}</td>
							<td class="count"
								>{data.buckets.reduce((s, b) => s + b.record_count, 0).toLocaleString()}</td
							>
							<td class="percent">100%</td>
						</tr>
					</tfoot>
				</table>
			</div>
		</div>
	{/if}
</div>

<style>
	.allocation-breakdown {
		background: var(--card-bg, #0f172a);
		border-radius: 16px;
		padding: 1.5rem;
		border: 1px solid var(--border-color, #1e293b);
	}

	.header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 1.5rem;
	}

	.header h2 {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary, #f8fafc);
		margin: 0;
	}

	.icon {
		width: 20px;
		height: 20px;
	}
	.icon-sm {
		width: 14px;
		height: 14px;
	}
	.icon-lg {
		width: 48px;
		height: 48px;
		color: #64748b;
	}

	.warning-badge {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		background: #fef3c7;
		color: #92400e;
		padding: 0.375rem 0.75rem;
		border-radius: 999px;
		font-size: 0.75rem;
		font-weight: 500;
	}

	.content-grid {
		display: grid;
		gap: 1.5rem;
	}

	@media (min-width: 768px) {
		.content-grid {
			grid-template-columns: 1fr 1fr;
			grid-template-rows: auto auto;
		}
		.table-section {
			grid-column: 1 / -1;
		}
	}

	.summary-section {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.summary-card {
		background: #1e293b;
		border-radius: 12px;
		padding: 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.summary-card.warning {
		background: linear-gradient(135deg, #7c2d12 0%, #1e293b 100%);
	}

	.summary-label {
		font-size: 0.75rem;
		text-transform: uppercase;
		color: #94a3b8;
		letter-spacing: 0.05em;
	}

	.summary-value {
		font-size: 1.5rem;
		font-weight: 700;
		color: #f8fafc;
	}

	.summary-percent {
		font-size: 0.875rem;
		color: #64748b;
	}

	.table-section h3 {
		font-size: 0.875rem;
		font-weight: 600;
		color: #f8fafc;
		margin: 0 0 1rem 0;
	}

	table {
		width: 100%;
		border-collapse: collapse;
	}

	th,
	td {
		padding: 0.75rem;
		text-align: left;
		border-bottom: 1px solid #1e293b;
	}

	th {
		font-size: 0.75rem;
		text-transform: uppercase;
		color: #64748b;
		font-weight: 500;
	}

	td {
		font-size: 0.875rem;
		color: #f8fafc;
	}

	.bucket-name {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.color-dot {
		width: 10px;
		height: 10px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.amount {
		font-weight: 600;
		font-variant-numeric: tabular-nums;
	}
	.count {
		color: #94a3b8;
	}

	.percent-bar {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.percent-fill {
		height: 6px;
		background: #3b82f6;
		border-radius: 3px;
		max-width: 100px;
	}

	tr.unallocated td {
		color: #f59e0b;
	}

	tfoot td {
		font-weight: 600;
		border-top: 2px solid #334155;
	}

	.loading-state,
	.error-state,
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 3rem;
		color: #94a3b8;
		text-align: center;
		gap: 1rem;
	}

	.empty-state h3 {
		margin: 0;
		color: #f8fafc;
	}

	.empty-state p {
		margin: 0;
		font-size: 0.875rem;
	}

	.spinner {
		width: 32px;
		height: 32px;
		border: 3px solid #1e293b;
		border-top-color: #3b82f6;
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
