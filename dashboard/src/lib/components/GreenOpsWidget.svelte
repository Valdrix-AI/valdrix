<script lang="ts">
	/**
	 * GreenOps Sustainability Widget
	 * High-ticket ESG metric display for enterprise boards.
	 * Shows estimated CO2 emission savings from idle resource termination.
	 */
	import { Leaf, Zap, TrendingDown } from '@lucide/svelte';

	interface GreenOpsData {
		estimated_savings_kg: number;
		gpu_waste_reduction_kg: number;
		total_avoided_emissions_kg: number;
		equivalence_trees: number;
	}

	let {
		data = {
			estimated_savings_kg: 124.5,
			gpu_waste_reduction_kg: 85.2,
			total_avoided_emissions_kg: 1450.8,
			equivalence_trees: 66
		}
	}: {
		data?: GreenOpsData;
	} = $props();

	function formatKG(kg: number): string {
		if (kg > 1000) return (kg / 1000).toFixed(2) + ' t';
		return kg.toFixed(1) + ' kg';
	}
</script>

<div class="greenops-widget glass-panel stagger-enter" style="animation-delay: 100ms;">
	<div class="header">
		<div class="title-area">
			<div class="icon-wrap">
				<Leaf size={20} color="#4ade80" />
			</div>
			<div>
				<h3>GreenOps Sustainability</h3>
				<p class="subtitle">ESG Performance & Carbon Savings</p>
			</div>
		</div>
		<div class="badge-esg">2026 Ready</div>
	</div>

	<div class="main-metric">
		<div class="metric-label">Estimated CO₂ Avoided</div>
		<div class="metric-value text-gradient">
			{formatKG(data.estimated_savings_kg)}
		</div>
		<div class="metric-trend">
			<TrendingDown size={14} />
			<span>-12% from last month</span>
		</div>
	</div>

	<div class="stats-grid">
		<div class="stat-item">
			<div class="stat-icon"><Zap size={16} class="text-yellow-400" /></div>
			<div class="stat-content">
				<span class="stat-label">GPU Idle Savings</span>
				<span class="stat-value">{formatKG(data.gpu_waste_reduction_kg)}</span>
			</div>
		</div>
		<div class="stat-item">
			<div class="stat-icon"><Leaf size={16} class="text-green-400" /></div>
			<div class="stat-content">
				<span class="stat-label">Tree Equivalence</span>
				<span class="stat-value">{data.equivalence_trees} Trees</span>
			</div>
		</div>
	</div>

	<div class="action-footer">
		<p class="text-xs text-ink-400">
			Valdrics is reducing your carbon footprint by automatically culling idle High-TDP nodes.
		</p>
	</div>
</div>

<style>
	.greenops-widget {
		padding: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1.5rem;
		position: relative;
		overflow: hidden;
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
		width: 40px;
		height: 40px;
		background: rgba(34, 197, 94, 0.1);
		border: 1px solid rgba(34, 197, 94, 0.2);
		border-radius: 10px;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	h3 {
		font-size: 1rem;
		font-weight: 600;
		color: #f8fafc;
		margin: 0;
	}

	.subtitle {
		font-size: var(--text-xs);
		color: #94a3b8;
		margin: 0;
	}

	.badge-esg {
		font-size: var(--text-xs);
		font-weight: 700;
		text-transform: uppercase;
		background: rgba(34, 197, 94, 0.2);
		color: #4ade80;
		padding: 0.25rem 0.5rem;
		border-radius: 999px;
		letter-spacing: 0.05em;
	}

	.main-metric {
		text-align: center;
		padding: 1rem 0;
	}

	.metric-label {
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: #64748b;
		margin-bottom: 0.5rem;
	}

	.metric-value {
		font-size: 3rem;
		font-weight: 800;
		line-height: 1;
		margin-bottom: 0.5rem;
	}

	.metric-trend {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.25rem;
		font-size: var(--text-xs);
		color: #4ade80;
		font-weight: 600;
	}

	.stats-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1rem;
	}

	.stat-item {
		background: rgba(30, 41, 59, 0.5);
		border: 1px solid rgba(51, 65, 85, 0.5);
		border-radius: 12px;
		padding: 0.75rem;
		display: flex;
		gap: 0.75rem;
		align-items: center;
	}

	.stat-content {
		display: flex;
		flex-direction: column;
	}

	.stat-label {
		font-size: var(--text-xs);
		color: #94a3b8;
	}

	.stat-value {
		font-size: 0.875rem;
		font-weight: 700;
		color: #f1f5f9;
	}

	.action-footer {
		border-top: 1px solid rgba(51, 65, 85, 0.5);
		padding-top: 1rem;
		text-align: center;
	}

	.text-gradient {
		background: linear-gradient(135deg, #4ade80 0%, #22c55e 100%);
		background-clip: text;
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
	}
</style>
