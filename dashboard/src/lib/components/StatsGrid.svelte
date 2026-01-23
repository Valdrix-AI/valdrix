<script lang="ts">
	interface CostData {
		total_cost: number;
	}
	interface CarbonData {
		total_co2_kg: number;
	}
	export let costs: CostData | null | undefined;
	export let carbon: CarbonData | null | undefined;
	export let zombieCount: number;
	export let totalMonthlyWaste: number;
	export let periodLabel: string;
</script>

<div class="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
	<!-- Period Cost -->
	<div class="card card-stat stagger-enter" style="animation-delay: 0ms;">
		<p class="text-sm text-ink-400 mb-1">{periodLabel} Cost</p>
		<p class="text-3xl font-bold" style="color: var(--color-accent-400);">
			${costs?.total_cost?.toFixed(2) ?? '0.00'}
		</p>
		<p class="text-xs text-ink-500 mt-2">vs last period</p>
	</div>

	<!-- Carbon Footprint -->
	<div class="card card-stat stagger-enter" style="animation-delay: 50ms;">
		<p class="text-sm text-ink-400 mb-1">Carbon Footprint</p>
		<p class="text-3xl font-bold" style="color: var(--color-success-400);">
			{carbon?.total_co2_kg?.toFixed(2) ?? '0.00'} kg
		</p>
		<p class="text-xs text-ink-500 mt-2">CO₂ emissions</p>
	</div>

	<!-- Zombie Resources -->
	<div class="card card-stat stagger-enter" style="animation-delay: 100ms;">
		<p class="text-sm text-ink-400 mb-1">Zombie Resources</p>
		<p class="text-3xl font-bold" style="color: var(--color-warning-400);">
			{zombieCount}
		</p>
		<p class="text-xs text-ink-500 mt-2">Unused resources found</p>
	</div>

	<!-- Monthly Waste -->
	<div class="card card-stat stagger-enter" style="animation-delay: 150ms;">
		<p class="text-sm text-ink-400 mb-1">Monthly Waste</p>
		<p class="text-3xl font-bold" style="color: var(--color-danger-400);">
			${totalMonthlyWaste?.toFixed(2) ?? '0.00'}
		</p>
		<p class="text-xs text-ink-500 mt-2">Potential savings</p>
	</div>
</div>
