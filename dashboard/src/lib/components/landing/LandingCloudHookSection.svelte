<script lang="ts">
	type HookMetric = {
		label: string;
		value: string;
	};

	type CloudHookState = {
		id: string;
		title: string;
		subtitle: string;
		ahaMoment: string;
		points: readonly string[];
		metrics: readonly HookMetric[];
	};

	let {
		activeHookState,
		hookStateIndex,
		cloudHookStates,
		onSelectHookState
	}: {
		activeHookState: CloudHookState;
		hookStateIndex: number;
		cloudHookStates: readonly CloudHookState[];
		onSelectHookState: (index: number) => void;
	} = $props();
</script>

<section
	id="cloud-hook"
	class="container mx-auto px-6 pb-16 landing-section-lazy"
	data-landing-section="cloud_hook"
>
	<div class="landing-hook glass-panel">
		<p class="landing-proof-k">The Cloud Cost Trap</p>
		<h2 class="landing-h2">Visibility alone does not control cloud spend.</h2>
		<p class="landing-section-sub">
			Most teams find waste post-invoice. Valdrics links each spend signal to an owner, safety
			checks, and approved action in one loop.
		</p>

		<div class="landing-hook-highlight">
			<p class="landing-hook-highlight-k">Aha Moment</p>
			<p class="landing-hook-highlight-v">
				{activeHookState.ahaMoment}
			</p>
		</div>

		<div class="landing-hook-switch" role="group" aria-label="Compare cloud operations">
			{#each cloudHookStates as state, index (state.id)}
				<button
					type="button"
					class="landing-hook-switch-btn"
					class:is-active={hookStateIndex === index}
					onclick={() => onSelectHookState(index)}
					aria-pressed={hookStateIndex === index}
				>
					{state.title}
				</button>
			{/each}
		</div>

		<div class="landing-hook-scene" class:is-with={activeHookState.id === 'with'}>
			<p class="landing-hook-sub">{activeHookState.subtitle}</p>
			<ul class="landing-hook-list">
				{#each activeHookState.points as point (point)}
					<li>{point}</li>
				{/each}
			</ul>
			<div class="landing-hook-metrics">
				{#each activeHookState.metrics as metric (metric.label)}
					<div class="landing-hook-metric">
						<p class="landing-hook-metric-k">{metric.label}</p>
						<p class="landing-hook-metric-v">{metric.value}</p>
					</div>
				{/each}
			</div>
		</div>
	</div>
</section>
