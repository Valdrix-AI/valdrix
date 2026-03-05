<script lang="ts">
	import { base } from '$app/paths';
	import { onDestroy, onMount } from 'svelte';
	import {
		COMPLIANCE_FOUNDATION_BADGES,
		CUSTOMER_PROOF_STORIES,
		CUSTOMER_QUOTES,
		EXECUTIVE_CONFIDENCE_POINTS,
		TRUST_BENCHMARK_OUTCOMES,
		TRUST_ECOSYSTEM_BADGES
	} from '$lib/landing/heroContent';
	import {
		getReducedMotionPreference,
		observeReducedMotionPreference
	} from '$lib/landing/reducedMotion';

	const QUOTE_ROTATION_MS = 6500;
	const CUSTOMER_COMMENTS_POLL_MS = 20_000;
	const CUSTOMER_COMMENTS_FEED_HREF = `${base}/api/marketing/customer-comments`;
	let activeQuoteIndex = $state(0);
	let prefersReducedMotion = $state(false);
	let quoteRotationInterval: ReturnType<typeof setInterval> | null = null;
	let customerCommentsPollInterval: ReturnType<typeof setInterval> | null = null;
	let customerCommentsFetchInFlight = false;
	let customerQuotes = $state([...CUSTOMER_QUOTES]);
	let activeQuote = $derived(customerQuotes[activeQuoteIndex] ?? customerQuotes[0]);

	function stopQuoteRotation(): void {
		if (!quoteRotationInterval) return;
		clearInterval(quoteRotationInterval);
		quoteRotationInterval = null;
	}

	function startQuoteRotation(): void {
		if (quoteRotationInterval || prefersReducedMotion || customerQuotes.length < 2) return;
		quoteRotationInterval = setInterval(() => {
			activeQuoteIndex = (activeQuoteIndex + 1) % customerQuotes.length;
		}, QUOTE_ROTATION_MS);
	}

	function setCustomerQuotes(quotes: Array<{ quote: string; attribution: string }>): void {
		if (quotes.length === 0) return;
		const unchanged =
			quotes.length === customerQuotes.length &&
			quotes.every(
				(quote, index) =>
					quote.quote === customerQuotes[index]?.quote &&
					quote.attribution === customerQuotes[index]?.attribution
			);
		if (unchanged) return;
		customerQuotes = quotes;
		if (activeQuoteIndex >= quotes.length) {
			activeQuoteIndex = 0;
		}
		stopQuoteRotation();
		startQuoteRotation();
	}

	async function loadCustomerComments(signal?: AbortSignal): Promise<void> {
		if (customerCommentsFetchInFlight) return;
		customerCommentsFetchInFlight = true;
		try {
			const response = await fetch(CUSTOMER_COMMENTS_FEED_HREF, {
				method: 'GET',
				headers: { accept: 'application/json' },
				cache: 'no-store',
				signal
			});
			if (!response.ok) return;
			const payload = (await response.json()) as {
				items?: Array<{ quote?: string; attribution?: string }>;
			};
			const quotes = (payload.items ?? [])
				.map((item) => ({
					quote: (item.quote ?? '').trim(),
					attribution: (item.attribution ?? '').trim()
				}))
				.filter((item) => item.quote && item.attribution)
				.slice(0, 8);
			setCustomerQuotes(quotes);
		} catch {
			// Keep local fallback quotes if feed is unavailable.
		} finally {
			customerCommentsFetchInFlight = false;
		}
	}

	function stopCustomerCommentsPolling(): void {
		if (!customerCommentsPollInterval) return;
		clearInterval(customerCommentsPollInterval);
		customerCommentsPollInterval = null;
	}

	function startCustomerCommentsPolling(): void {
		if (customerCommentsPollInterval) return;
		customerCommentsPollInterval = setInterval(() => {
			if (document.visibilityState !== 'visible') return;
			void loadCustomerComments();
		}, CUSTOMER_COMMENTS_POLL_MS);
	}

	function selectQuote(index: number): void {
		if (index < 0 || index >= customerQuotes.length) return;
		activeQuoteIndex = index;
		stopQuoteRotation();
		startQuoteRotation();
	}

	function showPreviousQuote(): void {
		if (customerQuotes.length < 2) return;
		activeQuoteIndex = (activeQuoteIndex - 1 + customerQuotes.length) % customerQuotes.length;
		stopQuoteRotation();
		startQuoteRotation();
	}

	function showNextQuote(): void {
		if (customerQuotes.length < 2) return;
		activeQuoteIndex = (activeQuoteIndex + 1) % customerQuotes.length;
		stopQuoteRotation();
		startQuoteRotation();
	}

	let {
		onTrackCta,
		requestValidationBriefingHref,
		onePagerHref,
		globalComplianceWorkbookHref = '/resources/global-finops-compliance-workbook.md'
	}: {
		onTrackCta: (
			value:
				| 'request_validation_briefing'
				| 'download_executive_one_pager'
				| 'download_global_compliance_workbook'
		) => void;
		requestValidationBriefingHref: string;
		onePagerHref: string;
		globalComplianceWorkbookHref?: string;
	} = $props();

	onMount(() => {
		const customerCommentsController = new AbortController();
		void loadCustomerComments(customerCommentsController.signal);
		const onVisibilityChange = () => {
			if (document.visibilityState === 'visible') {
				void loadCustomerComments();
			}
		};
		document.addEventListener('visibilitychange', onVisibilityChange);
		startCustomerCommentsPolling();
		prefersReducedMotion = getReducedMotionPreference(window);
		const stopReducedMotionObservation = observeReducedMotionPreference(window, (value) => {
			prefersReducedMotion = value;
			if (value) {
				stopQuoteRotation();
				return;
			}
			startQuoteRotation();
		});
		startQuoteRotation();
		return () => {
			customerCommentsController.abort();
			document.removeEventListener('visibilitychange', onVisibilityChange);
			stopCustomerCommentsPolling();
			stopReducedMotionObservation();
			stopQuoteRotation();
		};
	});

	onDestroy(() => {
		stopCustomerCommentsPolling();
		stopQuoteRotation();
	});
