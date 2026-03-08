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
	import {
		resolveLandingExperiments,
		shouldIncludeExperimentQueryParams,
		type LandingExperimentAssignments
	} from '$lib/landing/landingExperiment';
	import type { LandingAttribution } from '$lib/landing/landingFunnel';
	import { normalizeLandingReferrer } from '$lib/landing/landingHeroTelemetry';
	import { buildLandingSalesHref, buildLandingSignupHref } from '$lib/landing/landingHeroLinks';
	import { resolveGeoCurrencyHint } from '$lib/landing/landingGeoCurrency';
	import { setupLandingHeroLifecycle } from '$lib/landing/landingHeroLifecycle';
	import { createLandingHeroTelemetryController } from '$lib/landing/landingHeroTelemetryController';
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
	import LandingHeroView from '$lib/components/landing/LandingHeroView.svelte';
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
	const ENTERPRISE_PATH = `${base}/enterprise`;
	const SUPPORTED_CURRENCY_CODES = new Set(SUPPORTED_CURRENCIES.map((currency) => currency.code));
	type LandingMotionProfile = 'subtle' | 'cinematic';
	if (!DEFAULT_SIGNAL_SNAPSHOT) {
		throw new Error('Realtime signal map requires at least one snapshot.');
	}
	function resolveLandingMotionProfile(url: URL): LandingMotionProfile {
		const value = url.searchParams.get('motion')?.trim().toLowerCase();
		return value === 'cinematic' ? 'cinematic' : 'subtle';
	}
	let signalMapElement: HTMLDivElement | null = null;
	let signalMapInView = $state(true), documentVisible = $state(true), snapshotIndex = $state(0), hookStateIndex = $state(0), buyerRoleIndex = $state(0), demoStepIndex = $state(0);
	let activeLaneId = $state<SignalLaneId | null>(null), visitorId = $state(''), pageReferrer = $state('');
	let experiments = $state<LandingExperimentAssignments>(resolveLandingExperiments($page.url, DEFAULT_EXPERIMENT_ASSIGNMENTS.seed));
	let attribution = $state<LandingAttribution>({ utm: {} }), engagedCaptured = $state(false);
	let rotationInterval: ReturnType<typeof setInterval> | null = null, demoRotationInterval: ReturnType<typeof setInterval> | null = null;
	let roiMonthlySpendUsd = $state(DEFAULT_LANDING_ROI_INPUTS.monthlySpendUsd), roiExpectedReductionPct = $state(DEFAULT_LANDING_ROI_INPUTS.expectedReductionPct), roiRolloutDays = $state(DEFAULT_LANDING_ROI_INPUTS.rolloutDays);
	let roiTeamMembers = $state(DEFAULT_LANDING_ROI_INPUTS.teamMembers), roiBlendedHourlyUsd = $state(DEFAULT_LANDING_ROI_INPUTS.blendedHourlyUsd), roiPlatformAnnualCostUsd = $state(DEFAULT_LANDING_ROI_INPUTS.platformAnnualCostUsd);
	let scenarioWasteWithoutPct = $state(18), scenarioWasteWithPct = $state(7), scenarioWindowMonths = $state(12), scenarioAdjustCaptured = $state(false), landingScrollProgressPct = $state(0);
	let prefersReducedMotion = $state(getReducedMotionPreference(browser && typeof window !== 'undefined' ? window : undefined));
	let telemetryEnabled = $state(false), telemetryInitialized = $state(false), cookieBannerVisible = $state(false), roiCurrencyCode = $state('USD');
	let activeSnapshot = $derived(REALTIME_SIGNAL_SNAPSHOTS[snapshotIndex] ?? DEFAULT_SIGNAL_SNAPSHOT);
	let activeHookState = $derived(CLOUD_HOOK_STATES[hookStateIndex] ?? CLOUD_HOOK_STATES[0]);
	let activeBuyerRole = $derived(BUYER_ROLE_VIEWS[buyerRoleIndex] ?? BUYER_ROLE_VIEWS[0]);
	let activeSignalLane = $derived(activeSnapshot.lanes.find((lane) => lane.id === activeLaneId) ?? activeSnapshot.lanes[0]);
	let heroContext = $derived(HERO_ROLE_CONTEXT[activeBuyerRole.id] ?? HERO_ROLE_CONTEXT.finops);
	let heroTitle = $derived(experiments.heroVariant === 'from_metrics_to_control' ? heroContext.metricsTitle : heroContext.controlTitle);
	let heroSubtitle = $derived(heroContext.subtitle);
	let heroQuantPromise = $derived(heroContext.quantPromise);
	let canonicalUrl = $derived(new URL($page.url.pathname, $page.url.origin).toString()), ogImageUrl = $derived(new URL(`${assets}/og-image.png`, $page.url.origin).toString());
	let primaryCtaLabel = $derived(experiments.ctaVariant === 'book_briefing' ? 'Book Executive Briefing' : 'Start Free');
	let secondaryCtaLabel = $derived('See Enterprise Path'), secondaryCtaHref = $derived(buildEnterpriseReviewHref('hero_secondary'));
	let roiPlannerHref = $derived(buildSignupHref('roi_assessment', { source: 'simulator' }));
	let plansTalkToSalesHref = $derived(buildTalkToSalesHref('plans')), requestValidationBriefingHref = $derived(buildTalkToSalesHref('trust_validation'));
	let showBackToTop = $derived(landingScrollProgressPct >= 8), motionProfile = $derived(resolveLandingMotionProfile($page.url));
	let primaryCtaIntent = $derived(experiments.ctaVariant === 'book_briefing' ? 'executive_briefing' : heroContext.primaryIntent);
	let primaryCtaHref = $derived(buildSignupHref(primaryCtaIntent)), freeTierCtaHref = $derived(buildSignupHref('free_tier', { plan: 'free', source: 'free_tier' }));
	let includeExperimentQueryParams = $derived(shouldIncludeExperimentQueryParams($page.url, false));
	let shouldRotateSnapshots = $derived(!prefersReducedMotion && documentVisible && signalMapInView && REALTIME_SIGNAL_SNAPSHOTS.length > 1);
	let shouldRotateDemoSteps = $derived(!prefersReducedMotion && documentVisible && MICRO_DEMO_STEPS.length > 1);
	let roiInputs = $derived(normalizeLandingRoiInputs({ monthlySpendUsd: roiMonthlySpendUsd, expectedReductionPct: roiExpectedReductionPct, rolloutDays: roiRolloutDays, teamMembers: roiTeamMembers, blendedHourlyUsd: roiBlendedHourlyUsd, platformAnnualCostUsd: roiPlatformAnnualCostUsd }));
	let normalizedScenarioWasteWithoutPct = $derived(Math.min(35, Math.max(4, Math.round(Number(scenarioWasteWithoutPct) || 0))));
	let normalizedScenarioWasteWithPct = $derived(Math.min(normalizedScenarioWasteWithoutPct - 1, Math.max(1, Math.round(Number(scenarioWasteWithPct) || 0))));
	let normalizedScenarioWindowMonths = $derived(Math.min(24, Math.max(3, Math.round(Number(scenarioWindowMonths) || 0))));
	let scenarioWasteWithoutUsd = $derived(Math.round((roiInputs.monthlySpendUsd * normalizedScenarioWasteWithoutPct) / 100));
	let scenarioWasteWithUsd = $derived(Math.round((roiInputs.monthlySpendUsd * normalizedScenarioWasteWithPct) / 100));
	let scenarioWasteRecoveryMonthlyUsd = $derived(Math.max(0, scenarioWasteWithoutUsd - scenarioWasteWithUsd));
	let scenarioWasteRecoveryWindowUsd = $derived(scenarioWasteRecoveryMonthlyUsd * normalizedScenarioWindowMonths);
	let scenarioMaxBarUsd = $derived(Math.max(scenarioWasteWithoutUsd, scenarioWasteWithUsd, 1)), scenarioWithoutBarPct = $derived((scenarioWasteWithoutUsd / scenarioMaxBarUsd) * 100), scenarioWithBarPct = $derived((scenarioWasteWithUsd / scenarioMaxBarUsd) * 100);
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
		pageReferrer = normalizeLandingReferrer(document.referrer);
		const consent = storage?.getItem(LANDING_CONSENT_KEY);
		if (consent === 'accepted') {
			telemetryEnabled = true;
			telemetry.initialize();
		} else if (consent === 'rejected') {
			telemetryEnabled = false;
		} else {
			cookieBannerVisible = true;
		}
		const stopLandingLifecycle = setupLandingHeroLifecycle({
			documentRef: document,
			windowRef: window,
			signalMapElement,
			scrollMilestones: LANDING_SCROLL_MILESTONES,
			onDocumentVisibilityChange: (isVisible) => {
				documentVisible = isVisible;
			},
			onSignalMapVisibilityChange: (isVisible) => {
				signalMapInView = isVisible;
			},
			onSectionView: (sectionId) => {
				markEngaged();
				emitLandingTelemetrySafe(
					'section_view',
					'landing_section',
					sectionId,
					buildTelemetryContext('engaged')
				);
			},
			onScrollProgressChange: (progressPct) => {
				landingScrollProgressPct = progressPct;
			},
			onScrollMilestone: (milestone) => {
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
		});
		return () => {
			geoCurrencyController.abort();
			clearTimeout(geoCurrencyTimeout);
			stopReducedMotionObservation();
			stopLandingLifecycle();
		};
	});
	function getStorage(): Storage | undefined {
		if (!browser) return undefined;
		return window.localStorage;
	}
	const telemetry = createLandingHeroTelemetryController({
		getTelemetryEnabled: () => telemetryEnabled,
		setTelemetryEnabled: (value) => (telemetryEnabled = value),
		getTelemetryInitialized: () => telemetryInitialized,
		setTelemetryInitialized: (value) => (telemetryInitialized = value),
		setCookieBannerVisible: (value) => (cookieBannerVisible = value),
		getEngagedCaptured: () => engagedCaptured,
		setEngagedCaptured: (value) => (engagedCaptured = value),
		getScenarioAdjustCaptured: () => scenarioAdjustCaptured,
		setScenarioAdjustCaptured: (value) => (scenarioAdjustCaptured = value),
		getVisitorId: () => visitorId,
		setVisitorId: (value) => (visitorId = value),
		getExperiments: () => experiments,
		setExperiments: (value) => (experiments = value),
		getAttribution: () => attribution,
		setAttribution: (value) => (attribution = value),
		getPersona: () => activeBuyerRole.id,
		getPagePath: () => $page.url.pathname,
		getReferrer: () => pageReferrer,
		getStorage,
		getPageUrl: () => $page.url,
		consentStorageKey: LANDING_CONSENT_KEY
	});
	const buildTelemetryContext = telemetry.buildContext;
	const emitLandingTelemetrySafe = telemetry.emitSafe;
	const markEngaged = telemetry.markEngaged;
	function setTelemetryConsent(accepted: boolean): void {
		telemetry.setConsent(accepted);
	}
	function closeCookieBanner(): void {
		cookieBannerVisible = false;
	}
	function openCookieSettings(): void {
		cookieBannerVisible = true;
	}
	function buildSignupHref(intent: string, extraParams: Record<string, string> = {}): string {
		return buildLandingSignupHref({
			basePath: base,
			intent,
			persona: activeBuyerRole.id,
			includeExperimentQueryParams,
			experiments,
			utm: attribution.utm,
			extraParams
		});
	}
	function buildPlanCtaHref(planId: string): string {
		return buildSignupHref('start_plan', { plan: planId, source: 'plans' });
	}
	function buildTalkToSalesHref(source: string): string {
		return buildLandingSalesHref({
			path: TALK_TO_SALES_PATH,
			source,
			persona: activeBuyerRole.id,
			utm: attribution.utm
		});
	}
	function buildEnterpriseReviewHref(source: string): string {
		return buildLandingSalesHref({
			path: ENTERPRISE_PATH,
			source,
			persona: activeBuyerRole.id,
			utm: attribution.utm
		});
	}
	function trackIndexedSelection(
		index: number,
		size: number,
		assign: (value: number) => void,
		eventName: string,
		section: string,
		value: string | undefined
	): void {
		if (index < 0 || index >= size) return;
		assign(index);
		markEngaged();
		emitLandingTelemetrySafe(eventName, section, value, buildTelemetryContext('engaged'));
	}
	const selectSnapshot = (index: number) =>
		trackIndexedSelection(
			index,
			REALTIME_SIGNAL_SNAPSHOTS.length,
			(value) => (snapshotIndex = value),
			'snapshot_select',
			'signal_map',
			REALTIME_SIGNAL_SNAPSHOTS[index]?.id
		);
	const selectHookState = (index: number) =>
		trackIndexedSelection(
			index,
			CLOUD_HOOK_STATES.length,
			(value) => (hookStateIndex = value),
			'hook_toggle',
			'cloud_hook',
			CLOUD_HOOK_STATES[index]?.id
		);
	const selectDemoStep = (index: number) =>
		trackIndexedSelection(
			index,
			MICRO_DEMO_STEPS.length,
			(value) => (demoStepIndex = value),
			'micro_demo_step',
			'hero_demo',
			MICRO_DEMO_STEPS[index]?.id
		);
	function selectSignalLane(laneId: SignalLaneId): void {
		activeLaneId = laneId;
		markEngaged();
		emitLandingTelemetrySafe('lane_focus', 'signal_map', laneId, buildTelemetryContext('engaged'));
	}
	function trackCta(action: string, section: string, value: string): void {
		telemetry.trackCta(action, section, value);
	}
	function trackScenarioAdjust(control: string): void {
		telemetry.trackScenarioAdjust(control);
	}
	function handleSignalMapElementChange(element: HTMLDivElement | null): void {
		signalMapElement = element;
	}
	function handleScenarioWasteWithoutChange(value: number): void {
		scenarioWasteWithoutPct = value;
	}
	function handleScenarioWasteWithChange(value: number): void {
		scenarioWasteWithPct = value;
	}
	function handleScenarioWindowChange(value: number): void {
		scenarioWindowMonths = value;
	}
	function formatUsd(amount: number, currency: string = roiCurrencyCode): string {
		return formatCurrencyAmount(amount, currency);
	}
	async function applyGeoCurrencyHint(signal: AbortSignal): Promise<void> {
		// Keep pricing deterministic in USD unless a trusted edge country hint maps to a supported currency.
		roiCurrencyCode = 'USD';
		const currencyCode = await resolveGeoCurrencyHint({
			requestEndpoint: GEO_CURRENCY_HINT_ENDPOINT,
			requestOrigin: $page.url.origin,
			hostname: browser && typeof window !== 'undefined' ? window.location.hostname : undefined,
			supportedCurrencyCodes: SUPPORTED_CURRENCY_CODES,
			signal
		});
		if (currencyCode) {
			roiCurrencyCode = currencyCode;
		}
	}
