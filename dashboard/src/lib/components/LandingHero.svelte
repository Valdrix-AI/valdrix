<script lang="ts">
	import { browser } from '$app/environment';
	import { assets, base } from '$app/paths';
	import { page } from '$app/stores';
	import { onDestroy, onMount } from 'svelte';
	import {
		REALTIME_SIGNAL_SNAPSHOTS,
		lanePositionPercent,
		laneSeverityClass,
		nextSnapshotIndex,
		type SignalLaneId
	} from '$lib/landing/realtimeSignalMap';
	import { emitLandingTelemetry } from '$lib/landing/landingTelemetry';
	import {
		resolveLandingExperiments,
		resolveOrCreateLandingVisitorId,
		shouldIncludeExperimentQueryParams,
		type BuyerPersona,
		type LandingExperimentAssignments
	} from '$lib/landing/landingExperiment';
	import {
		captureLandingAttribution,
		incrementLandingFunnelStage,
		type FunnelStage,
		type LandingAttribution
	} from '$lib/landing/landingFunnel';

	const DEFAULT_EXPERIMENT_ASSIGNMENTS: LandingExperimentAssignments = Object.freeze({
		buyerPersonaDefault: 'cto',
		heroVariant: 'control_every_dollar',
		ctaVariant: 'start_free',
		sectionOrderVariant: 'problem_first',
		seed: 'default'
	});

	const HERO_ROLE_CONTEXT: Record<
		BuyerPersona,
		{
			controlTitle: string;
			metricsTitle: string;
			subtitle: string;
			primaryIntent: string;
		}
	> = Object.freeze({
		cto: {
			controlTitle: 'Control cloud and software spend without slowing delivery.',
			metricsTitle: 'From spend metrics to controlled engineering decisions.',
			subtitle: 'Keep teams shipping while preventing surprise overruns and fire-drill escalations.',
			primaryIntent: 'engineering_control'
		},
		finops: {
			controlTitle: 'Control every dollar with accountable ownership.',
			metricsTitle: 'From visibility dashboards to governed financial action.',
			subtitle: 'Spot spend shifts early, assign owners fast, and close actions before month-end.',
			primaryIntent: 'finops_governance'
		},
		security: {
			controlTitle: 'Control economic risk with policy-first execution.',
			metricsTitle: 'From cost anomalies to policy-enforced remediation.',
			subtitle:
				'Reduce risky changes and keep teams aligned on safe execution across production environments.',
			primaryIntent: 'security_governance'
		},
		cfo: {
			controlTitle: 'Control cloud margin risk before it reaches the boardroom.',
			metricsTitle: 'From cloud metrics to executive-grade economic control.',
			subtitle: 'Protect gross margin with clearer ownership, faster decisions, and fewer budget surprises.',
			primaryIntent: 'executive_briefing'
		}
	});

	const HERO_PROOF_POINTS = Object.freeze([
		{
			title: 'Shared Clarity',
			detail: 'Platform, finance, and leadership use one decision context.'
		},
		{
			title: 'Controlled Execution',
			detail: 'No destructive action runs without policy checks and explicit approval.'
		},
		{
			title: 'Executive Confidence',
			detail: 'Every action path is explainable during review and planning cycles.'
		}
	]);

	const SIGNAL_VALUE_CARDS = Object.freeze([
		{
			label: 'Clarity',
			value: 'See what changed and why',
			hint: 'Cloud spend, anomaly, and workload signals in one operational view.'
		},
		{
			label: 'Ownership',
			value: 'Know who decides next',
			hint: 'Clear responsibility across platform, finance, and leadership.'
		},
		{
			label: 'Confidence',
			value: 'Explain decisions quickly',
			hint: 'Teams stay aligned during finance, audit, and leadership reviews.'
		}
	]);

	const MICRO_DEMO_STEPS = Object.freeze([
		{
			id: 'detect',
			title: 'Detect',
			detail: 'Realtime cloud anomaly is detected and scoped to impacted workloads.'
		},
		{
			id: 'govern',
			title: 'Govern',
			detail: 'Policy checks and entitlement rules evaluate blast radius before execution.'
		},
		{
			id: 'approve',
			title: 'Approve',
			detail: 'Accountable owner approves with explicit decision context and controls.'
		},
		{
			id: 'prove',
			title: 'Prove',
			detail: 'Outcome and evidence are captured for finance and executive review.'
		}
	]);

	const CLOUD_HOOK_STATES = Object.freeze([
		{
			id: 'without',
			title: 'Without Valdrics',
			subtitle: 'Reactive cloud cost operations',
			ahaMoment: 'Anomalies surface late, ownership is unclear, and teams react under pressure.',
			points: [
				'Spend spikes are discovered after the billing cycle.',
				'Remediation ownership is ambiguous across teams.',
				'Cost actions execute without consistent policy controls.'
			],
			metrics: [
				{ label: 'Signal Lag', value: 'After invoice close' },
				{ label: 'Decision Owner', value: 'Unclear' },
				{ label: 'Execution Safety', value: 'Inconsistent' }
			]
		},
		{
			id: 'with',
			title: 'With Valdrics',
			subtitle: 'Controlled cloud economics',
			ahaMoment:
				'Anomaly detected, owner assigned, policy checked, and action approved in one flow.',
			points: [
				'Realtime anomalies route to an explicit accountable owner.',
				'Execution controls enforce policy checks before any change.',
				'Every decision path is exportable for finance and leadership.'
			],
			metrics: [
				{ label: 'Signal Lag', value: 'Realtime' },
				{ label: 'Decision Owner', value: 'Explicit' },
				{ label: 'Execution Safety', value: 'Policy-gated' }
			]
		}
	]);

	const EXECUTIVE_CONFIDENCE_POINTS = Object.freeze([
		{
			kicker: 'Governance',
			title: 'Decisions stay policy-led',
			detail: 'Economic controls are explicit, reviewable, and consistently applied across teams.'
		},
		{
			kicker: 'Operations',
			title: 'Execution stays human-approved',
			detail: 'Change flows remain controlled with clear ownership and accountable approvals.'
		},
		{
			kicker: 'Trust',
			title: 'Reviews stay simple',
			detail: 'Leadership gets a clear narrative from signal to action without audit noise.'
		}
	]);

	const BUYER_ROLE_VIEWS = Object.freeze([
		{
			id: 'cto' as const,
			label: 'CTO',
			headline: 'Keep roadmap velocity while enforcing cloud spend controls',
			detail:
				'Engineering ships faster when cloud cost risk is governed inline, not escalated after the month closes.',
			signals: ['Roadmap stability', 'Controlled velocity', 'Fewer escalation loops']
		},
		{
			id: 'finops' as const,
			label: 'FinOps',
			headline: 'Move from reporting to decision-ready cloud governance',
			detail:
				'Use one control loop to attribute spend movement, assign ownership, and route remediation with policy clarity.',
			signals: ['Forecast confidence', 'Ownership clarity', 'Faster remediation cycle']
		},
		{
			id: 'security' as const,
			label: 'Security',
			headline: 'Enforce controls without becoming a delivery bottleneck',
			detail:
				'Apply policy gates before execution with deterministic outcomes and auditable approval lineage.',
			signals: ['Policy adherence', 'Deterministic controls', 'Audit-ready decisions']
		},
		{
			id: 'cfo' as const,
			label: 'CFO',
			headline: 'Protect gross margin with governed cloud economics',
			detail:
				'Tie cloud actions to financial impact and ownership so executive decisions rely on controlled, trusted signals.',
			signals: ['Margin protection', 'Investment confidence', 'Board-level explainability']
		}
	]);

	const CROSS_SURFACE_COVERAGE = Object.freeze([
		{
			title: 'Cloud Infrastructure',
			detail:
				'AWS, Azure, and GCP spend signals are attributed to accountable teams before they become month-end surprises.'
		},
		{
			title: 'SaaS Spend',
			detail:
				'Vendor usage and expansion pressure are surfaced with ownership context so renewals become controlled decisions.'
		},
		{
			title: 'ITAM and License',
			detail:
				'Entitlement and license posture are reviewed in the same decision loop as cloud spend and approvals.'
		},
		{
			title: 'Platform Tooling',
			detail:
				'Observability and platform service costs are tied to operating owners and financial outcomes.'
		}
	]);

	const landingGridX = [...Array(13).keys()];
	const landingGridY = [...Array(9).keys()];
	const SNAPSHOT_ROTATION_MS = 4400;
	const DEMO_ROTATION_MS = 3200;
	const DEFAULT_SIGNAL_SNAPSHOT = REALTIME_SIGNAL_SNAPSHOTS[0];

	if (!DEFAULT_SIGNAL_SNAPSHOT) {
		throw new Error('Realtime signal map requires at least one snapshot.');
	}

	let signalMapElement: HTMLDivElement | null = null;
	let signalMapInView = $state(true);
	let documentVisible = $state(true);
	let snapshotIndex = $state(0);
	let hookStateIndex = $state(0);
	let buyerRoleIndex = $state(0);
	let demoStepIndex = $state(0);
	let activeLaneId = $state<SignalLaneId | null>(null);
	let visitorId = $state('');
	let pageReferrer = $state('');
	let experiments = $state<LandingExperimentAssignments>(
		resolveLandingExperiments($page.url, DEFAULT_EXPERIMENT_ASSIGNMENTS.seed)
	);
	let attribution = $state<LandingAttribution>({ utm: {} });
	let engagedCaptured = $state(false);
	let rotationInterval: ReturnType<typeof setInterval> | null = null;
	let demoRotationInterval: ReturnType<typeof setInterval> | null = null;

	let activeSnapshot = $derived(
		REALTIME_SIGNAL_SNAPSHOTS[snapshotIndex] ?? DEFAULT_SIGNAL_SNAPSHOT
	);
	let activeHookState = $derived(CLOUD_HOOK_STATES[hookStateIndex] ?? CLOUD_HOOK_STATES[0]);
	let activeBuyerRole = $derived(BUYER_ROLE_VIEWS[buyerRoleIndex] ?? BUYER_ROLE_VIEWS[0]);
	let activeDemoStep = $derived(MICRO_DEMO_STEPS[demoStepIndex] ?? MICRO_DEMO_STEPS[0]);
	let activeSignalLane = $derived(
		activeSnapshot.lanes.find((lane) => lane.id === activeLaneId) ?? activeSnapshot.lanes[0]
	);
	let heroContext = $derived(
		HERO_ROLE_CONTEXT[(activeBuyerRole.id as BuyerPersona) ?? 'finops'] ?? HERO_ROLE_CONTEXT.finops
	);
	let heroTitle = $derived(
		experiments.heroVariant === 'from_metrics_to_control'
			? heroContext.metricsTitle
			: heroContext.controlTitle
	);
	let heroSubtitle = $derived(
		`${heroContext.subtitle} Valdrics helps teams catch overspend early, route the right owner, and act safely before waste compounds.`
	);
	let primaryCtaLabel = $derived(
		experiments.ctaVariant === 'book_briefing' ? 'Book Executive Briefing' : 'Start Free'
	);
	let secondaryCtaLabel = $derived('See Pricing');
	let secondaryCtaHref = $derived(`${base}/pricing`);
	let primaryCtaIntent = $derived(
		experiments.ctaVariant === 'book_briefing' ? 'executive_briefing' : heroContext.primaryIntent
	);
	let includeExperimentQueryParams = $derived(
		shouldIncludeExperimentQueryParams($page.url, false)
	);
	let shouldRotateSnapshots = $derived(
		signalMapInView && documentVisible && REALTIME_SIGNAL_SNAPSHOTS.length > 1
	);
	let shouldRotateDemoSteps = $derived(documentVisible && MICRO_DEMO_STEPS.length > 1);

	$effect(() => {
		const defaultBuyerIndex = BUYER_ROLE_VIEWS.findIndex(
			(role) => role.id === experiments.buyerPersonaDefault
		);
		if (defaultBuyerIndex >= 0) {
			buyerRoleIndex = defaultBuyerIndex;
		}
	});

	$effect(() => {
		if (!activeSignalLane && activeSnapshot.lanes[0]) {
			activeLaneId = activeSnapshot.lanes[0].id;
			return;
		}
		if (activeSignalLane) {
			return;
		}
		activeLaneId = activeSnapshot.lanes[0]?.id ?? null;
	});

	function stopSnapshotRotation() {
		if (!rotationInterval) return;
		clearInterval(rotationInterval);
		rotationInterval = null;
	}

	function stopDemoRotation() {
		if (!demoRotationInterval) return;
		clearInterval(demoRotationInterval);
		demoRotationInterval = null;
	}

	$effect(() => {
		stopSnapshotRotation();
		if (!shouldRotateSnapshots) return;

		rotationInterval = setInterval(() => {
			snapshotIndex = nextSnapshotIndex(snapshotIndex, REALTIME_SIGNAL_SNAPSHOTS.length);
		}, SNAPSHOT_ROTATION_MS);

		return () => stopSnapshotRotation();
	});

	$effect(() => {
		stopDemoRotation();
		if (!shouldRotateDemoSteps) return;

		demoRotationInterval = setInterval(() => {
			demoStepIndex = nextSnapshotIndex(demoStepIndex, MICRO_DEMO_STEPS.length);
		}, DEMO_ROTATION_MS);

		return () => stopDemoRotation();
	});

	onDestroy(() => {
		stopSnapshotRotation();
		stopDemoRotation();
	});

	onMount(() => {
		const storage = browser ? window.localStorage : undefined;
		documentVisible = document.visibilityState === 'visible';
		visitorId = resolveOrCreateLandingVisitorId(storage);
		experiments = resolveLandingExperiments($page.url, visitorId);
		attribution = captureLandingAttribution($page.url, storage);
		pageReferrer = normalizeReferrer(document.referrer);

		incrementLandingFunnelStage('view', storage);
		emitLandingTelemetry('landing_view', 'landing', 'public', buildTelemetryContext('view'));

		const handleVisibility = () => {
			documentVisible = document.visibilityState === 'visible';
		};
		document.addEventListener('visibilitychange', handleVisibility);

		let observer: IntersectionObserver | null = null;
		if (signalMapElement && typeof IntersectionObserver !== 'undefined') {
			observer = new IntersectionObserver(
				(entries) => {
					const entry = entries[0];
					signalMapInView = Boolean(entry?.isIntersecting && entry.intersectionRatio > 0.12);
				},
				{ threshold: [0, 0.12, 0.5] }
			);
			observer.observe(signalMapElement);
		}

		return () => {
			document.removeEventListener('visibilitychange', handleVisibility);
			observer?.disconnect();
		};
	});

	function normalizeReferrer(referrer: string): string {
		return referrer.trim().slice(0, 200);
	}

	function getStorage(): Storage | undefined {
		if (!browser) return undefined;
		return window.localStorage;
	}

	function buildTelemetryContext(stage?: FunnelStage) {
		return {
			visitorId,
			persona: activeBuyerRole.id,
			funnelStage: stage,
			pagePath: $page.url.pathname,
			referrer: pageReferrer || undefined,
			experiment: {
				hero: experiments.heroVariant,
				cta: experiments.ctaVariant,
				order: experiments.sectionOrderVariant
			},
			utm: attribution.utm
		};
	}

	function markEngaged(): void {
		if (engagedCaptured) return;
		engagedCaptured = true;
		incrementLandingFunnelStage('engaged', getStorage());
		emitLandingTelemetry('landing_engaged', 'landing', 'interactive', buildTelemetryContext('engaged'));
	}

	function buildPrimaryCtaHref(): string {
		const params = new URLSearchParams({
			intent: primaryCtaIntent,
			persona: activeBuyerRole.id
		});
		if (includeExperimentQueryParams) {
			params.set('exp_hero', experiments.heroVariant);
			params.set('exp_cta', experiments.ctaVariant);
			params.set('exp_order', experiments.sectionOrderVariant);
		}
		appendUtmParams(params);
		return `${base}/auth/login?${params.toString()}`;
	}

	function appendUtmParams(params: URLSearchParams): void {
		if (attribution.utm.source) params.set('utm_source', attribution.utm.source);
		if (attribution.utm.medium) params.set('utm_medium', attribution.utm.medium);
		if (attribution.utm.campaign) params.set('utm_campaign', attribution.utm.campaign);
		if (attribution.utm.term) params.set('utm_term', attribution.utm.term);
		if (attribution.utm.content) params.set('utm_content', attribution.utm.content);
	}

	function selectSnapshot(index: number) {
		if (index < 0 || index >= REALTIME_SIGNAL_SNAPSHOTS.length) return;
		snapshotIndex = index;
		markEngaged();
		emitLandingTelemetry(
			'snapshot_select',
			'signal_map',
			REALTIME_SIGNAL_SNAPSHOTS[index]?.id,
			buildTelemetryContext('engaged')
		);
	}

	function selectHookState(index: number) {
		if (index < 0 || index >= CLOUD_HOOK_STATES.length) return;
		hookStateIndex = index;
		markEngaged();
		emitLandingTelemetry(
			'hook_toggle',
			'cloud_hook',
			CLOUD_HOOK_STATES[index]?.id,
			buildTelemetryContext('engaged')
		);
	}

	function selectBuyerRole(index: number) {
		if (index < 0 || index >= BUYER_ROLE_VIEWS.length) return;
		buyerRoleIndex = index;
		markEngaged();
		emitLandingTelemetry(
			'buyer_role_select',
			'buyers',
			BUYER_ROLE_VIEWS[index]?.id,
			buildTelemetryContext('engaged')
		);
	}

	function selectDemoStep(index: number) {
		if (index < 0 || index >= MICRO_DEMO_STEPS.length) return;
		demoStepIndex = index;
		markEngaged();
		emitLandingTelemetry(
			'micro_demo_step',
			'hero_demo',
			MICRO_DEMO_STEPS[index]?.id,
			buildTelemetryContext('engaged')
		);
	}

	function selectSignalLane(laneId: SignalLaneId): void {
		activeLaneId = laneId;
		markEngaged();
		emitLandingTelemetry('lane_focus', 'signal_map', laneId, buildTelemetryContext('engaged'));
	}

	function trackCta(action: string, section: string, value: string): void {
		incrementLandingFunnelStage('cta', getStorage());
		emitLandingTelemetry(action, section, value, buildTelemetryContext('cta'));

		if (section === 'hero' && (value === 'start_free' || value === 'book_briefing')) {
			incrementLandingFunnelStage('signup_intent', getStorage());
			emitLandingTelemetry('signup_intent', section, value, buildTelemetryContext('signup_intent'));
		}
	}