</script>

<section
	id="trust"
	class="container mx-auto px-6 pb-16 landing-section-lazy"
	data-landing-section="proof"
>
	<div class="landing-section-head">
		<h2 class="landing-h2">Proof and Trust</h2>
		<p class="landing-section-sub">
			Outcome patterns, security baseline, and an optional enterprise diligence lane.
		</p>
	</div>

	<div class="landing-validation-cta glass-panel" aria-label="Proof and Trust">
		<p class="landing-proof-k">Optional Enterprise Diligence</p>
		<p class="landing-p">
			Need formal security and procurement review? Use the enterprise lane for governance artifacts,
			validation briefing, and rollout planning support.
		</p>
		<div class="landing-lead-actions">
			<a
				href={requestValidationBriefingHref}
				class="btn btn-primary w-fit pulse-glow"
				onclick={() => onTrackCta('request_validation_briefing')}
			>
				Talk to Sales for Validation
			</a>
			<a
				href={onePagerHref}
				class="btn btn-secondary w-fit"
				onclick={() => onTrackCta('download_executive_one_pager')}
			>
				Download Executive One-Pager
			</a>
		</div>
		<p class="landing-more-resources">
			Enterprise resources:
			<a href={`${base}/enterprise`}>Enterprise Governance Overview</a>
			•
			<a
				href={globalComplianceWorkbookHref}
				onclick={() => onTrackCta('download_global_compliance_workbook')}
			>
				Access Control & Compliance Checklist
			</a>
		</p>
		<p class="landing-trust-note">Validation briefing is ungated. No login required.</p>
		<p class="landing-trust-note">
			Valdrics is prelaunch. Public customer logos and production outcome studies will be published
			post go-live. Current proof reflects design-partner sessions and benchmark ranges.
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

	<div class="landing-trust-ecosystem">
		<p class="landing-proof-k">Platform Coverage</p>
		<div class="landing-trust-badges">
			{#each TRUST_ECOSYSTEM_BADGES as badge (badge)}
				<span class="landing-trust-badge">{badge}</span>
			{/each}
		</div>
	</div>

	<div class="landing-story-grid">
		{#each CUSTOMER_PROOF_STORIES as story (story.title)}
			<article class="glass-panel landing-story-card">
				<p class="landing-proof-k">{story.title}</p>
				<p class="landing-story-label">Before</p>
				<p class="landing-p">{story.before}</p>
				<p class="landing-story-label">After</p>
				<p class="landing-p">{story.after}</p>
				<p class="landing-trust-benchmark-k">{story.impact}</p>
			</article>
		{/each}
	</div>

	<div class="landing-trust-benchmarks">
		{#each TRUST_BENCHMARK_OUTCOMES as outcome (outcome.title)}
			<article class="glass-panel landing-trust-benchmark">
				<p class="landing-proof-k">Outcome Pattern</p>
				<h3 class="landing-h3">{outcome.title}</h3>
				<p class="landing-p">{outcome.detail}</p>
				<p class="landing-trust-benchmark-k">{outcome.benchmark}</p>
			</article>
		{/each}
	</div>

	<div class="landing-testimonial-rotator glass-panel" aria-live="polite" aria-atomic="true">
		<div class="landing-testimonial-head">
			<p class="landing-proof-k">Design-Partner Comments</p>
			<p class="landing-testimonial-counter">{activeQuoteIndex + 1}/{customerQuotes.length}</p>
		</div>
		{#if activeQuote}
			<blockquote class="landing-testimonial-card">
				<p class="landing-testimonial-quote">"{activeQuote.quote}"</p>
				<cite class="landing-testimonial-cite">{activeQuote.attribution}</cite>
			</blockquote>
		{/if}
		<div class="landing-testimonial-controls">
			<button
				type="button"
				class="landing-testimonial-nav"
				aria-label="Previous design-partner comment"
				disabled={customerQuotes.length < 2}
				onclick={showPreviousQuote}
			>
				Prev
			</button>
			<div class="landing-testimonial-dots" role="group" aria-label="Design-partner comment selector">
				{#each customerQuotes as quote, index (quote.quote)}
					<button
						type="button"
						class="landing-testimonial-dot"
						aria-label={`Show design-partner comment ${index + 1}`}
						aria-pressed={activeQuoteIndex === index}
						onclick={() => selectQuote(index)}
					></button>
				{/each}
			</div>
			<button
				type="button"
				class="landing-testimonial-nav"
				aria-label="Next design-partner comment"
				disabled={customerQuotes.length < 2}
				onclick={showNextQuote}
			>
				Next
			</button>
		</div>
	</div>

	<div class="landing-compliance-block">
		<p class="landing-proof-k">Security and compliance essentials</p>
		<div class="landing-trust-badges">
			{#each COMPLIANCE_FOUNDATION_BADGES as badge (badge)}
				<span
					class="landing-trust-badge {badge.includes('ISO 27001') || badge.includes('DORA')
						? 'is-featured'
						: ''}">{badge}</span
				>
			{/each}
		</div>
	</div>
	<p class="landing-trust-note">
		Use the briefing and one-pager to align engineering, finance, and security before kickoff.
	</p>
</section>
