<script lang="ts">
	import { browser } from '$app/environment';
	import { assets, base } from '$app/paths';
	import { page } from '$app/stores';
	import { onDestroy, onMount } from 'svelte';
	import {
		REALTIME_SIGNAL_SNAPSHOTS,
		nextSnapshotIndex,
		type SignalLaneId
	} from '$lib/landing/realtimeSignalMap';
	import { emitLandingTelemetry as emitLandingTelemetryCore } from '$lib/landing/landingTelemetry';
	import {
		resolveLandingExperiments,
		resolveOrCreateLandingVisitorId as resolveOrCreateLandingVisitorIdCore,
		shouldIncludeExperimentQueryParams,
		type BuyerPersona,
		type LandingExperimentAssignments
	} from '$lib/landing/landingExperiment';
	import {
		captureLandingAttribution as captureLandingAttributionCore,
		incrementLandingFunnelStage as incrementLandingFunnelStageCore,
		type FunnelStage,
		type LandingAttribution
	} from '$lib/landing/landingFunnel';
	import {
		DEFAULT_LANDING_ROI_INPUTS,
		normalizeLandingRoiInputs
	} from '$lib/landing/roiCalculator';
	import {
		BUYER_ROLE_VIEWS,
		CLOUD_HOOK_STATES,
		HERO_ROLE_CONTEXT,
		MICRO_DEMO_STEPS
	} from '$lib/landing/heroContent';
	import LandingHeroCopy from '$lib/components/landing/LandingHeroCopy.svelte';
	import LandingSignalMapCard from '$lib/components/landing/LandingSignalMapCard.svelte';
	import LandingRoiSimulator from '$lib/components/landing/LandingRoiSimulator.svelte';
	import LandingCloudHookSection from '$lib/components/landing/LandingCloudHookSection.svelte';
	import LandingWorkflowSection from '$lib/components/landing/LandingWorkflowSection.svelte';
	import LandingRoiPlannerCta from '$lib/components/landing/LandingRoiPlannerCta.svelte';
	import LandingBenefitsSection from '$lib/components/landing/LandingBenefitsSection.svelte';
	import LandingPlansSection from '$lib/components/landing/LandingPlansSection.svelte';
	import LandingPersonaSection from '$lib/components/landing/LandingPersonaSection.svelte';
	import LandingCapabilitiesSection from '$lib/components/landing/LandingCapabilitiesSection.svelte';
	import LandingTrustSection from '$lib/components/landing/LandingTrustSection.svelte';
	import LandingLeadCaptureSection from '$lib/components/landing/LandingLeadCaptureSection.svelte';
	import LandingExitIntentPrompt from '$lib/components/landing/LandingExitIntentPrompt.svelte';
	import LandingCookieConsent from '$lib/components/landing/LandingCookieConsent.svelte';
	import './LandingHero.css';

	const DEFAULT_EXPERIMENT_ASSIGNMENTS: LandingExperimentAssignments = Object.freeze({
		buyerPersonaDefault: 'cto',
		heroVariant: 'control_every_dollar',
		ctaVariant: 'start_free',
		sectionOrderVariant: 'problem_first',
		seed: 'default'
	});

	const USD_WHOLE_FORMATTER = new Intl.NumberFormat('en-US', {
		style: 'currency',
		currency: 'USD',
		maximumFractionDigits: 0
	});

	const SNAPSHOT_ROTATION_MS = 4400;
	const DEMO_ROTATION_MS = 3200;
	const LANDING_SCROLL_MILESTONES = Object.freeze([25, 50, 75, 95]);
	const LANDING_CONSENT_KEY = 'valdrics.cookie_consent.v1';
	const DEFAULT_SIGNAL_SNAPSHOT = REALTIME_SIGNAL_SNAPSHOTS[0];
	const SUBSCRIBE_API_PATH = `${base}/api/marketing/subscribe`;
	const RESOURCES_HREF = `${base}/resources`;
	const ROI_WORKSHEET_HREF = `${base}/resources/valdrics-roi-assumptions.csv`;
	const TALK_TO_SALES_PATH = `${base}/talk-to-sales`;
	const HERO_PLAIN_COPY: Record<BuyerPersona, { title: string; subtitle: string }> = Object.freeze({
		cto: {
			title: 'Stop overspending before it delays your product roadmap.',
			subtitle:
				'Spot cost issues early, assign the right owner quickly, and fix them safely without slowing delivery.'
		},
		finops: {
			title: 'Turn spend data into fast owner-led action.',
			subtitle:
				'Find where money is leaking, route accountability fast, and close actions before month-end pressure.'
		},
		security: {
			title: 'Reduce cloud waste without increasing change risk.',
			subtitle:
				'Every high-impact action passes risk checks and explicit approvals before execution.'
		},
		cfo: {
			title: 'Protect gross margin with early spend decisions.',
			subtitle:
				'Give finance and engineering one shared operating view with clear ownership and measurable outcomes.'
		}
	});

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
	let roiMonthlySpendUsd = $state(DEFAULT_LANDING_ROI_INPUTS.monthlySpendUsd);
	let roiExpectedReductionPct = $state(DEFAULT_LANDING_ROI_INPUTS.expectedReductionPct);
	let roiRolloutDays = $state(DEFAULT_LANDING_ROI_INPUTS.rolloutDays);
	let roiTeamMembers = $state(DEFAULT_LANDING_ROI_INPUTS.teamMembers);
	let roiBlendedHourlyUsd = $state(DEFAULT_LANDING_ROI_INPUTS.blendedHourlyUsd);
	let roiPlatformAnnualCostUsd = $state(DEFAULT_LANDING_ROI_INPUTS.platformAnnualCostUsd);
	let scenarioWasteWithoutPct = $state(18);
	let scenarioWasteWithPct = $state(7);
	let scenarioWindowMonths = $state(12);
	let scenarioAdjustCaptured = $state(false);
	let plainLanguageMode = $state(false);
	let landingScrollProgressPct = $state(0);
	let telemetryEnabled = $state(false);
	let telemetryInitialized = $state(false);
	let cookieBannerVisible = $state(false);

	let activeSnapshot = $derived(
		REALTIME_SIGNAL_SNAPSHOTS[snapshotIndex] ?? DEFAULT_SIGNAL_SNAPSHOT
	);
	let activeHookState = $derived(CLOUD_HOOK_STATES[hookStateIndex] ?? CLOUD_HOOK_STATES[0]);
	let activeBuyerRole = $derived(BUYER_ROLE_VIEWS[buyerRoleIndex] ?? BUYER_ROLE_VIEWS[0]);
	let activeSignalLane = $derived(
		activeSnapshot.lanes.find((lane) => lane.id === activeLaneId) ?? activeSnapshot.lanes[0]
	);
	let heroContext = $derived(
		HERO_ROLE_CONTEXT[(activeBuyerRole.id as BuyerPersona) ?? 'finops'] ?? HERO_ROLE_CONTEXT.finops
	);
	let plainCopy = $derived(
		HERO_PLAIN_COPY[(activeBuyerRole.id as BuyerPersona) ?? 'finops'] ?? HERO_PLAIN_COPY.finops
	);
	let heroTitle = $derived(
		plainLanguageMode
			? plainCopy.title
			: experiments.heroVariant === 'from_metrics_to_control'
				? heroContext.metricsTitle
				: heroContext.controlTitle
	);
	let heroSubtitle = $derived(
		plainLanguageMode
			? `${plainCopy.subtitle} Valdrics helps teams catch overspend early, route the right owner, and act safely before waste compounds.`
			: `${heroContext.subtitle} Valdrics helps teams catch overspend early, route the right owner, and act safely before waste compounds.`
	);
	let heroQuantPromise = $derived(heroContext.quantPromise);
	let primaryCtaLabel = $derived(
		experiments.ctaVariant === 'book_briefing' ? 'Book Executive Briefing' : 'Start Free'
	);
	let secondaryCtaLabel = $derived('See Plans');
	let secondaryCtaHref = $derived('#plans');
	let primaryCtaIntent = $derived(
		experiments.ctaVariant === 'book_briefing' ? 'executive_briefing' : heroContext.primaryIntent
	);
	let includeExperimentQueryParams = $derived(shouldIncludeExperimentQueryParams($page.url, false));
	let shouldRotateSnapshots = $derived(
		signalMapInView && documentVisible && REALTIME_SIGNAL_SNAPSHOTS.length > 1
	);
	let shouldRotateDemoSteps = $derived(documentVisible && MICRO_DEMO_STEPS.length > 1);
	let roiInputs = $derived(
		normalizeLandingRoiInputs({
			monthlySpendUsd: roiMonthlySpendUsd,
			expectedReductionPct: roiExpectedReductionPct,
			rolloutDays: roiRolloutDays,
			teamMembers: roiTeamMembers,
			blendedHourlyUsd: roiBlendedHourlyUsd,
			platformAnnualCostUsd: roiPlatformAnnualCostUsd
		})
	);
	let normalizedScenarioWasteWithoutPct = $derived(
		Math.min(35, Math.max(4, Math.round(Number(scenarioWasteWithoutPct) || 0)))
	);
	let normalizedScenarioWasteWithPct = $derived(
		Math.min(
			normalizedScenarioWasteWithoutPct - 1,
			Math.max(1, Math.round(Number(scenarioWasteWithPct) || 0))
		)
	);
	let normalizedScenarioWindowMonths = $derived(
		Math.min(24, Math.max(3, Math.round(Number(scenarioWindowMonths) || 0)))
	);
	let scenarioWasteWithoutUsd = $derived(
		Math.round((roiInputs.monthlySpendUsd * normalizedScenarioWasteWithoutPct) / 100)
	);
	let scenarioWasteWithUsd = $derived(
		Math.round((roiInputs.monthlySpendUsd * normalizedScenarioWasteWithPct) / 100)
	);
	let scenarioWasteRecoveryMonthlyUsd = $derived(
		Math.max(0, scenarioWasteWithoutUsd - scenarioWasteWithUsd)
	);
	let scenarioWasteRecoveryWindowUsd = $derived(
		scenarioWasteRecoveryMonthlyUsd * normalizedScenarioWindowMonths
	);
	let scenarioMaxBarUsd = $derived(Math.max(scenarioWasteWithoutUsd, scenarioWasteWithUsd, 1));
	let scenarioWithoutBarPct = $derived((scenarioWasteWithoutUsd / scenarioMaxBarUsd) * 100);
	let scenarioWithBarPct = $derived((scenarioWasteWithUsd / scenarioMaxBarUsd) * 100);

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
		pageReferrer = normalizeReferrer(document.referrer);
		const consent = storage?.getItem(LANDING_CONSENT_KEY);
		if (consent === 'accepted') {
			telemetryEnabled = true;
			initializeTelemetry();
		} else if (consent === 'rejected') {
			telemetryEnabled = false;
		} else {
			cookieBannerVisible = true;
		}

		const handleVisibility = () => {
			documentVisible = document.visibilityState === 'visible';
		};
		document.addEventListener('visibilitychange', handleVisibility);

		let signalMapObserver: IntersectionObserver | null = null;
		if (signalMapElement && typeof IntersectionObserver !== 'undefined') {
			signalMapObserver = new IntersectionObserver(
				(entries) => {
					const entry = entries[0];
					signalMapInView = Boolean(entry?.isIntersecting && entry.intersectionRatio > 0.12);
				},
				{ threshold: [0, 0.12, 0.5] }
			);
			signalMapObserver.observe(signalMapElement);
		}

		const seenSections = new Set<string>();
		let sectionObserver: IntersectionObserver | null = null;
		const landingSections = Array.from(
			document.querySelectorAll<HTMLElement>('[data-landing-section]')
		);
		if (landingSections.length > 0 && typeof IntersectionObserver !== 'undefined') {
			sectionObserver = new IntersectionObserver(
				(entries) => {
					for (const entry of entries) {
						if (!entry.isIntersecting || entry.intersectionRatio < 0.35) {
							continue;
						}
						const sectionId = (entry.target as HTMLElement).dataset.landingSection?.trim();
						if (!sectionId || seenSections.has(sectionId)) {
							continue;
						}

						seenSections.add(sectionId);
						markEngaged();
						emitLandingTelemetrySafe(
							'section_view',
							'landing_section',
							sectionId,
							buildTelemetryContext('engaged')
						);
					}
				},
				{ threshold: [0.15, 0.35, 0.6] }
			);

			for (const section of landingSections) {
				sectionObserver.observe(section);
			}
		}

		const seenMilestones = new Set<number>();
		const handleScroll = () => {
			const root = document.documentElement;
			const maxScrollable = Math.max(1, root.scrollHeight - window.innerHeight);
			const scrollProgress = Math.min(100, Math.max(0, (window.scrollY / maxScrollable) * 100));
			landingScrollProgressPct = scrollProgress;

			for (const milestone of LANDING_SCROLL_MILESTONES) {
				if (scrollProgress < milestone || seenMilestones.has(milestone)) {
					continue;
				}
				seenMilestones.add(milestone);
				if (milestone >= 50) {
					markEngaged();
				}
				emitLandingTelemetrySafe(
					'scroll_depth',
					'landing',
					`${milestone}`,
					buildTelemetryContext('engaged')
				);
			}
		};

		window.addEventListener('scroll', handleScroll, { passive: true });
		handleScroll();

		return () => {
			document.removeEventListener('visibilitychange', handleVisibility);
			window.removeEventListener('scroll', handleScroll);
			signalMapObserver?.disconnect();
			sectionObserver?.disconnect();
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

	function initializeTelemetry(): void {
		if (telemetryInitialized || !telemetryEnabled) return;
		const storage = getStorage();
		visitorId = resolveOrCreateLandingVisitorIdCore(storage);
		experiments = resolveLandingExperiments($page.url, visitorId);
		attribution = captureLandingAttributionCore($page.url, storage);
		telemetryInitialized = true;

		incrementLandingFunnelStageCore('view', storage);
		emitLandingTelemetryCore('landing_view', 'landing', 'public', buildTelemetryContext('view'));
		emitLandingTelemetryCore(
			'experiment_exposure',
			'landing',
			`${experiments.heroVariant}|${experiments.ctaVariant}|${experiments.sectionOrderVariant}`,
			buildTelemetryContext('view')
		);
	}

	function getTelemetryStorage(): Storage | undefined {
		return telemetryEnabled ? getStorage() : undefined;
	}

	function emitLandingTelemetrySafe(
		name: string,
		section: string,
		value?: string,
		context?: Parameters<typeof emitLandingTelemetryCore>[3]
	): void {
		if (!telemetryEnabled) return;
		emitLandingTelemetryCore(name, section, value, context);
	}

	function setTelemetryConsent(accepted: boolean): void {
		telemetryEnabled = accepted;
		cookieBannerVisible = false;
		const storage = getStorage();
		storage?.setItem(LANDING_CONSENT_KEY, accepted ? 'accepted' : 'rejected');
		if (accepted) {
			initializeTelemetry();
		}
	}

	function markEngaged(): void {
		if (engagedCaptured) return;
		engagedCaptured = true;
		incrementLandingFunnelStageCore('engaged', getTelemetryStorage());
		emitLandingTelemetrySafe(
			'landing_engaged',
			'landing',
			'interactive',
			buildTelemetryContext('engaged')
		);
	}

	function buildSignupHref(intent: string, extraParams: Record<string, string> = {}): string {
		const params = new URLSearchParams({
			intent,
			persona: activeBuyerRole.id
		});
		for (const [key, value] of Object.entries(extraParams)) {
			if (value) {
				params.set(key, value);
			}
		}
		if (includeExperimentQueryParams) {
			params.set('exp_hero', experiments.heroVariant);
			params.set('exp_cta', experiments.ctaVariant);
			params.set('exp_order', experiments.sectionOrderVariant);
		}
		params.set('entry', 'landing');
		appendUtmParams(params);
		return `${base}/auth/login?${params.toString()}`;
	}

	function buildPrimaryCtaHref(): string {
		return buildSignupHref(primaryCtaIntent);
	}

	function appendUtmParams(params: URLSearchParams): void {
		if (attribution.utm.source) params.set('utm_source', attribution.utm.source);
		if (attribution.utm.medium) params.set('utm_medium', attribution.utm.medium);
		if (attribution.utm.campaign) params.set('utm_campaign', attribution.utm.campaign);
		if (attribution.utm.term) params.set('utm_term', attribution.utm.term);
		if (attribution.utm.content) params.set('utm_content', attribution.utm.content);
	}

	function buildPlanCtaHref(planId: string): string {
		return buildSignupHref('start_plan', { plan: planId, source: 'plans' });
	}

	function buildFreeTierCtaHref(): string {
		return buildSignupHref('free_tier', { plan: 'free', source: 'free_tier' });
	}

	function buildTalkToSalesHref(source: string): string {
		const params = new URLSearchParams({
			entry: 'landing',
			source,
			persona: activeBuyerRole.id
		});
		appendUtmParams(params);
		return `${TALK_TO_SALES_PATH}?${params.toString()}`;
	}

	function selectSnapshot(index: number) {
		if (index < 0 || index >= REALTIME_SIGNAL_SNAPSHOTS.length) return;
		snapshotIndex = index;
		markEngaged();
		emitLandingTelemetrySafe(
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
		emitLandingTelemetrySafe(
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
		emitLandingTelemetrySafe(
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
		emitLandingTelemetrySafe(
			'micro_demo_step',
			'hero_demo',
			MICRO_DEMO_STEPS[index]?.id,
			buildTelemetryContext('engaged')
		);
	}

	function selectSignalLane(laneId: SignalLaneId): void {
		activeLaneId = laneId;
		markEngaged();
		emitLandingTelemetrySafe('lane_focus', 'signal_map', laneId, buildTelemetryContext('engaged'));
	}

	function trackCta(action: string, section: string, value: string): void {
		incrementLandingFunnelStageCore('cta', getTelemetryStorage());
		emitLandingTelemetrySafe(action, section, value, buildTelemetryContext('cta'));

		const isSignupIntent =
			value === 'start_free' ||
			value === 'book_briefing' ||
			value.includes('start_plan') ||
			value.includes('start_roi_assessment');
		if (isSignupIntent) {
			incrementLandingFunnelStageCore('signup_intent', getTelemetryStorage());
			emitLandingTelemetrySafe(
				'signup_intent',
				section,
				value,
				buildTelemetryContext('signup_intent')
			);
		}
	}

	function trackScenarioAdjust(control: string): void {
		markEngaged();
		if (scenarioAdjustCaptured) {
			return;
		}
		scenarioAdjustCaptured = true;
		emitLandingTelemetrySafe('scenario_adjust', 'simulator', control, buildTelemetryContext('engaged'));
	}

	function formatUsd(amount: number): string {
		return USD_WHOLE_FORMATTER.format(amount);
	}

	function togglePlainLanguageMode(): void {
		plainLanguageMode = !plainLanguageMode;
		markEngaged();
		emitLandingTelemetrySafe(
			'copy_mode_toggle',
			'hero',
			plainLanguageMode ? 'plain_english' : 'expert',
			buildTelemetryContext('engaged')
		);
	}
</script>

<div class="landing" itemscope itemtype="https://schema.org/SoftwareApplication">
	<div class="landing-scroll-progress" aria-hidden="true">
		<span style={`width:${landingScrollProgressPct}%;`}></span>
	</div>
	<meta itemprop="name" content="Valdrics" />
	<meta itemprop="operatingSystem" content="Web" />
	<meta itemprop="applicationCategory" content="BusinessApplication" />
	<meta
		itemprop="description"
		content="Valdrics helps teams reduce cloud and software spend by turning live spend signals into owner-assigned actions, approvals, and measurable savings."
	/>
	<meta itemprop="url" content={new URL($page.url.pathname, $page.url.origin).toString()} />
	<meta itemprop="image" content={new URL(`${assets}/og-image.png`, $page.url.origin).toString()} />

		<section id="hero" class="landing-hero" data-landing-section="hero">
			<div class="container mx-auto px-6 pt-10 pb-16">
				<div class="landing-hero-grid">
					<LandingHeroCopy
						heroTitle={heroTitle}
						heroSubtitle={heroSubtitle}
						heroQuantPromise={heroQuantPromise}
						primaryCtaLabel={primaryCtaLabel}
						secondaryCtaLabel={secondaryCtaLabel}
						secondaryCtaHref={secondaryCtaHref}
						primaryCtaHref={buildPrimaryCtaHref()}
						talkToSalesHref={buildTalkToSalesHref('hero')}
						plainLanguageMode={plainLanguageMode}
						onPrimaryCta={() => trackCta('cta_click', 'hero', experiments.ctaVariant)}
						onSecondaryCta={() => trackCta('cta_click', 'hero', 'see_plans')}
						onSimulatorCta={() => trackCta('cta_click', 'hero', 'open_simulator')}
						onTalkToSalesCta={() => trackCta('cta_click', 'hero', 'talk_to_sales')}
						onTogglePlainLanguage={togglePlainLanguageMode}
					/>

					<LandingSignalMapCard
						activeSnapshot={activeSnapshot}
						activeSignalLane={activeSignalLane}
						signalMapInView={signalMapInView}
						snapshotIndex={snapshotIndex}
						demoStepIndex={demoStepIndex}
						onSelectSignalLane={selectSignalLane}
						onSelectDemoStep={selectDemoStep}
						onSelectSnapshot={selectSnapshot}
						onSignalMapElementChange={(element) => {
							signalMapElement = element;
						}}
					/>
				</div>
			</div>
		</section>

	{#if experiments.sectionOrderVariant === 'workflow_first'}
		<LandingWorkflowSection />
	{:else}
		<LandingCloudHookSection
			activeHookState={activeHookState}
			hookStateIndex={hookStateIndex}
			cloudHookStates={CLOUD_HOOK_STATES}
			onSelectHookState={selectHookState}
		/>
	{/if}

	<LandingRoiSimulator
		normalizedScenarioWasteWithoutPct={normalizedScenarioWasteWithoutPct}
		normalizedScenarioWasteWithPct={normalizedScenarioWasteWithPct}
		normalizedScenarioWindowMonths={normalizedScenarioWindowMonths}
		scenarioWithoutBarPct={scenarioWithoutBarPct}
		scenarioWithBarPct={scenarioWithBarPct}
		scenarioWasteWithoutUsd={scenarioWasteWithoutUsd}
		scenarioWasteWithUsd={scenarioWasteWithUsd}
		scenarioWasteRecoveryMonthlyUsd={scenarioWasteRecoveryMonthlyUsd}
		scenarioWasteRecoveryWindowUsd={scenarioWasteRecoveryWindowUsd}
		monthlySpendUsd={roiInputs.monthlySpendUsd}
		scenarioWasteWithoutPct={scenarioWasteWithoutPct}
		scenarioWasteWithPct={scenarioWasteWithPct}
		scenarioWindowMonths={scenarioWindowMonths}
		formatUsd={formatUsd}
		onTrackScenarioAdjust={trackScenarioAdjust}
		onScenarioWasteWithoutChange={(value) => {
			scenarioWasteWithoutPct = value;
		}}
		onScenarioWasteWithChange={(value) => {
			scenarioWasteWithPct = value;
		}}
		onScenarioWindowChange={(value) => {
			scenarioWindowMonths = value;
		}}
	/>

	<LandingRoiPlannerCta
		href={buildSignupHref('roi_assessment', { source: 'simulator' })}
		worksheetHref={ROI_WORKSHEET_HREF}
		onTrackCta={() => trackCta('cta_click', 'roi', 'start_roi_assessment')}
		onTrackWorksheetCta={() => trackCta('cta_click', 'roi', 'download_roi_worksheet')}
	/>

	<LandingBenefitsSection />

	<LandingPlansSection
		{buildFreeTierCtaHref}
		{buildPlanCtaHref}
		talkToSalesHref={buildTalkToSalesHref('plans')}
		onTrackCta={trackCta}
	/>

	<LandingPersonaSection
		activeBuyerRole={activeBuyerRole}
		buyerRoleIndex={buyerRoleIndex}
		onSelectBuyerRole={selectBuyerRole}
	/>

	<LandingCapabilitiesSection onTrackCta={trackCta} />

	<LandingTrustSection
		onTrackCta={() => trackCta('cta_click', 'trust', 'request_named_references')}
		requestReferencesHref={buildSignupHref('named_references', { source: 'trust' })}
	/>

	<LandingLeadCaptureSection
		subscribeApiPath={SUBSCRIBE_API_PATH}
		startFreeHref={buildPrimaryCtaHref()}
		resourcesHref={RESOURCES_HREF}
		onTrackCta={trackCta}
	/>

	<div class="landing-mobile-sticky-cta" aria-label="Mobile quick actions">
		<a
			href={buildPrimaryCtaHref()}
			class="btn btn-primary"
			onclick={() => trackCta('cta_click', 'mobile_sticky', experiments.ctaVariant)}
		>
			{primaryCtaLabel}
		</a>
		<a
			href="#plans"
			class="btn btn-secondary"
			onclick={() => trackCta('cta_click', 'mobile_sticky', 'see_plans')}
		>
			Plans
		</a>
	</div>

	{#if landingScrollProgressPct >= 20}
		<a href="#hero" class="landing-back-to-top" onclick={() => trackCta('cta_click', 'utility', 'back_to_top')}>
			Back to top
		</a>
	{/if}

	<LandingExitIntentPrompt
		startFreeHref={buildPrimaryCtaHref()}
		resourcesHref={RESOURCES_HREF}
		subscribeApiPath={SUBSCRIBE_API_PATH}
		onTrackCta={trackCta}
	/>

	<LandingCookieConsent
		visible={cookieBannerVisible}
		onAccept={() => setTelemetryConsent(true)}
		onReject={() => setTelemetryConsent(false)}
		onClose={() => {
			cookieBannerVisible = false;
		}}
	/>

	{#if !cookieBannerVisible}
		<button
			type="button"
			class="landing-cookie-settings"
			onclick={() => {
				cookieBannerVisible = true;
			}}
		>
			Cookie Settings
		</button>
	{/if}
</div>