</script>

<div class="landing" itemscope itemtype="https://schema.org/SoftwareApplication">
	<meta itemprop="name" content="Valdrics" />
	<meta itemprop="operatingSystem" content="Web" />
	<meta itemprop="applicationCategory" content="BusinessApplication" />
	<meta
		itemprop="description"
		content="Valdrics is the economic control plane for cloud and software spend: measure, govern, and enforce every decision with deterministic policy controls."
	/>
	<meta itemprop="url" content={new URL($page.url.pathname, $page.url.origin).toString()} />
	<meta itemprop="image" content={new URL(`${assets}/og-image.png`, $page.url.origin).toString()} />

	<section class="landing-hero">
		<div class="container mx-auto px-6 pt-10 pb-16">
			<div class="landing-hero-grid">
				<div class="landing-copy">
					<div class="landing-kicker fade-in-up" style="animation-delay: 0ms;">
						<span class="badge badge-accent">Economic Control Plane</span>
						<span class="landing-sep" aria-hidden="true">•</span>
						<span class="landing-kicker-text">Measure. Govern. Maximize.</span>
					</div>

					<div class="landing-problem-hook fade-in-up" style="animation-delay: 70ms;">
						<p class="landing-problem-k">Most teams do not lose money because of missing dashboards.</p>
						<p class="landing-problem-v">They lose it when ownership and action arrive too late.</p>
					</div>

					<h1 class="landing-title fade-in-up" style="animation-delay: 110ms;">
						{heroTitle}
					</h1>

					<p class="landing-subtitle fade-in-up" style="animation-delay: 220ms;">
						{heroSubtitle}
					</p>

					<div class="landing-cta fade-in-up" style="animation-delay: 320ms;">
						<a
							href={buildPrimaryCtaHref()}
							class="btn btn-primary text-base px-8 py-3 pulse-glow"
							onclick={() => trackCta('cta_click', 'hero', experiments.ctaVariant)}
						>
							{primaryCtaLabel}
						</a>
						<a
							href={secondaryCtaHref}
							class="btn btn-secondary text-base px-8 py-3"
							onclick={() => trackCta('cta_click', 'hero', 'see_pricing')}
						>
							{secondaryCtaLabel}
						</a>
					</div>
					<p class="landing-cta-note fade-in-up" style="animation-delay: 360ms;">
						Start with visibility, then scale into governed execution when your operating model is ready.
					</p>
					<a
						href="#cloud-hook"
						class="landing-cta-link fade-in-up"
						style="animation-delay: 390ms;"
						onclick={() => trackCta('cta_click', 'hero', 'why_visibility_fails')}
					>
						See why visibility alone fails
					</a>

					<div class="landing-proof fade-in-up" style="animation-delay: 420ms;">
						{#each HERO_PROOF_POINTS as point (point.title)}
							<div class="landing-proof-item">
								<p class="landing-proof-k">{point.title}</p>
								<p class="landing-proof-v">
									{point.detail}
								</p>
							</div>
						{/each}
					</div>
				</div>

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
							<svg
								class="signal-svg"
								viewBox="0 0 640 420"
								role="img"
								aria-labelledby="signal-map-summary"
							>
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
									onclick={() => selectSignalLane(lane.id)}
									aria-label={`Open ${lane.title} lane detail`}
								></button>
							{/each}

							<div id="signal-map-summary" class="sr-only">
								Signal map summary for {activeSnapshot.label}: {activeSnapshot.headline}
								{activeSnapshot.decisionSummary} This view highlights clarity, control, and confidence
								signals for governed execution.
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
									onclick={() => selectSignalLane(lane.id)}
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
								<p class="signal-lane-detail-k">
									{activeSignalLane.title} · {activeSignalLane.status}
								</p>
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
							<p class="landing-demo-k">20-second Cloud Control Demo</p>
							<div class="landing-demo-steps" role="group" aria-label="Control loop demo steps">
								{#each MICRO_DEMO_STEPS as step, index (step.id)}
									<button
										type="button"
										class="landing-demo-step"
										class:is-active={demoStepIndex === index}
										onclick={() => selectDemoStep(index)}
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
									onclick={() => selectSnapshot(index)}
									aria-pressed={snapshotIndex === index}
								>
									{snapshot.label}
								</button>
							{/each}
						</div>
					</div>
				</div>
			</div>
		</div>
	</section>

	{#snippet cloudHookSection()}
		<section id="cloud-hook" class="container mx-auto px-6 pb-20 landing-section-lazy">
			<div class="landing-hook glass-panel">
				<p class="landing-proof-k">The Cloud Cost Trap</p>
				<h2 class="landing-h2">Visibility alone does not control cloud spend.</h2>
				<p class="landing-section-sub">
					Most teams see cloud waste after the invoice closes. Valdrics creates the aha moment by
					linking each cloud signal to policy checks, ownership, and approved execution in one loop.
				</p>

				<div class="landing-hook-highlight">
					<p class="landing-hook-highlight-k">Aha Moment</p>
					<p class="landing-hook-highlight-v">
						{activeHookState.ahaMoment}
					</p>
				</div>

				<div class="landing-hook-switch" role="group" aria-label="Compare cloud operations">
					{#each CLOUD_HOOK_STATES as state, index (state.id)}
						<button
							type="button"
							class="landing-hook-switch-btn"
							class:is-active={hookStateIndex === index}
							onclick={() => selectHookState(index)}
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
	{/snippet}

	{#snippet workflowSection()}
		<section id="workflow" class="container mx-auto px-6 pb-20 landing-section-lazy">
			<div class="landing-section-head">
				<h2 class="landing-h2">From signal to savings in one controlled flow</h2>
				<p class="landing-section-sub">
					Detect spend risk early, route the right owner, and execute approved actions without slowing
					delivery.
				</p>
			</div>

			<div class="landing-steps">
				<div class="glass-panel landing-step">
					<p class="landing-step-n">01</p>
					<h3 class="landing-h3">Unify your spend signals</h3>
					<p class="landing-p">
						Bring AWS, Azure, GCP, SaaS, and license data into one live operating view.
					</p>
				</div>
				<div class="glass-panel landing-step">
					<p class="landing-step-n">02</p>
					<h3 class="landing-h3">Decide with guardrails</h3>
					<p class="landing-p">
						Apply policy and ownership rules before changes so teams move fast without risky shortcuts.
					</p>
				</div>
				<div class="glass-panel landing-step">
					<p class="landing-step-n">03</p>
					<h3 class="landing-h3">Execute safely, prove impact</h3>
					<p class="landing-p">
						Run approved remediation and keep a clean record for finance and leadership reviews.
					</p>
				</div>
			</div>
		</section>
	{/snippet}

	{#if experiments.sectionOrderVariant === 'workflow_first'}
		{@render workflowSection()}
	{:else}
		{@render cloudHookSection()}
	{/if}

	<section id="benefits" class="container mx-auto px-6 pb-20 landing-section-lazy">
		<div class="landing-section-head">
			<h2 class="landing-h2">Why teams switch from dashboards to control</h2>
			<p class="landing-section-sub">
				Valdrics combines visibility, ownership, and action so teams can reduce waste with less
				escalation.
			</p>
		</div>

		<div class="landing-benefits-grid">
			<article class="glass-panel landing-benefit-card">
				<p class="landing-proof-k">Economic Visibility</p>
				<h3 class="landing-h3">See spend shifts before they become monthly surprises</h3>
				<p class="landing-p">
					Get one clear view of cloud and software spend movement so teams can respond early and
					avoid end-of-month firefighting.
				</p>
			</article>

			<article class="glass-panel landing-benefit-card">
				<p class="landing-proof-k">Execution Controls</p>
				<h3 class="landing-h3">Prevent risky actions before they reach production</h3>
				<p class="landing-p">
					Move from ad-hoc approvals to consistent guardrails so teams can act faster without
					compromising safety.
				</p>
			</article>

			<article class="glass-panel landing-benefit-card">
				<p class="landing-proof-k">Financial Governance</p>
				<h3 class="landing-h3">Set budget rules once and enforce them everywhere</h3>
				<p class="landing-p">
					Keep financial decisions aligned across platform, finance, and leadership with clear
					ownership and consistent decision paths.
				</p>
			</article>

			<article class="glass-panel landing-benefit-card">
				<p class="landing-proof-k">AI-Assisted Optimization</p>
				<h3 class="landing-h3">Get faster recommendations your team can trust</h3>
				<p class="landing-p">
					Use AI to prioritize high-impact opportunities while keeping final decisions with your
					team.
				</p>
			</article>

			<article class="glass-panel landing-benefit-card">
				<p class="landing-proof-k">Executive Explainability</p>
				<h3 class="landing-h3">Answer leadership questions in minutes</h3>
				<p class="landing-p">
					Share clear decision history and supporting evidence when leadership, finance, or audit
					needs answers.
				</p>
			</article>
		</div>
	</section>

	<section id="personas" class="container mx-auto px-6 pb-20 landing-section-lazy">
		<div class="landing-section-head">
			<h2 class="landing-h2">Built for every decision-maker</h2>
			<p class="landing-section-sub">
				Finance, engineering, security, and leadership each get the context they need without separate
				tools.
			</p>
		</div>

		<div class="landing-buyer-switch" role="tablist" aria-label="Buyer role views">
			{#each BUYER_ROLE_VIEWS as role, index (role.id)}
				<button
					type="button"
					role="tab"
					id={`buyer-tab-${role.id}`}
					class="landing-buyer-btn"
					class:is-active={buyerRoleIndex === index}
					aria-selected={buyerRoleIndex === index}
					aria-controls={`buyer-panel-${role.id}`}
					tabindex={buyerRoleIndex === index ? 0 : -1}
					onclick={() => selectBuyerRole(index)}
				>
					{role.label}
				</button>
			{/each}
		</div>

		<div
			class="glass-panel landing-buyer-panel"
			role="tabpanel"
			id={`buyer-panel-${activeBuyerRole.id}`}
			aria-labelledby={`buyer-tab-${activeBuyerRole.id}`}
		>
			<p class="landing-proof-k">{activeBuyerRole.label} Priority</p>
			<h3 class="landing-h3">{activeBuyerRole.headline}</h3>
			<p class="landing-p">{activeBuyerRole.detail}</p>
			<div class="landing-buyer-signals">
				{#each activeBuyerRole.signals as signal (signal)}
					<span class="landing-buyer-signal">{signal}</span>
				{/each}
			</div>
		</div>
		<div class="landing-persona-proof">
			Outcome: one platform that aligns engineering, finance, security, and executive decision quality.
		</div>
	</section>

	{#if experiments.sectionOrderVariant === 'workflow_first'}
		{@render cloudHookSection()}
	{:else}
		{@render workflowSection()}
	{/if}

	<section id="coverage" class="container mx-auto px-6 pb-20 landing-section-lazy">
		<div class="landing-section-head">
			<h2 class="landing-h2">One platform for cloud, SaaS, and license spend</h2>
			<p class="landing-section-sub">
				Valdrics starts with cloud economics and extends decision governance into SaaS, ITAM/license,
				and platform operations.
			</p>
		</div>

		<div class="landing-coverage-grid">
			{#each CROSS_SURFACE_COVERAGE as area (area.title)}
				<article class="glass-panel landing-coverage-card">
					<p class="landing-proof-k">{area.title}</p>
					<p class="landing-p">{area.detail}</p>
				</article>
			{/each}
		</div>
	</section>

	<section id="trust" class="container mx-auto px-6 pb-20 landing-section-lazy">
		<div class="landing-section-head">
			<h2 class="landing-h2">Why buyers trust Valdrics</h2>
			<p class="landing-section-sub">
				Operational trust signals that show teams can move fast without losing control.
			</p>
		</div>

		<div class="landing-evidence-grid">
			{#each EXECUTIVE_CONFIDENCE_POINTS as point (point.title)}
				<article class="glass-panel landing-evidence-card">
					<p class="landing-proof-k">{point.kicker}</p>
					<h3 class="landing-h3">{point.title}</h3>
					<p class="landing-p">{point.detail}</p>
				</article>
			{/each}
		</div>
	</section>
</div>

<style>
	.landing {
		position: relative;
		isolation: isolate;
	}

	.landing-section-lazy {
		content-visibility: auto;
		contain-intrinsic-size: 640px;
	}

	.landing-hero {
		position: relative;
		overflow: hidden;
	}

	.landing-hero::before {
		content: '';
		position: absolute;
		inset: -260px -120px auto -120px;
		height: 640px;
		background:
			radial-gradient(520px 320px at 18% 18%, rgb(6 182 212 / 0.22), transparent 62%),
			radial-gradient(520px 360px at 58% 22%, rgb(34 211 238 / 0.18), transparent 65%),
			radial-gradient(520px 420px at 82% 38%, rgb(16 185 129 / 0.14), transparent 68%),
			radial-gradient(420px 360px at 70% 74%, rgb(245 158 11 / 0.1), transparent 70%);
		filter: blur(46px);
		opacity: 1;
		pointer-events: none;
		z-index: 0;
	}

	.landing-hero::after {
		content: '';
		position: absolute;
		inset: 0;
		background-image: radial-gradient(rgb(255 255 255 / 0.1) 1px, transparent 1px);
		background-size: 24px 24px;
		opacity: 0.1;
		pointer-events: none;
		z-index: 0;
	}

	.landing-hero :global(.container) {
		position: relative;
		z-index: 1;
	}

	.landing-hero-grid {
		display: grid;
		gap: 2.5rem;
		align-items: start;
	}

	@media (min-width: 1024px) {
		.landing-hero-grid {
			grid-template-columns: 1.1fr 0.9fr;
			gap: 3rem;
		}
	}

	.landing-copy {
		text-align: center;
	}

	@media (min-width: 1024px) {
		.landing-copy {
			text-align: left;
			padding-top: 0.75rem;
		}
	}

	.landing-kicker {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.55rem;
		flex-wrap: wrap;
	}

	@media (min-width: 1024px) {
		.landing-kicker {
			justify-content: flex-start;
		}
	}

	.landing-kicker-text {
		color: var(--color-ink-400);
		font-size: 0.95rem;
		font-weight: 500;
		letter-spacing: 0.01em;
	}

	.landing-sep {
		color: var(--color-ink-600);
	}

	.landing-problem-hook {
		margin-top: 0.9rem;
		border: 1px solid rgb(244 63 94 / 0.28);
		border-radius: var(--radius-lg);
		padding: 0.7rem 0.85rem;
		background: linear-gradient(130deg, rgb(244 63 94 / 0.12), rgb(15 23 42 / 0.24));
	}

	.landing-problem-k {
		margin: 0;
		font-size: 0.86rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 800;
		color: var(--color-ink-200);
	}

	.landing-problem-v {
		margin: 0.35rem 0 0 0;
		font-size: 1rem;
		line-height: 1.45;
		color: var(--color-ink-100);
	}

	.landing-title {
		font-family: ui-serif, 'Iowan Old Style', 'Palatino Linotype', Palatino, serif;
		font-weight: 800;
		letter-spacing: -0.04em;
		line-height: 1.02;
		font-size: clamp(2.6rem, 5vw, 4.4rem);
		margin-top: 0.9rem;
		margin-bottom: 1rem;
	}

	.landing-subtitle {
		color: var(--color-ink-300);
		font-size: 1.125rem;
		line-height: 1.65;
		max-width: 42rem;
		margin: 0 auto;
	}

	@media (min-width: 1024px) {
		.landing-subtitle {
			margin-left: 0;
		}
	}

	.landing-cta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		justify-content: center;
		margin-top: 1.4rem;
	}

	@media (max-width: 640px) {
		.landing-cta {
			flex-direction: column;
			align-items: stretch;
			gap: 0.65rem;
		}

		.landing-cta a {
			display: inline-flex;
			align-items: center;
			justify-content: center;
			width: 100%;
			min-height: 2.85rem;
			font-size: 1rem;
			line-height: 1.2;
			padding: 0.72rem 1rem;
		}
	}

	@media (min-width: 1024px) {
		.landing-cta {
			justify-content: flex-start;
		}
	}

	.landing-cta-note {
		margin: 0.6rem 0 0 0;
		color: var(--color-ink-400);
		font-size: 0.92rem;
		line-height: 1.45;
	}

	.landing-cta-link {
		display: inline-flex;
		margin-top: 0.2rem;
		font-size: 0.95rem;
		font-weight: 700;
		color: var(--color-accent-300);
		text-decoration: underline;
		text-decoration-thickness: 1px;
		text-underline-offset: 2px;
	}

	.landing-cta-link:hover {
		color: var(--color-accent-200);
	}

	.landing-cta-link:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
		border-radius: 4px;
	}

	@media (max-width: 640px) {
		.landing-cta-note,
		.landing-cta-link {
			text-align: center;
			justify-content: center;
		}
	}

	.landing-proof {
		margin-top: 1.75rem;
		display: grid;
		gap: 0.85rem;
		grid-template-columns: 1fr;
	}

	@media (min-width: 768px) {
		.landing-proof {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-proof-item {
		border: 1px solid rgb(255 255 255 / 0.06);
		border-radius: var(--radius-lg);
		padding: 0.95rem 1rem;
		background: rgb(15 19 24 / 0.35);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
	}

	.landing-proof-k {
		margin: 0 0 0.25rem 0;
		font-size: var(--text-xs);
		letter-spacing: 0.09em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-200);
	}

	.landing-proof-v {
		margin: 0;
		font-size: 1rem;
		color: var(--color-ink-400);
	}

	.landing-preview {
		max-width: 42rem;
		margin: 0 auto;
	}

	@media (min-width: 1024px) {
		.landing-preview {
			max-width: none;
			margin: 0;
		}
	}

	.landing-preview-card {
		padding: 1.1rem;
		contain: layout paint style;
	}

	.landing-preview-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.landing-preview-title {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		font-weight: 700;
		color: var(--color-ink-100);
	}

	.landing-preview-pill {
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: 0.12em;
		font-weight: 800;
		padding: 0.25rem 0.55rem;
		border-radius: 9999px;
		color: var(--color-success-400);
		background: rgb(16 185 129 / 0.1);
		border: 1px solid rgb(16 185 129 / 0.22);
	}

	.landing-live-dot {
		width: 8px;
		height: 8px;
		border-radius: 9999px;
		background: var(--color-success-400);
		box-shadow: 0 0 0 6px rgb(16 185 129 / 0.12);
		animation: livePulse 1.8s var(--ease-in-out) infinite;
	}

	@keyframes livePulse {
		0%,
		100% {
			transform: scale(1);
			opacity: 0.95;
		}
		50% {
			transform: scale(1.4);
			opacity: 0.55;
		}
	}

	.signal-state-headline {
		margin: 0;
		font-size: 1.08rem;
		font-weight: 600;
		color: var(--color-ink-200);
	}

	.signal-state-sub {
		margin: 0.35rem 0 0.8rem 0;
		font-size: 1rem;
		line-height: 1.5;
		color: var(--color-ink-400);
	}

	.signal-map {
		position: relative;
		border-radius: var(--radius-lg);
		overflow: hidden;
		contain: strict;
		border: 1px solid rgb(255 255 255 / 0.07);
		background:
			radial-gradient(
				120% 90% at 30% 20%,
				rgb(34 211 238 / 0.18) 0%,
				rgb(6 182 212 / 0.06) 38%,
				rgb(15 19 24 / 0.55) 70%
			),
			radial-gradient(90% 120% at 75% 70%, rgb(16 185 129 / 0.12) 0%, rgb(15 19 24 / 0) 62%);
		height: 344px;
	}

	.signal-map::after {
		content: '';
		position: absolute;
		inset: 0;
		background-image: radial-gradient(rgb(255 255 255 / 0.1) 1px, transparent 1px);
		background-size: 26px 26px;
		opacity: 0.12;
		pointer-events: none;
		z-index: 2;
	}

	.signal-svg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		z-index: 1;
	}

	.sig-grid line {
		stroke: rgb(255 255 255 / 0.06);
		stroke-width: 1;
	}

	.sig-link {
		opacity: 0.88;
		animation: lineDash 7s linear infinite;
	}

	.signal-map.is-paused .sig-link,
	.signal-map.is-paused .sig-node {
		animation-play-state: paused;
	}

	@keyframes lineDash {
		to {
			stroke-dashoffset: -220;
		}
	}

	.sig-node {
		fill: rgb(10 13 18 / 0.8);
		stroke: var(--color-accent-400);
		stroke-width: 2.2;
		filter: drop-shadow(0 0 10px rgb(34 211 238 / 0.2));
		transform-box: fill-box;
		transform-origin: center;
		animation: nodePulse 2.9s var(--ease-in-out) infinite;
	}

	.sig-node--center {
		fill: rgb(6 182 212 / 0.65);
		stroke: var(--color-accent-400);
		animation-duration: 3.8s;
	}

	@keyframes nodePulse {
		0%,
		100% {
			transform: scale(1);
		}
		50% {
			transform: scale(1.18);
		}
	}

	.sig-link.is-healthy {
		opacity: 0.92;
	}

	.sig-link.is-watch {
		stroke: var(--color-warning-400);
		opacity: 0.82;
	}

	.sig-link.is-critical {
		stroke: var(--color-danger-400);
		opacity: 0.95;
	}

	.sig-node.is-healthy {
		stroke: var(--color-success-400);
		filter: drop-shadow(0 0 10px rgb(16 185 129 / 0.24));
	}

	.sig-node.is-watch {
		stroke: var(--color-warning-400);
		filter: drop-shadow(0 0 10px rgb(245 158 11 / 0.24));
	}

	.sig-node.is-critical {
		stroke: var(--color-danger-400);
		filter: drop-shadow(0 0 10px rgb(244 63 94 / 0.26));
	}

	.sig-node.is-focused {
		stroke-width: 3.2;
		filter: drop-shadow(0 0 14px rgb(34 211 238 / 0.45));
	}

	@media (prefers-reduced-motion: reduce) {
		.landing-live-dot,
		.sig-link,
		.sig-node {
			animation: none !important;
		}
	}

	@media (max-width: 640px) {
		.landing-live-dot,
		.sig-link,
		.sig-node {
			animation-duration: 0.001ms;
			animation-iteration-count: 1;
		}
	}

	.signal-hotspot {
		position: absolute;
		width: 1.35rem;
		height: 1.35rem;
		border-radius: 9999px;
		border: 1px solid rgb(255 255 255 / 0.42);
		background: rgb(7 12 18 / 0.55);
		transform: translate(-50%, -50%);
		z-index: 4;
		transition: all var(--duration-fast) var(--ease-out);
	}

	.signal-hotspot:hover,
	.signal-hotspot.is-active {
		border-color: rgb(34 211 238 / 0.82);
		box-shadow: 0 0 0 3px rgb(34 211 238 / 0.2);
		background: rgb(34 211 238 / 0.2);
	}

	.signal-hotspot:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.signal-lane-controls {
		margin-top: 0.85rem;
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.45rem;
	}

	@media (min-width: 768px) {
		.signal-lane-controls {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.signal-lane-btn {
		border-radius: 0.75rem;
		border: 1px solid rgb(255 255 255 / 0.12);
		background: rgb(11 16 23 / 0.62);
		padding: 0.55rem 0.65rem;
		color: var(--color-ink-300);
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		text-align: left;
		transition: all var(--duration-fast) var(--ease-out);
	}

	.signal-lane-btn:hover {
		border-color: rgb(255 255 255 / 0.24);
		color: var(--color-ink-100);
	}

	.signal-lane-btn:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.signal-lane-btn.is-active {
		background: rgb(6 182 212 / 0.14);
		border-color: rgb(6 182 212 / 0.36);
		color: var(--color-accent-200);
	}

	.signal-lane-btn-title {
		font-size: 0.83rem;
		font-weight: 700;
		line-height: 1.2;
	}

	.signal-lane-btn-status {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.03em;
		text-transform: uppercase;
		opacity: 0.85;
	}

	.signal-lane-detail-panel {
		margin-top: 0.65rem;
		border: 1px solid rgb(255 255 255 / 0.12);
		border-radius: var(--radius-lg);
		padding: 0.72rem 0.8rem;
		background: rgb(8 12 18 / 0.55);
	}

	.signal-lane-detail-k {
		margin: 0;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 800;
		color: var(--color-accent-300);
	}

	.signal-lane-detail-v {
		margin: 0.4rem 0 0 0;
		font-size: 0.93rem;
		line-height: 1.45;
		color: var(--color-ink-200);
	}

	.signal-lane-detail-m {
		margin: 0.38rem 0 0 0;
		font-size: 0.86rem;
		line-height: 1.35;
		color: var(--color-ink-400);
	}

	.signal-label {
		position: absolute;
		padding: 0.55rem 0.65rem;
		border-radius: 0.85rem;
		background: rgb(10 13 18 / 0.55);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
		border: 1px solid rgb(255 255 255 / 0.08);
		pointer-events: none;
		max-width: 12.75rem;
		z-index: 3;
	}

	.signal-label-k {
		margin: 0;
		font-size: var(--text-xs);
		letter-spacing: 0.12em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-200);
	}

	.signal-label-v {
		margin: 0.15rem 0 0 0;
		font-size: 0.94rem;
		line-height: 1.35;
		color: var(--color-ink-400);
		display: -webkit-box;
		line-clamp: 2;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.signal-label--center {
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		text-align: center;
		max-width: 10.5rem;
	}

	.signal-label--a {
		left: 18%;
		top: 34%;
		transform: translate(-8%, -96%);
	}

	.signal-label--b {
		left: 73%;
		top: 34%;
		transform: translate(-58%, -96%);
	}

	.signal-label--c {
		left: 77%;
		top: 66%;
		transform: translate(-36%, 0);
	}

	.signal-label--d {
		left: 16%;
		top: 66%;
		transform: translate(0, 0);
	}

	@media (max-width: 900px) {
		.signal-label {
			max-width: 10.25rem;
			padding: 0.45rem 0.55rem;
		}

		.signal-label-k {
			font-size: 0.68rem;
		}

		.signal-label-v {
			font-size: 0.82rem;
		}

		.signal-label--a {
			left: 6%;
			top: 10%;
			transform: none;
		}

		.signal-label--b {
			left: auto;
			right: 6%;
			top: 10%;
			transform: none;
			text-align: right;
		}

		.signal-label--c {
			left: auto;
			right: 6%;
			top: auto;
			bottom: 8%;
			transform: none;
			text-align: right;
		}

		.signal-label--d {
			left: 6%;
			top: auto;
			bottom: 8%;
			transform: none;
		}
	}

	@media (max-width: 560px) {
		.signal-label:not(.signal-label--center) {
			display: none;
		}

		.signal-label--center {
			max-width: 9rem;
			padding: 0.5rem 0.6rem;
		}
	}

	.landing-metrics {
		margin-top: 0.9rem;
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.75rem;
	}

	@media (max-width: 900px) {
		.landing-metrics {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	@media (max-width: 560px) {
		.landing-metrics {
			grid-template-columns: 1fr;
		}
	}

	.landing-metric {
		padding: 0.85rem 0.9rem;
		border-radius: var(--radius-lg);
	}

	.landing-metric-k {
		margin: 0;
		font-size: var(--text-xs);
		letter-spacing: 0.1em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-400);
	}

	.landing-metric-v {
		margin: 0.25rem 0 0 0;
		font-size: 1.1rem;
		font-weight: 800;
		line-height: 1.3;
	}

	.landing-metric-h {
		margin: 0.3rem 0 0 0;
		font-size: 0.95rem;
		color: var(--color-ink-500);
	}

	.landing-demo-strip {
		margin-top: 0.95rem;
		border: 1px solid rgb(255 255 255 / 0.09);
		border-radius: var(--radius-lg);
		padding: 0.8rem 0.9rem;
		background: rgb(7 12 18 / 0.5);
	}

	.landing-demo-k {
		margin: 0;
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: 0.12em;
		font-weight: 800;
		color: var(--color-accent-300);
	}

	.landing-demo-steps {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.45rem;
		margin-top: 0.55rem;
	}

	@media (min-width: 900px) {
		.landing-demo-steps {
			grid-template-columns: repeat(4, minmax(0, 1fr));
		}
	}

	.landing-demo-step {
		border-radius: 9999px;
		border: 1px solid rgb(255 255 255 / 0.14);
		background: rgb(21 30 40 / 0.78);
		color: var(--color-ink-300);
		font-size: var(--text-xs);
		font-weight: 700;
		padding: 0.35rem 0.5rem;
		transition: all var(--duration-fast) var(--ease-out);
	}

	.landing-demo-step:hover {
		color: var(--color-ink-100);
		border-color: rgb(255 255 255 / 0.24);
	}

	.landing-demo-step:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.landing-demo-step.is-active {
		background: rgb(6 182 212 / 0.18);
		border-color: rgb(6 182 212 / 0.36);
		color: var(--color-accent-300);
	}

	.landing-demo-detail {
		margin: 0.65rem 0 0 0;
		font-size: 0.9rem;
		line-height: 1.5;
		color: var(--color-ink-300);
	}

	.signal-snapshot-controls {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 0.95rem;
	}

	.signal-snapshot-btn {
		padding: 0.4rem 0.65rem;
		border-radius: 9999px;
		font-size: var(--text-xs);
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		border: 1px solid rgb(255 255 255 / 0.1);
		background: rgb(24 32 40 / 0.7);
		color: var(--color-ink-300);
		transition: all var(--duration-fast) var(--ease-out);
	}

	.signal-snapshot-btn:hover {
		color: var(--color-ink-100);
		border-color: rgb(255 255 255 / 0.2);
	}

	.signal-snapshot-btn:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.signal-snapshot-btn.is-active {
		background: rgb(6 182 212 / 0.16);
		border-color: rgb(6 182 212 / 0.35);
		color: var(--color-accent-400);
	}

	.landing-section-head {
		max-width: 52rem;
		margin: 0 auto 1.25rem auto;
		text-align: center;
	}

	.landing-h2 {
		font-family: ui-serif, 'Iowan Old Style', 'Palatino Linotype', Palatino, serif;
		font-weight: 800;
		letter-spacing: -0.03em;
		line-height: 1.1;
		font-size: clamp(1.85rem, 3vw, 2.3rem);
		margin: 0;
	}

	.landing-section-sub {
		margin: 0.7rem auto 0 auto;
		color: var(--color-ink-400);
		font-size: 1.05rem;
		max-width: 46rem;
	}

	.landing-h3 {
		font-weight: 700;
		font-size: 1.08rem;
		margin: 0 0 0.55rem 0;
	}

	.landing-p {
		margin: 0;
		color: var(--color-ink-300);
		font-size: 1rem;
		line-height: 1.65;
	}

	.landing-hook {
		padding: 1.25rem;
	}

	.landing-hook-highlight {
		margin-top: 1rem;
		border: 1px solid rgb(6 182 212 / 0.22);
		background: linear-gradient(120deg, rgb(6 182 212 / 0.14), rgb(16 185 129 / 0.08));
		border-radius: var(--radius-lg);
		padding: 0.85rem 1rem;
	}

	.landing-hook-highlight-k {
		margin: 0;
		font-size: var(--text-xs);
		letter-spacing: 0.11em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-accent-300);
	}

	.landing-hook-highlight-v {
		margin: 0.25rem 0 0 0;
		font-size: 1.02rem;
		font-weight: 700;
		color: var(--color-ink-100);
	}

	.landing-hook-switch {
		margin-top: 1rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem;
	}

	.landing-hook-switch-btn {
		padding: 0.45rem 0.72rem;
		border-radius: 9999px;
		border: 1px solid rgb(255 255 255 / 0.12);
		background: rgb(24 32 40 / 0.7);
		color: var(--color-ink-300);
		font-size: 0.86rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		transition: all var(--duration-fast) var(--ease-out);
	}

	.landing-hook-switch-btn:hover {
		color: var(--color-ink-100);
		border-color: rgb(255 255 255 / 0.2);
	}

	.landing-hook-switch-btn:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.landing-hook-switch-btn.is-active {
		background: rgb(6 182 212 / 0.16);
		border-color: rgb(6 182 212 / 0.35);
		color: var(--color-accent-400);
	}

	.landing-hook-scene {
		margin-top: 0.9rem;
		border: 1px solid rgb(244 63 94 / 0.22);
		border-radius: var(--radius-lg);
		padding: 0.95rem 1rem;
		background: linear-gradient(145deg, rgb(244 63 94 / 0.1), rgb(15 23 42 / 0.42));
		transition:
			background var(--duration-fast) var(--ease-out),
			border-color var(--duration-fast) var(--ease-out);
	}

	.landing-hook-scene.is-with {
		border-color: rgb(16 185 129 / 0.24);
		background: linear-gradient(145deg, rgb(6 182 212 / 0.12), rgb(16 185 129 / 0.08));
	}

	.landing-hook-sub {
		margin: 0 0 0.6rem 0;
		font-size: 0.9rem;
		color: var(--color-ink-200);
		font-weight: 600;
	}

	.landing-hook-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.5rem;
	}

	.landing-hook-list li {
		position: relative;
		padding-left: 1rem;
		color: var(--color-ink-200);
		line-height: 1.45;
	}

	.landing-hook-list li::before {
		content: '';
		position: absolute;
		left: 0;
		top: 0.46rem;
		width: 0.42rem;
		height: 0.42rem;
		border-radius: 9999px;
		background: var(--color-accent-400);
		box-shadow: 0 0 0 4px rgb(6 182 212 / 0.14);
	}

	.landing-hook-metrics {
		margin-top: 0.9rem;
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.55rem;
	}

	@media (min-width: 900px) {
		.landing-hook-metrics {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-hook-metric {
		border: 1px solid rgb(255 255 255 / 0.1);
		border-radius: var(--radius-lg);
		padding: 0.6rem 0.7rem;
		background: rgb(10 13 18 / 0.42);
	}

	.landing-hook-metric-k {
		margin: 0;
		font-size: var(--text-xs);
		letter-spacing: 0.1em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-500);
	}

	.landing-hook-metric-v {
		margin: 0.22rem 0 0 0;
		font-size: 0.94rem;
		font-weight: 700;
		color: var(--color-ink-100);
	}

	.landing-benefits-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	@media (min-width: 1024px) {
		.landing-benefits-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}

		.landing-benefits-grid .landing-benefit-card:last-child {
			grid-column: span 2;
		}
	}

	.landing-buyer-switch {
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem;
		justify-content: center;
	}

	.landing-buyer-btn {
		padding: 0.45rem 0.75rem;
		border-radius: 9999px;
		border: 1px solid rgb(255 255 255 / 0.15);
		background: rgb(24 32 40 / 0.7);
		color: var(--color-ink-300);
		font-size: var(--text-xs);
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		transition: all var(--duration-fast) var(--ease-out);
	}

	.landing-buyer-btn:hover {
		color: var(--color-ink-100);
		border-color: rgb(255 255 255 / 0.24);
	}

	.landing-buyer-btn:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.landing-buyer-btn.is-active {
		background: rgb(6 182 212 / 0.16);
		border-color: rgb(6 182 212 / 0.35);
		color: var(--color-accent-300);
	}

	.landing-buyer-panel {
		margin-top: 0.85rem;
	}

	.landing-buyer-signals {
		margin-top: 0.75rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.landing-buyer-signal {
		padding: 0.28rem 0.5rem;
		border-radius: 9999px;
		border: 1px solid rgb(255 255 255 / 0.14);
		background: rgb(8 12 17 / 0.48);
		font-size: 0.86rem;
		line-height: 1.2;
		color: var(--color-ink-200);
	}

	.landing-persona-proof {
		margin: 0.9rem auto 0 auto;
		max-width: 56rem;
		text-align: center;
		font-size: 0.92rem;
		font-weight: 600;
		line-height: 1.45;
		color: var(--color-ink-200);
	}

	.landing-steps {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	.landing-coverage-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	@media (min-width: 900px) {
		.landing-coverage-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.landing-coverage-card {
		border-color: rgb(16 185 129 / 0.2);
		background: linear-gradient(145deg, rgb(6 182 212 / 0.1), rgb(16 185 129 / 0.08));
	}

	@media (min-width: 768px) {
		.landing-steps {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-step {
		position: relative;
		overflow: hidden;
	}

	.landing-step::before {
		content: '';
		position: absolute;
		inset: 0 0 auto 0;
		height: 2px;
		background: linear-gradient(90deg, rgb(34 211 238 / 0.9), rgb(16 185 129 / 0.75));
		opacity: 0.75;
	}

	.landing-step-n {
		margin: 0 0 0.35rem 0;
		font-size: var(--text-xs);
		letter-spacing: 0.16em;
		font-weight: 900;
		color: var(--color-ink-500);
		text-transform: uppercase;
	}

	.landing-evidence-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	@media (max-width: 640px) {
		.landing-subtitle {
			font-size: 1.06rem;
			line-height: 1.62;
		}

		.landing-demo-step,
		.signal-snapshot-btn,
		.landing-hook-switch-btn,
		.landing-buyer-btn {
			min-height: 2.5rem;
			padding: 0.5rem 0.78rem;
			font-size: 0.89rem;
		}

	}

	@media (min-width: 1024px) {
		.landing-evidence-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

</style>
