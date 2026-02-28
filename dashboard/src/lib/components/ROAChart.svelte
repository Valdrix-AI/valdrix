<script lang="ts">
	/**
	 * 12-Month ROA (Return on Automation) Chart
	 * Projection chart showing cumulative savings over time.
	 * Proves "Compound Value" to investors.
	 */
	import { onMount, onDestroy } from 'svelte';
	import { Activity, TrendingUp } from '@lucide/svelte';
	import { loadChartJs } from '$lib/chartjs';

	let canvas: HTMLCanvasElement;
	let chart: import('chart.js').Chart | null = null;

	const labels = [
		'Jan',
		'Feb',
		'Mar',
		'Apr',
		'May',
		'Jun',
		'Jul',
		'Aug',
		'Sep',
		'Oct',
		'Nov',
		'Dec'
	];

	// Simulated cumulative savings data (Compound Value)
	const savingsData = [
		1200, 2500, 3900, 5400, 7100, 9000, 11200, 13700, 16500, 19600, 23000, 26800
	];

	async function createChart() {
		if (!canvas) return;
		if (typeof window === 'undefined') return;

		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		const { Chart } = await loadChartJs();
		if (chart) chart.destroy();

		chart = new Chart(ctx, {
			type: 'line',
			data: {
				labels,
				datasets: [
					{
						label: 'Cumulative Savings (USD)',
						data: savingsData,
						borderColor: '#3b82f6',
						backgroundColor: 'rgba(59, 130, 246, 0.1)',
						borderWidth: 3,
						fill: true,
						tension: 0.4,
						pointRadius: 4,
						pointBackgroundColor: '#3b82f6',
						pointBorderColor: '#0f172a',
						pointBorderWidth: 2
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: { display: false },
					tooltip: {
						mode: 'index',
						intersect: false,
						callbacks: {
							label: (context) => `$${context.parsed.y?.toLocaleString() || '0'}`
						}
					}
				},
				scales: {
					x: {
						grid: { display: false },
						ticks: { color: '#64748b', font: { size: 10 } }
					},
					y: {
						grid: { color: 'rgba(51, 65, 85, 0.2)' },
						ticks: {
							color: '#64748b',
							font: { size: 10 },
							callback: (value) => `$${(value as number) / 1000}k`
						}
					}
				}
			}
		});
	}

	onMount(() => {
		void createChart();
	});
	onDestroy(() => {
		if (chart) chart.destroy();
	});
</script>

<div class="roa-chart glass-panel stagger-enter" style="animation-delay: 300ms;">
	<div class="header">
		<div class="title-area">
			<div class="icon-wrap">
				<Activity size={18} color="#a78bfa" />
			</div>
			<div>
				<h3>12-Month ROA</h3>
				<p class="subtitle">Return on Automation Projection</p>
			</div>
		</div>
		<div class="growth-stats">
			<TrendingUp size={14} class="text-green-400" />
			<span class="growth-value">+22% MoM</span>
		</div>
	</div>

	<div class="chart-wrapper">
		<canvas bind:this={canvas}></canvas>
	</div>

	<div class="footer">
		<div class="footer-item">
			<span class="label">Projected EOY Savings</span>
			<span class="value text-accent-400">$26,800</span>
		</div>
		<div class="footer-item">
			<span class="label">Automation Score</span>
			<span class="value text-green-400">94/100</span>
		</div>
	</div>
</div>

<style>
	.roa-chart {
		padding: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		min-height: 380px;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
	}

	.title-area {
		display: flex;
		gap: 0.75rem;
		align-items: center;
	}

	.icon-wrap {
		width: 36px;
		height: 36px;
		background: rgba(139, 92, 246, 0.1);
		border: 1px solid rgba(139, 92, 246, 0.2);
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

	.growth-stats {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		background: rgba(34, 197, 94, 0.1);
		padding: 0.25rem 0.5rem;
		border-radius: 6px;
	}

	.growth-value {
		font-size: var(--text-xs);
		font-weight: 700;
		color: #4ade80;
	}

	.chart-wrapper {
		flex: 1;
		min-height: 200px;
		position: relative;
	}

	.footer {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1rem;
		padding-top: 1rem;
		border-top: 1px solid rgba(51, 65, 85, 0.4);
	}

	.footer-item {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.label {
		font-size: var(--text-xs);
		text-transform: uppercase;
		color: #64748b;
		letter-spacing: 0.05em;
	}

	.value {
		font-size: 1.125rem;
		font-weight: 700;
	}
</style>