</script>
<LandingHeroView
	{motionProfile} {landingScrollProgressPct} canonicalUrl={canonicalUrl} imageUrl={ogImageUrl}
	{heroTitle} {heroSubtitle} quantPromise={heroQuantPromise}
	{primaryCtaLabel} {secondaryCtaLabel} {secondaryCtaHref}
	{primaryCtaHref} ctaVariant={experiments.ctaVariant}
	sectionOrderVariant={experiments.sectionOrderVariant}
	{activeHookState} {hookStateIndex} onSelectHookState={selectHookState}
	{activeSnapshot} {activeSignalLane} {signalMapInView} {snapshotIndex} {demoStepIndex}
	onSelectSignalLane={selectSignalLane} onSelectDemoStep={selectDemoStep}
	onSelectSnapshot={selectSnapshot} onSignalMapElementChange={handleSignalMapElementChange}
	{normalizedScenarioWasteWithoutPct} {normalizedScenarioWasteWithPct}
	{normalizedScenarioWindowMonths} {scenarioWithoutBarPct} {scenarioWithBarPct}
	{scenarioWasteWithoutUsd} {scenarioWasteWithUsd} {scenarioWasteRecoveryMonthlyUsd}
	{scenarioWasteRecoveryWindowUsd} monthlySpendUsd={roiInputs.monthlySpendUsd}
	{scenarioWasteWithoutPct} {scenarioWasteWithPct} {scenarioWindowMonths} {formatUsd}
	currencyCode={roiCurrencyCode} onTrackScenarioAdjust={trackScenarioAdjust}
	onScenarioWasteWithoutChange={handleScenarioWasteWithoutChange}
	onScenarioWasteWithChange={handleScenarioWasteWithChange}
	onScenarioWindowChange={handleScenarioWindowChange}
	{roiPlannerHref} {freeTierCtaHref} {buildPlanCtaHref} {plansTalkToSalesHref}
	{requestValidationBriefingHref} onePagerHref={ONE_PAGER_HREF} onTrackCta={trackCta}
	{cookieBannerVisible} onSetTelemetryConsent={setTelemetryConsent}
	onCloseCookieBanner={closeCookieBanner} onOpenCookieSettings={openCookieSettings}
	{showBackToTop}
/>
