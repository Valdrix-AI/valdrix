<script lang="ts">
	import { onDestroy } from 'svelte';
	import {
		REALTIME_SIGNAL_SNAPSHOTS,
		laneSeverityClass,
		SIGNAL_MAP_VIEWBOX,
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
	const SIGNAL_CENTER = Object.freeze({ x: 320, y: 210 });
	const LANE_ANCHOR_NUDGE: Readonly<Record<SignalLaneId, { x: number; y: number }>> = Object.freeze(
		{
			economic_visibility: { x: -40, y: -30 },
			deterministic_enforcement: { x: 40, y: -30 },
			financial_governance: { x: 40, y: 30 },
			operational_resilience: { x: -40, y: 30 }
		}
	);

	const LABEL_TRANSLATE: Readonly<Record<SignalLaneId, string>> = Object.freeze({
		economic_visibility: 'transform: translate(-100%, -50%) translateX(-12px);',
		deterministic_enforcement: 'transform: translate(0, -50%) translateX(12px);',
		financial_governance: 'transform: translate(0, -50%) translateX(12px);',
		operational_resilience: 'transform: translate(-100%, -50%) translateX(-12px);'
	});

	let signalMapElement: HTMLDivElement | null = $state(null);
	let signalMapWidth = $state(0);
	let signalMapHeight = $state(0);
	let activeDemoStep = $derived(MICRO_DEMO_STEPS[demoStepIndex] ?? MICRO_DEMO_STEPS[0]);
	let controlDetailsOpen = $state(false);
	let walkthroughOpen = $state(false);

	$effect(() => {
		onSignalMapElementChange(signalMapElement);
	});

	$effect(() => {
		if (!signalMapElement) {
			signalMapWidth = 0;
			signalMapHeight = 0;
			return;
		}

		const refreshDimensions = () => {
			if (!signalMapElement) return;
			const rect = signalMapElement.getBoundingClientRect();
			signalMapWidth = rect.width;
			signalMapHeight = rect.height;
		};

		refreshDimensions();

		if (typeof ResizeObserver !== 'undefined') {
			const resizeObserver = new ResizeObserver(() => {
				refreshDimensions();
			});
			resizeObserver.observe(signalMapElement);
			return () => {
				resizeObserver.disconnect();
			};
		}

		if (typeof window !== 'undefined') {
			window.addEventListener('resize', refreshDimensions);
			return () => {
				window.removeEventListener('resize', refreshDimensions);
			};
		}
	});

	onDestroy(() => {
		onSignalMapElementChange(null);
	});

	function stepProgressWidth(index: number): number {
		if (demoStepIndex > index) return 100;
		if (demoStepIndex < index) return 0;
		return 62;
	}

	function resolveSvgProjection():
		| {
				scale: number;
				offsetX: number;
				offsetY: number;
		  }
		| undefined {
		if (signalMapWidth <= 0 || signalMapHeight <= 0) {
			return undefined;
		}
		const scale = Math.min(
			signalMapWidth / SIGNAL_MAP_VIEWBOX.width,
			signalMapHeight / SIGNAL_MAP_VIEWBOX.height
		);
		const renderedWidth = SIGNAL_MAP_VIEWBOX.width * scale;
		const renderedHeight = SIGNAL_MAP_VIEWBOX.height * scale;
		return {
			scale,
			offsetX: (signalMapWidth - renderedWidth) / 2,
			offsetY: (signalMapHeight - renderedHeight) / 2
		};
	}

	function resolveLaneAnchor(lane: SignalLaneSnapshot): { x: number; y: number } {
		const nudge = LANE_ANCHOR_NUDGE[lane.id];
		return {
			x: Math.min(622, Math.max(18, lane.x + nudge.x)),
			y: Math.min(402, Math.max(18, lane.y + nudge.y))
		};
	}

	function resolveFlowEndpoint(lane: SignalLaneSnapshot): { x: number; y: number } {
		return resolveLaneAnchor(lane);
	}

	function resolveHotspotPoint(point: {
		x: number;
		y: number;
	}): { leftPx: number; topPx: number } | undefined {
		const projection = resolveSvgProjection();
		if (!projection) {
			return undefined;
		}
		return {
			leftPx: projection.offsetX + point.x * projection.scale,
			topPx: projection.offsetY + point.y * projection.scale
		};
	}
</script>

<div class="landing-preview fade-in-up" style="animation-delay: 170ms;">
	<div class="glass-panel landing-preview-card" id="signal-map-card">
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
					{@const flowEndpoint = resolveFlowEndpoint(lane)}
					<line
						class={`sig-link ${laneSeverityClass(lane.severity)}`}
						x1={SIGNAL_CENTER.x}
						y1={SIGNAL_CENTER.y}
						x2={flowEndpoint.x}
						y2={flowEndpoint.y}
						stroke-width="2"
						stroke-linecap="round"
						stroke-dasharray="6 10"
					/>
				{/each}

				<circle class="sig-node sig-node--center" cx="320" cy="210" r="12" />
				{#each activeSnapshot.lanes as lane (lane.id)}
					{@const laneAnchor = resolveLaneAnchor(lane)}
					<circle
						class={`sig-node ${laneSeverityClass(lane.severity)} ${activeSignalLane?.id === lane.id ? 'is-focused' : ''}`}
						cx={laneAnchor.x}
						cy={laneAnchor.y}
						r="8"
					/>
				{/each}
			</svg>

			<div class="signal-label signal-label--center" aria-hidden="true">
				<p class="signal-label-k">Valdrics</p>
				<p class="signal-label-v">Economic Control Plane</p>
			</div>
			{#each activeSnapshot.lanes as lane (lane.id)}
				{@const laneAnchor = resolveLaneAnchor(lane)}
				{@const labelPoint = resolveHotspotPoint(laneAnchor)}
				{#if labelPoint}
					<div
						class={`signal-label ${lane.labelClass}`}
						aria-hidden="true"
						style={`left:${labelPoint.leftPx}px; top:${labelPoint.topPx}px; ${LABEL_TRANSLATE[lane.id]}`}
					>
						<p class="signal-label-k">{lane.title}</p>
						<p class="signal-label-v">{lane.status} · {lane.metric}</p>
						{#if lane.wasteUsd}
							<div class="impact-badge" class:is-watch={lane.severity === 'watch'}>
								${lane.wasteUsd.toLocaleString()} waste
							</div>
						{/if}
					</div>
				{/if}
			{/each}
			{#each activeSnapshot.lanes as lane (lane.id)}
				{@const laneAnchor = resolveLaneAnchor(lane)}
				{@const lanePoint = resolveHotspotPoint(laneAnchor)}
				{#if lanePoint}
					<button
						type="button"
						class="signal-hotspot"
						class:is-active={activeSignalLane?.id === lane.id}
						style={`left:${lanePoint.leftPx}px; top:${lanePoint.topPx}px;`}
						onclick={() => {
							controlDetailsOpen = true;
							onSelectSignalLane(lane.id);
						}}
						aria-label={`Open ${lane.title} lane detail`}
					></button>
				{/if}
			{/each}

			<div id="signal-map-summary" class="sr-only">
				Signal map summary for {activeSnapshot.label}: {activeSnapshot.headline}
				{activeSnapshot.decisionSummary} This view highlights clarity, control, and confidence signals
				for owner-led execution.
			</div>
		</div>

		<div class="signal-summary-row">
			{#if activeSignalLane}
				<p class="signal-summary-text">
					Focus lane: <strong>{activeSignalLane.title}</strong> ({activeSignalLane.status})
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
				{controlDetailsOpen ? 'Hide control details' : 'Explore control details'}
			</button>
		</div>

		{#if controlDetailsOpen}
			<div id="signal-control-details">
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
						data-testid="signal-lane-panel"
					>
						<p class="signal-lane-detail-k">{activeSignalLane.title} · {activeSignalLane.status}</p>
						<p class="signal-lane-detail-v">{activeSignalLane.detail}</p>
						<div class="signal-lane-detail-footer">
							<p class="signal-lane-detail-m">Current metric: {activeSignalLane.metric}</p>
							{#if activeSignalLane.actionLabel}
								<a
									href="/auth/login?intent=demo_action"
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
					<p class="signal-walkthrough-text">Need a quick product walkthrough?</p>
					<button
						type="button"
						class="signal-details-toggle signal-details-toggle--secondary"
						aria-expanded={walkthroughOpen}
						aria-controls="signal-guided-walkthrough"
						onclick={() => {
							walkthroughOpen = !walkthroughOpen;
						}}
					>
						{walkthroughOpen ? 'Hide walkthrough' : 'Open 20-second walkthrough'}
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
				{/if}
			</div>
		{/if}
	</div>
</div>
