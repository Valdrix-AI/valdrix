<script lang="ts">
	import { onDestroy } from 'svelte';
	import {
		REALTIME_SIGNAL_SNAPSHOTS,
		lanePositionPercent,
		laneSeverityClass,
		type SignalLaneId,
		type SignalLaneSnapshot,
		type SignalSnapshot
	} from '$lib/landing/realtimeSignalMap';
	import { MICRO_DEMO_STEPS, SIGNAL_VALUE_CARDS } from '$lib/landing/heroContent';

	let {
		activeSnapshot,
		activeSignalLane,
		signalMapInView,
		snapshotIndex,
		demoStepIndex,
		onSelectSignalLane,
		onSelectDemoStep,
		onSelectSnapshot,
		onSignalMapElementChange
	}: {
		activeSnapshot: SignalSnapshot;
		activeSignalLane: SignalLaneSnapshot | undefined;
		signalMapInView: boolean;
		snapshotIndex: number;
		demoStepIndex: number;
		onSelectSignalLane: (laneId: SignalLaneId) => void;
		onSelectDemoStep: (index: number) => void;
		onSelectSnapshot: (index: number) => void;
		onSignalMapElementChange: (element: HTMLDivElement | null) => void;
	} = $props();

	const landingGridX = [...Array(13).keys()];
	const landingGridY = [...Array(9).keys()];

	let signalMapElement: HTMLDivElement | null = $state(null);
	let activeDemoStep = $derived(MICRO_DEMO_STEPS[demoStepIndex] ?? MICRO_DEMO_STEPS[0]);

	$effect(() => {
		onSignalMapElementChange(signalMapElement);
	});

	onDestroy(() => {
		onSignalMapElementChange(null);
	});

	function stepProgressWidth(index: number): number {
		if (demoStepIndex > index) return 100;
		if (demoStepIndex < index) return 0;
		return 62;
	}
</script>

