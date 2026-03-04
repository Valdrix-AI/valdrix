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
		normalizeLandingRoiInputs,
		formatCurrencyAmount,
		SUPPORTED_CURRENCIES
	} from '$lib/landing/roiCalculator';
	import {
		getReducedMotionPreference,
		observeReducedMotionPreference
	} from '$lib/landing/reducedMotion';
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
	import LandingTrustSection from '$lib/components/landing/LandingTrustSection.svelte';
	import LandingCookieConsent from '$lib/components/landing/LandingCookieConsent.svelte';
	import './LandingHero.css';

	const DEFAULT_EXPERIMENT_ASSIGNMENTS: LandingExperimentAssignments = Object.freeze({
		buyerPersonaDefault: 'cto',
		heroVariant: 'control_every_dollar',
		ctaVariant: 'start_free',
		sectionOrderVariant: 'problem_first',
		seed: 'default'
	});

	const SNAPSHOT_ROTATION_MS = 4400;
	const DEMO_ROTATION_MS = 3200;
	const LANDING_SCROLL_MILESTONES = Object.freeze([25, 50, 75, 95]);
	const LANDING_CONSENT_KEY = 'valdrics.cookie_consent.v1';
	const GEO_CURRENCY_HINT_ENDPOINT = `${base}/api/geo/currency`;
	const GEO_CURRENCY_HINT_TIMEOUT_MS = 1200;
	const DEFAULT_SIGNAL_SNAPSHOT = REALTIME_SIGNAL_SNAPSHOTS[0];
	const ONE_PAGER_HREF = `${base}/resources/valdrics-enterprise-one-pager.md`;
	const TALK_TO_SALES_PATH = `${base}/talk-to-sales`;
	const SUPPORTED_CURRENCY_CODES = new Set(SUPPORTED_CURRENCIES.map((currency) => currency.code));

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
	let landingScrollProgressPct = $state(0);
	let prefersReducedMotion = $state(
		getReducedMotionPreference(browser && typeof window !== 'undefined' ? window : undefined)
	);
	let telemetryEnabled = $state(false);
	let telemetryInitialized = $state(false);
	let cookieBannerVisible = $state(false);
	let roiCurrencyCode = $state('USD');

	let activeSnapshot = $derived(
		REALTIME_SIGNAL_SNAPSHOTS[snapshotIndex] ?? DEFAULT_SIGNAL_SNAPSHOT
	);
	let activeHookState = $derived(CLOUD_HOOK_STATES[hookStateIndex] ?? CLOUD_HOOK_STATES[0]);
	let activeBuyerRole = $derived(BUYER_ROLE_VIEWS[buyerRoleIndex] ?? BUYER_ROLE_VIEWS[0]);
	let activeSignalLane = $derived(
		activeSnapshot.lanes.find((lane) => lane.id === activeLaneId) ?? activeSnapshot.lanes[0]
	);
	let heroContext = $derived(HERO_ROLE_CONTEXT[activeBuyerRole.id] ?? HERO_ROLE_CONTEXT.finops);
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
	let secondaryCtaLabel = $derived('See it in action');
	let secondaryCtaHref = $derived('#signal-map');
	let primaryCtaIntent = $derived(
		experiments.ctaVariant === 'book_briefing' ? 'executive_briefing' : heroContext.primaryIntent
	);
	let includeExperimentQueryParams = $derived(shouldIncludeExperimentQueryParams($page.url, false));
	let shouldRotateSnapshots = $derived(
		!prefersReducedMotion &&
			documentVisible &&
			signalMapInView &&
			REALTIME_SIGNAL_SNAPSHOTS.length > 1
	);
	let shouldRotateDemoSteps = $derived(
		!prefersReducedMotion && documentVisible && MICRO_DEMO_STEPS.length > 1
	);
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

		// Auto-synchronize focus during rotation
		if (shouldRotateSnapshots) {
			const watchLane = activeSnapshot.lanes.find(
				(lane) => lane.severity === 'watch' || lane.severity === 'critical'
			);
			if (watchLane && watchLane.id !== activeLaneId) {
				activeLaneId = watchLane.id;
			}
		}
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
		const geoCurrencyController = new AbortController();
		const geoCurrencyTimeout = setTimeout(
			() => geoCurrencyController.abort(),
			GEO_CURRENCY_HINT_TIMEOUT_MS
		);
		void applyGeoCurrencyHint(geoCurrencyController.signal).finally(() => {
			clearTimeout(geoCurrencyTimeout);
		});

		const storage = browser ? window.localStorage : undefined;
		const stopReducedMotionObservation = observeReducedMotionPreference(window, (value) => {
			prefersReducedMotion = value;
		});
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
			geoCurrencyController.abort();
			clearTimeout(geoCurrencyTimeout);
			stopReducedMotionObservation();
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
		emitLandingTelemetrySafe(
			'scenario_adjust',
			'simulator',
			control,
			buildTelemetryContext('engaged')
		);
	}

	function formatUsd(amount: number, currency: string = roiCurrencyCode): string {
		return formatCurrencyAmount(amount, currency);
	}

	async function applyGeoCurrencyHint(signal: AbortSignal): Promise<void> {
		// Keep pricing deterministic in USD unless a trusted edge country hint maps to a supported currency.
		roiCurrencyCode = 'USD';
		if (browser && typeof window !== 'undefined') {
			const host = window.location.hostname.toLowerCase();
			if (host === 'localhost' || host === '127.0.0.1' || host === '::1') {
				return;
			}
		}

		let requestUrl: string;
		try {
			requestUrl = new URL(GEO_CURRENCY_HINT_ENDPOINT, $page.url.origin).toString();
		} catch {
			return;
		}

		try {
			const response = await fetch(requestUrl, {
				method: 'GET',
				headers: { accept: 'application/json' },
				cache: 'no-store',
				signal
			});
			if (!response.ok) return;
			const payload = (await response.json()) as { currencyCode?: string };
			const currencyCode = String(payload.currencyCode ?? '')
				.trim()
				.toUpperCase();
			if (!SUPPORTED_CURRENCY_CODES.has(currencyCode)) return;
			roiCurrencyCode = currencyCode;
		} catch {
			// Keep locale/timezone fallback when geo hint is unavailable.
		}
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
		<div class="container mx-auto px-6 pt-8 pb-12 sm:pt-10 sm:pb-16">
			<LandingHeroCopy
				{heroTitle}
				{heroSubtitle}
				{primaryCtaLabel}
				{secondaryCtaLabel}
				{secondaryCtaHref}
				primaryCtaHref={buildPrimaryCtaHref()}
				onPrimaryCta={() => trackCta('cta_click', 'hero', experiments.ctaVariant)}
				onSecondaryCta={() => trackCta('cta_click', 'hero', 'see_signal_map')}
			/>
		</div>
	</section>

	{#if experiments.sectionOrderVariant === 'workflow_first'}
		<LandingWorkflowSection />
	{:else}
		<LandingCloudHookSection
			{activeHookState}
			{hookStateIndex}
			cloudHookStates={CLOUD_HOOK_STATES}
			onSelectHookState={selectHookState}
		/>
	{/if}

	<section
		id="signal-map"
		class="container mx-auto px-6 pb-12 md:pb-16 landing-section-lazy"
		data-landing-section="signal_map"
	>
		<div class="landing-section-head">
			<h2 class="landing-h2">See it in action</h2>
			<p class="landing-section-sub">
				One shared signal map for cost, risk, ownership, and controlled execution.
			</p>
		</div>
		<LandingSignalMapCard
			{activeSnapshot}
			{activeSignalLane}
			{signalMapInView}
			{snapshotIndex}
			{demoStepIndex}
			onSelectSignalLane={selectSignalLane}
			onSelectDemoStep={selectDemoStep}
			onSelectSnapshot={selectSnapshot}
			onSignalMapElementChange={(element) => {
				signalMapElement = element;
			}}
		/>
	</section>

	<LandingRoiSimulator
		{normalizedScenarioWasteWithoutPct}
		{normalizedScenarioWasteWithPct}
		{normalizedScenarioWindowMonths}
		{scenarioWithoutBarPct}
		{scenarioWithBarPct}
		{scenarioWasteWithoutUsd}
		{scenarioWasteWithUsd}
		{scenarioWasteRecoveryMonthlyUsd}
		{scenarioWasteRecoveryWindowUsd}
		monthlySpendUsd={roiInputs.monthlySpendUsd}
		{scenarioWasteWithoutPct}
		{scenarioWasteWithPct}
		{scenarioWindowMonths}
		{formatUsd}
		currencyCode={roiCurrencyCode}
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
		onTrackCta={() => trackCta('cta_click', 'roi', 'start_roi_assessment')}
	/>

	<LandingBenefitsSection />

	<LandingPlansSection
		{buildFreeTierCtaHref}
		{buildPlanCtaHref}
		talkToSalesHref={buildTalkToSalesHref('plans')}
		onTrackCta={trackCta}
	/>

	<LandingTrustSection
		onTrackCta={(value) => trackCta('cta_click', 'trust', value)}
		requestValidationBriefingHref={buildSignupHref('executive_briefing', {
			source: 'trust_validation'
		})}
		onePagerHref={ONE_PAGER_HREF}
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
			href="#signal-map"
			class="btn btn-secondary"
			onclick={() => trackCta('cta_click', 'mobile_sticky', 'see_signal_map')}
		>
			See it in action
		</a>
	</div>

	{#if landingScrollProgressPct >= 8}
		<a
			href="#hero"
			class="landing-back-to-top"
			onclick={() => trackCta('cta_click', 'utility', 'back_to_top')}
		>
			Back to top
		</a>
	{/if}

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
