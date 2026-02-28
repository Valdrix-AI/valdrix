<script lang="ts">
	/**
	 * Cloud Distribution Matrix (Donut Chart)
	 * Visualizes cloud waste across AWS vs Azure vs GCP.
	 * Proves Multi-Cloud power at a glance.
	 */
	import PieChart from './PieChart.svelte';
	import { Globe } from '@lucide/svelte';

	interface WasteData {
		label: string;
		value: number;
		color: string;
	}

	let {
		data = [
			{ label: 'AWS', value: 4200, color: '#f97316' },
			{ label: 'Azure', value: 2800, color: '#3b82f6' },
			{ label: 'GCP', value: 1500, color: '#facc15' }
		]
	}: {
		data?: WasteData[];
	} = $props();

	let totalWaste = $derived(data.reduce((sum, item) => sum + item.value, 0));

	function formatCurrency(amount: number): string {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: 'USD',
			maximumFractionDigits: 0
		}).format(amount);
	}
</script>

<div class="distribution-matrix glass-panel stagger-enter" style="animation-delay: 200ms;">
	<div class="header">
		<div class="title-area">
			<div class="icon-wrap">
				<Globe size={18} color="#60a5fa" />
			</div>
			<div>
				<h3>Cloud Waste Distribution</h3>
				<p class="subtitle">Multi-Cloud Inefficiency Matrix</p>
			</div>
		</div>
	</div>

	<div class="chart-container">
		<PieChart {data} title="" height={220} showLegend={false} />
		<div class="chart-center">
			<div class="center-label">Total Waste</div>
			<div class="center-value">{formatCurrency(totalWaste)}</div>
		</div>
	</div>

	<div class="legend-grid">
		{#each data as item (item.label)}
			<div class="legend-item">
				<div class="item-header">
					<span class="dot" style="background: {item.color}"></span>
					<span class="label">{item.label}</span>
				</div>
				<div class="item-value">{formatCurrency(item.value)}</div>
				<div class="item-percent">
					{((item.value / totalWaste) * 100).toFixed(0)}%
				</div>
			</div>
		{/each}
	</div>
</div>

<style>
	.distribution-matrix {
		padding: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.title-area {
		display: flex;
		gap: 0.75rem;
		align-items: center;
	}

	.icon-wrap {
		width: 36px;
		height: 36px;
		background: rgba(59, 130, 246, 0.1);
		border: 1px solid rgba(59, 130, 246, 0.2);
		border-radius: 8px;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	h3 {
		font-size: 0.9375rem;
		font-weight: 600;
		color: #f8fafc;
		margin: 0;
	}

	.subtitle {
		font-size: var(--text-xs);
		color: #94a3b8;
		margin: 0;
	}

	.chart-container {
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.chart-center {
		position: absolute;
		text-align: center;
		pointer-events: none;
	}

	.center-label {
		font-size: var(--text-xs);
		text-transform: uppercase;
		color: #64748b;
		letter-spacing: 0.05em;
	}

	.center-value {
		font-size: 1.25rem;
		font-weight: 700;
		color: #f8fafc;
	}

	.legend-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 1rem;
		padding-top: 1rem;
		border-top: 1px solid rgba(51, 65, 85, 0.4);
	}

	.legend-item {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.item-header {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
	}

	.label {
		font-size: var(--text-xs);
		font-weight: 600;
		color: #f1f5f9;
	}

	.item-value {
		font-size: 0.8125rem;
		font-weight: 700;
		color: #f8fafc;
	}

	.item-percent {
		font-size: var(--text-xs);
		color: #64748b;
		background: rgba(30, 41, 59, 0.5);
		padding: 0.125rem 0.375rem;
		border-radius: 4px;
		width: fit-content;
	}
</style>