<div class="landing-preview fade-in-up" style="animation-delay: 170ms;">
	<div class="glass-panel landing-preview-card" id="signal-map">
		<div class="landing-preview-header">
			<div class="landing-preview-title">
				<span class="landing-live-dot" aria-hidden="true"></span>
				Realtime Signal Map
			</div>
			<span class="landing-preview-pill">{activeSnapshot.label}</span>
		</div>

		<p class="signal-state-headline">{activeSnapshot.headline}</p>
		<p class="signal-state-sub">{activeSnapshot.decisionSummary}</p>

		<div class="signal-map" class:is-paused={!signalMapInView} bind:this={signalMapElement}>
			<svg class="signal-svg" viewBox="0 0 640 420" role="img" aria-labelledby="signal-map-summary">
				<defs>
					<linearGradient id="sigLine" x1="0" y1="0" x2="1" y2="1">
						<stop offset="0" stop-color="var(--color-accent-400)" stop-opacity="0.95" />
						<stop offset="1" stop-color="var(--color-success-400)" stop-opacity="0.72" />
					</linearGradient>
					<radialGradient id="sigGlow" cx="50%" cy="50%" r="60%">
						<stop offset="0" stop-color="var(--color-accent-400)" stop-opacity="0.32" />
						<stop offset="1" stop-color="var(--color-accent-400)" stop-opacity="0" />
					</radialGradient>
				</defs>

				<rect x="0" y="0" width="640" height="420" fill="rgba(0,0,0,0)" />
				<g class="sig-grid">
					{#each landingGridX as xIndex (xIndex)}
						<line x1={xIndex * 54} y1="0" x2={xIndex * 54} y2="420" />
					{/each}
					{#each landingGridY as yIndex (yIndex)}
						<line x1="0" y1={yIndex * 52} x2="640" y2={yIndex * 52} />
					{/each}
				</g>

				<circle cx="320" cy="210" r="160" fill="url(#sigGlow)" />

				{#each activeSnapshot.lanes as lane (lane.id)}
					<line
						class={`sig-link ${laneSeverityClass(lane.severity)}`}
						x1="320"
						y1="210"
						x2={lane.x}
						y2={lane.y}
						stroke="url(#sigLine)"
						stroke-width="2"
						stroke-linecap="round"
						stroke-dasharray="6 10"
					/>
				{/each}

				<circle class="sig-node sig-node--center" cx="320" cy="210" r="12" />
				{#each activeSnapshot.lanes as lane (lane.id)}
					<circle
						class={`sig-node ${laneSeverityClass(lane.severity)} ${activeSignalLane?.id === lane.id ? 'is-focused' : ''}`}
						cx={lane.x}
						cy={lane.y}
						r="8"
					/>
				{/each}
			</svg>

			<div class="signal-label signal-label--center" aria-hidden="true">
				<p class="signal-label-k">Valdrics</p>
				<p class="signal-label-v">Economic Control Plane</p>
			</div>
			{#each activeSnapshot.lanes as lane (lane.id)}
				{@const lanePoint = lanePositionPercent(lane)}
				<button
					type="button"
					class="signal-hotspot"
					class:is-active={activeSignalLane?.id === lane.id}
					style={`left:${lanePoint.leftPct}%; top:${lanePoint.topPct}%;`}
					onclick={() => onSelectSignalLane(lane.id)}
					aria-label={`Open ${lane.title} lane detail`}
				></button>
			{/each}

			<div id="signal-map-summary" class="sr-only">
				Signal map summary for {activeSnapshot.label}: {activeSnapshot.headline}
				{activeSnapshot.decisionSummary} This view highlights clarity, control, and confidence signals
				for owner-led execution.
			</div>
		</div>

		<div class="signal-lane-controls" role="tablist" aria-label="Realtime signal lane details">
			{#each activeSnapshot.lanes as lane (lane.id)}
				<button
					type="button"
					role="tab"
					id={`signal-lane-tab-${lane.id}`}
					class="signal-lane-btn"
					class:is-active={activeSignalLane?.id === lane.id}
					aria-selected={activeSignalLane?.id === lane.id}
					aria-controls={`signal-lane-panel-${lane.id}`}
					onclick={() => onSelectSignalLane(lane.id)}
				>
					<span class="signal-lane-btn-title">{lane.title}</span>
					<span class="signal-lane-btn-status">{lane.status}</span>
				</button>
			{/each}
		</div>

		{#if activeSignalLane}
			<div
				class="signal-lane-detail-panel"
				role="tabpanel"
				id={`signal-lane-panel-${activeSignalLane.id}`}
				aria-labelledby={`signal-lane-tab-${activeSignalLane.id}`}
			>
				<p class="signal-lane-detail-k">{activeSignalLane.title} · {activeSignalLane.status}</p>
				<p class="signal-lane-detail-v">{activeSignalLane.detail}</p>
				<p class="signal-lane-detail-m">Current metric: {activeSignalLane.metric}</p>
			</div>
		{/if}

		<div class="landing-metrics" aria-live="polite">
			{#each SIGNAL_VALUE_CARDS as card (card.label)}
				<div class="landing-metric glass-card">
					<p class="landing-metric-k">{card.label}</p>
					<p class="landing-metric-v">{card.value}</p>
					<p class="landing-metric-h">{card.hint}</p>
				</div>
			{/each}
		</div>

		<div class="landing-demo-strip" aria-label="Guided product moment">
			<p class="landing-demo-k">20-second guided control walkthrough</p>
			<div class="landing-demo-visual" aria-hidden="true">
				{#each MICRO_DEMO_STEPS as step, index (step.id)}
					<div class="landing-demo-visual-step">
						<div
							class="landing-demo-visual-dot"
							class:is-active={demoStepIndex === index}
							class:is-complete={demoStepIndex > index}
						></div>
						<div class="landing-demo-visual-meta">
							<p>{step.title}</p>
							<div class="landing-demo-visual-track">
								<span style={`width:${stepProgressWidth(index)}%;`}></span>
							</div>
						</div>
					</div>
				{/each}
			</div>
			<div class="landing-demo-steps" role="group" aria-label="Control loop demo steps">
				{#each MICRO_DEMO_STEPS as step, index (step.id)}
					<button
						type="button"
						class="landing-demo-step"
						class:is-active={demoStepIndex === index}
						onclick={() => onSelectDemoStep(index)}
						aria-pressed={demoStepIndex === index}
					>
						{step.title}
					</button>
				{/each}
			</div>
			<p class="landing-demo-detail">{activeDemoStep.detail}</p>
		</div>

		<div class="signal-snapshot-controls" role="group" aria-label="Switch signal snapshots">
			{#each REALTIME_SIGNAL_SNAPSHOTS as snapshot, index (snapshot.id)}
				<button
					type="button"
					class="signal-snapshot-btn"
					class:is-active={snapshotIndex === index}
					onclick={() => onSelectSnapshot(index)}
					aria-pressed={snapshotIndex === index}
				>
					{snapshot.label}
				</button>
			{/each}
		</div>
	</div>
</div>
