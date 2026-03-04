<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { browser } from '$app/environment';
	import { base } from '$app/paths';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import AuthGate from '$lib/components/AuthGate.svelte';
	import LandingRoiCalculator from '$lib/components/landing/LandingRoiCalculator.svelte';
	import {
		DEFAULT_LANDING_ROI_INPUTS,
		calculateLandingRoi,
		normalizeLandingRoiInputs,
		formatCurrencyAmount,
		SUPPORTED_CURRENCIES
	} from '$lib/landing/roiCalculator';
	import '$lib/components/LandingHero.css';

	let { data } = $props();
	const GEO_CURRENCY_HINT_ENDPOINT = `${base}/api/geo/currency`;
	const GEO_CURRENCY_HINT_TIMEOUT_MS = 1200;
	const SUPPORTED_CURRENCY_CODES = new Set(SUPPORTED_CURRENCIES.map((currency) => currency.code));

	let roiMonthlySpendUsd = $state(DEFAULT_LANDING_ROI_INPUTS.monthlySpendUsd);
	let roiExpectedReductionPct = $state(DEFAULT_LANDING_ROI_INPUTS.expectedReductionPct);
	let roiRolloutDays = $state(DEFAULT_LANDING_ROI_INPUTS.rolloutDays);
	let roiTeamMembers = $state(DEFAULT_LANDING_ROI_INPUTS.teamMembers);
	let roiBlendedHourlyUsd = $state(DEFAULT_LANDING_ROI_INPUTS.blendedHourlyUsd);
	let roiPlatformAnnualCostUsd = $state(DEFAULT_LANDING_ROI_INPUTS.platformAnnualCostUsd);
	let roiCurrencyCode = $state('USD');

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
	let roiResult = $derived(calculateLandingRoi(roiInputs));

	function formatUsd(amount: number, currency: string = roiCurrencyCode): string {
		return formatCurrencyAmount(amount, currency);
	}

	onMount(() => {
		const geoCurrencyController = new AbortController();
		const geoCurrencyTimeout = setTimeout(
			() => geoCurrencyController.abort(),
			GEO_CURRENCY_HINT_TIMEOUT_MS
		);
		void applyGeoCurrencyHint(geoCurrencyController.signal).finally(() => {
			clearTimeout(geoCurrencyTimeout);
		});
	});

	async function applyGeoCurrencyHint(signal: AbortSignal): Promise<void> {
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
			// Keep deterministic USD fallback.
		}
	}
</script>

<svelte:head>
	<title>ROI Planner | Valdrics</title>
	<meta
		name="description"
		content="Build a full 12-month ROI plan with your own cloud and software spend assumptions before rollout."
	/>
</svelte:head>

<div class="container mx-auto px-6 py-10">
	<div class="max-w-3xl mb-8">
		<h1 class="text-3xl md:text-4xl font-semibold text-ink-100">ROI Planner Workspace</h1>
		<p class="text-ink-300 mt-3">
			Use your own spend profile to estimate savings potential, payback window, and net annual
			impact before rollout decisions.
		</p>
	</div>

	<AuthGate
		authenticated={!!data.user}
		action="open the ROI planner workspace"
		className="card py-12 text-center"
	>
		<LandingRoiCalculator
			sectionId="roi-planner"
			heading="Build your 12-month ROI plan"
			subtitle="Set realistic assumptions, pressure-test rollout timelines, and align engineering and finance on expected value."
			ctaLabel="Continue to Guided Setup"
			ctaNote="Directional planning model. Validate assumptions with your own usage and contract baselines."
			{roiInputs}
			{roiResult}
			{roiMonthlySpendUsd}
			{roiExpectedReductionPct}
			{roiRolloutDays}
			{roiTeamMembers}
			{roiBlendedHourlyUsd}
			buildRoiCtaHref={`${base}/onboarding?intent=roi_assessment`}
			{formatUsd}
			onRoiControlInput={() => {}}
			onRoiMonthlySpendChange={(value) => {
				roiMonthlySpendUsd = value;
			}}
			onRoiExpectedReductionChange={(value) => {
				roiExpectedReductionPct = value;
			}}
			onRoiRolloutDaysChange={(value) => {
				roiRolloutDays = value;
			}}
			onRoiTeamMembersChange={(value) => {
				roiTeamMembers = value;
			}}
			onRoiBlendedHourlyChange={(value) => {
				roiBlendedHourlyUsd = value;
			}}
			onRoiCta={() => {}}
			currencyCode={roiCurrencyCode}
		/>
	</AuthGate>
</div>
