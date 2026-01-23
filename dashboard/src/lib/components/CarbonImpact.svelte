<script lang="ts">
	interface CarbonData {
		equivalencies: {
			miles_driven: number | string;
			trees_needed_for_year: number | string;
			smartphone_charges: number | string;
			percent_of_home_month: number | string;
		};
	}
	export let carbon: CarbonData | null | undefined;
</script>

{#if carbon?.equivalencies}
	<div class="card stagger-enter" style="animation-delay: 200ms;">
		<h2 class="text-lg font-semibold mb-5">Carbon Impact</h2>
		<div class="grid gap-6 md:grid-cols-4 text-center">
			<div class="p-4 rounded-lg bg-ink-800/50">
				<p class="text-2xl font-bold text-ink-100">{carbon.equivalencies.miles_driven}</p>
				<p class="text-sm text-ink-400 mt-1">Miles Driven</p>
			</div>
			<div class="p-4 rounded-lg bg-ink-800/50">
				<p class="text-2xl font-bold text-ink-100">{carbon.equivalencies.trees_needed_for_year}</p>
				<p class="text-sm text-ink-400 mt-1">Trees Needed</p>
			</div>
			<div class="p-4 rounded-lg bg-ink-800/50">
				<p class="text-2xl font-bold text-ink-100">{carbon.equivalencies.smartphone_charges}</p>
				<p class="text-sm text-ink-400 mt-1">Phone Charges</p>
			</div>
			<div class="p-4 rounded-lg bg-ink-800/50">
				<p class="text-2xl font-bold text-ink-100">{carbon.equivalencies.percent_of_home_month}%</p>
				<p class="text-sm text-ink-400 mt-1">Of Home/Month</p>
			</div>
		</div>
	</div>
{/if}
