<script lang="ts">
	interface AIData {
		total_monthly_savings?: string;
		summary?: string;
	}
	export let aiData: AIData | null | undefined;
</script>

{#if aiData}
	<div class="glass-panel stagger-enter col-span-full" style="animation-delay: 200ms;">
		<div class="flex items-center justify-between">
			<div>
				<p class="text-sm text-ink-400 mb-1">Potential Monthly Savings</p>
				<p class="text-5xl font-bold text-gradient">
					{aiData.total_monthly_savings || '$0.00'}
				</p>
				<p class="text-sm text-ink-400 mt-2">
					{aiData.summary || 'Analysis complete.'}
					<span class="block mt-1 font-semibold text-accent-400"
						>Value Optimizer: Continuously eliminating waste and technical debt.</span
					>
				</p>
			</div>
			<div class="hero-icon text-6xl">💰</div>
		</div>
	</div>
{/if}
