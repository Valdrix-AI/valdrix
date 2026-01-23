<script lang="ts">
	/**
	 * PieChart Component using Chart.js
	 * For cost allocation visualization (Allocated vs Unallocated, Team Breakdown)
	 */
	import { onMount, onDestroy } from 'svelte';
	import { Chart, registerables } from 'chart.js';

	Chart.register(...registerables);

	interface ChartDataItem {
		label: string;
		value: number;
		color?: string;
	}

	let {
		data = [],
		title = 'Breakdown',
		height = 300,
		showLegend = true,
		showPercentage = true
	}: {
		data: ChartDataItem[];
		title?: string;
		height?: number;
		showLegend?: boolean;
		showPercentage?: boolean;
	} = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	const defaultColors = [
		'#3b82f6', // blue
		'#10b981', // green
		'#f59e0b', // amber
		'#ef4444', // red
		'#8b5cf6', // purple
		'#ec4899', // pink
		'#06b6d4', // cyan
		'#84cc16', // lime
		'#f97316', // orange
		'#6366f1' // indigo
	];

	function getColor(index: number, itemColor?: string): string {
		return itemColor || defaultColors[index % defaultColors.length];
	}

	function createChart() {
		if (!canvas || data.length === 0) return;

		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		if (chart) {
			chart.destroy();
		}

		const total = data.reduce((sum, item) => sum + item.value, 0);

		chart = new Chart(ctx, {
			type: 'doughnut',
			data: {
				labels: data.map((d) =>
					showPercentage ? `${d.label} (${((d.value / total) * 100).toFixed(1)}%)` : d.label
				),
				datasets: [
					{
						data: data.map((d) => d.value),
						backgroundColor: data.map((d, i) => getColor(i, d.color)),
						borderWidth: 2,
						borderColor: '#1e293b'
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				cutout: '60%',
				plugins: {
					legend: {
						display: showLegend,
						position: 'right',
						labels: {
							color: '#94a3b8',
							font: { size: 12 },
							padding: 16
						}
					},
					tooltip: {
						callbacks: {
							label: (context) => {
								const value = context.parsed;
								const percentage = ((value / total) * 100).toFixed(1);
								return `$${value.toLocaleString()} (${percentage}%)`;
							}
						}
					}
				}
			}
		});
	}

	onMount(() => {
		createChart();
	});

	onDestroy(() => {
		if (chart) {
			chart.destroy();
		}
	});

	// Reactively update chart when data changes
	$effect(() => {
		if (data) {
			createChart();
		}
	});
</script>

<div class="pie-chart-container">
	{#if title}
		<h3 class="chart-title">{title}</h3>
	{/if}
	<div class="chart-wrapper" style="height: {height}px">
		{#if data.length === 0}
			<div class="no-data">No data available</div>
		{:else}
			<canvas bind:this={canvas}></canvas>
		{/if}
	</div>
</div>

<style>
	.pie-chart-container {
		background: var(--card-bg, #0f172a);
		border-radius: 12px;
		padding: 1.5rem;
		border: 1px solid var(--border-color, #1e293b);
	}

	.chart-title {
		font-size: 1rem;
		font-weight: 600;
		color: var(--text-primary, #f8fafc);
		margin: 0 0 1rem 0;
	}

	.chart-wrapper {
		position: relative;
	}

	.no-data {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		color: var(--text-muted, #64748b);
		font-size: 0.875rem;
	}
</style>
