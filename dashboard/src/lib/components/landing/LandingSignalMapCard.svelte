<script lang="ts">
	import { base } from '$app/paths';
	import { onDestroy } from 'svelte';
	import {
		REALTIME_SIGNAL_SNAPSHOTS,
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

	let signalMapElement: HTMLDivElement | null = $state(null);
	let activeDemoStep = $derived(MICRO_DEMO_STEPS[demoStepIndex] ?? MICRO_DEMO_STEPS[0]);
	let controlDetailsOpen = $state(false);
	let walkthroughOpen = $state(false);
	let activeLaneIndex = $derived(
		Math.max(
			0,
			activeSnapshot.lanes.findIndex((lane) => lane.id === activeSignalLane?.id)
		)
	);
	let chainProgressPct = $derived(
		activeSnapshot.lanes.length > 1
			? Number(((activeLaneIndex / (activeSnapshot.lanes.length - 1)) * 100).toFixed(2))
			: 0
	);
	let capturedAtLabel = $derived(
		new Intl.DateTimeFormat('en-US', {
			month: 'short',
			day: 'numeric',
			year: 'numeric',
			timeZone: 'UTC'
		}).format(new Date(activeSnapshot.capturedAt))
	);
	let sourcePreview = $derived(activeSnapshot.sources.slice(0, 2).join(' • '));
	let sourceCountLabel = $derived(
		`${activeSnapshot.sources.length} source input${activeSnapshot.sources.length === 1 ? '' : 's'}`
	);

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
	<div class="glass-panel landing-preview-card" id="signal-map-card">
		<div class="landing-preview-header">
			<div class="landing-preview-title">
				<span class="landing-live-dot" aria-hidden="true"></span>
				Live Decision Loop
			</div>
			<span class="landing-preview-pill">{activeSnapshot.label}</span>
		</div>

		<p class="signal-state-headline">{activeSnapshot.headline}</p>
		<p class="signal-state-sub">{activeSnapshot.decisionSummary}</p>

		<div class="signal-map" class:is-paused={!signalMapInView} bind:this={signalMapElement}>
			<div
				class="approval-chain-shell"
				style={`--approval-progress:${chainProgressPct}%;`}
				aria-describedby="signal-map-summary"
			>
				<div class="approval-chain-atmosphere" aria-hidden="true">
					<div class="approval-chain-orbit">
						<div class="approval-chain-orbit-ring approval-chain-orbit-ring--outer"></div>
						<div class="approval-chain-orbit-ring approval-chain-orbit-ring--inner"></div>
						<div class="approval-chain-orbit-core">
							<span>Valdrics</span>
							<strong>Control core</strong>
						</div>
					</div>
					<div class="approval-chain-spoke approval-chain-spoke--nw"></div>
					<div class="approval-chain-spoke approval-chain-spoke--ne"></div>
					<div class="approval-chain-spoke approval-chain-spoke--se"></div>
					<div class="approval-chain-spoke approval-chain-spoke--sw"></div>
					{#each activeSnapshot.lanes as lane, index (lane.id)}
						<div
							class={`approval-chain-orbit-node ${laneSeverityClass(lane.severity)} ${activeSignalLane?.id === lane.id ? 'is-active' : ''}`}
							style={`--approval-node:${activeSnapshot.lanes.length > 1 ? (index / (activeSnapshot.lanes.length - 1)) * 100 : 0}%;`}
						></div>
					{/each}
				</div>

				<div class="approval-chain-record-row">
					<article class="approval-chain-record-card" aria-label="Active decision record">
						<p class="approval-chain-record-k">Decision record</p>
						<p class="approval-chain-record-v">{activeSnapshot.traceId}</p>
						<p class="approval-chain-record-m">{activeSnapshot.decisionSummary}</p>
						<p class="approval-chain-record-note">Inputs: {sourcePreview}</p>
					</article>

					<div class="approval-chain-meta-grid" aria-hidden="true">
						<div class="approval-chain-meta-cell">
							<span>Captured</span>
							<strong>{capturedAtLabel}</strong>
						</div>
						<div class="approval-chain-meta-cell">
							<span>Current gate</span>
							<strong>{activeSignalLane?.title ?? activeSnapshot.lanes[0]?.title}</strong>
						</div>
						<div class="approval-chain-meta-cell">
							<span>Linked proof</span>
							<strong>{sourceCountLabel}</strong>
						</div>
					</div>
				</div>

				<div class="approval-chain-rail" aria-hidden="true">
					<div class="approval-chain-rail-line"></div>
					<div class="approval-chain-rail-progress"></div>
					<div class="approval-chain-packet"></div>
					{#each activeSnapshot.lanes as lane, index (lane.id)}
						<div
							class={`approval-chain-rail-stop ${laneSeverityClass(lane.severity)} ${activeSignalLane?.id === lane.id ? 'is-active' : ''}`}
							style={`--approval-stop:${activeSnapshot.lanes.length > 1 ? (index / (activeSnapshot.lanes.length - 1)) * 100 : 0}%;`}
						></div>
					{/each}
				</div>

				<div class="approval-chain-stage-grid">
					{#each activeSnapshot.lanes as lane, index (lane.id)}
						<button
							type="button"
							class={`approval-chain-stage ${laneSeverityClass(lane.severity)} ${activeSignalLane?.id === lane.id ? 'is-active' : ''}`}
							onclick={() => {
								controlDetailsOpen = true;
								onSelectSignalLane(lane.id);
							}}
							aria-label={`Inspect ${lane.title} step`}
						>
							<div class="approval-chain-stage-meta">
								<span class="approval-chain-stage-index">
									{String(index + 1).padStart(2, '0')}
								</span>
								<span class="approval-chain-stage-status">{lane.status}</span>
							</div>
							<p class="approval-chain-stage-title">{lane.title}</p>
							<p class="approval-chain-stage-metric">{lane.metric}</p>
							<p class="approval-chain-stage-subtitle">{lane.subtitle}</p>
							{#if lane.wasteUsd}
								<div class="impact-badge" class:is-watch={lane.severity === 'watch'}>
									${lane.wasteUsd.toLocaleString()} waste
								</div>
							{/if}
						</button>
					{/each}
				</div>

				<div id="signal-map-summary" class="sr-only">
					Approval chain summary for {activeSnapshot.label}: {activeSnapshot.headline}
					{activeSnapshot.decisionSummary} This view shows one decision record moving through scoped
					signals, checks, approvals, and recorded outcomes.
				</div>
			</div>
		</div>

		<div class="signal-summary-row">
			{#if activeSignalLane}
				<p class="signal-summary-text">
					Active step: <strong>{activeSignalLane.title}</strong> ({activeSignalLane.status})
				</p>
			{/if}
			<button
				type="button"
				class="signal-details-toggle"
				aria-expanded={controlDetailsOpen}
				aria-controls="signal-control-details"
				onclick={() => {
					const nextState = !controlDetailsOpen;
					controlDetailsOpen = nextState;
					if (!nextState) {
						walkthroughOpen = false;
					}
				}}
			>
				{controlDetailsOpen ? 'Hide approval chain' : 'Open approval chain'}
			</button>
		</div>

		{#if controlDetailsOpen}
			<div id="signal-control-details">
				<div class="signal-lane-controls" role="tablist" aria-label="Approval chain step details">
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
						data-testid="signal-lane-panel"
					>
						<p class="signal-lane-detail-k">{activeSignalLane.title} · {activeSignalLane.status}</p>
						<p class="signal-lane-detail-v">{activeSignalLane.detail}</p>
						<div class="signal-lane-detail-footer">
							<p class="signal-lane-detail-m">Current metric: {activeSignalLane.metric}</p>
							{#if activeSignalLane.actionLabel}
								<a
									href={`${base}/auth/login?intent=demo_action`}
									class="demo-action-btn"
									role="button"
									style="text-decoration: none;"
								>
									{activeSignalLane.actionLabel}
								</a>
							{/if}
						</div>
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

				<div class="signal-walkthrough-row">
					<p class="signal-walkthrough-text">Want the approval-chain walkthrough?</p>
					<button
						type="button"
						class="signal-details-toggle signal-details-toggle--secondary"
						aria-expanded={walkthroughOpen}
						aria-controls="signal-guided-walkthrough"
						onclick={() => {
							walkthroughOpen = !walkthroughOpen;
						}}
					>
						{walkthroughOpen
							? 'Hide approval chain walkthrough'
							: 'Open approval chain walkthrough'}
					</button>
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

				{#if walkthroughOpen}
					<div
						id="signal-guided-walkthrough"
						class="landing-demo-strip"
						aria-label="Guided product moment"
					>
						<p class="landing-demo-k">20-second approval chain walkthrough</p>
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
				{/if}
			</div>
		{/if}
	</div>
</div>
