<script lang="ts">
	import { base } from '$app/paths';
</script>

<svelte:head>
	<title>Proof Pack | Valdrics</title>
	<meta
		name="description"
		content="Structured proof pack for Valdrics: control integrity, governance posture, deterministic execution, and operational resilience."
	/>
</svelte:head>

<section class="container mx-auto px-6 py-12 space-y-8">
	<header class="space-y-3">
		<p class="text-xs uppercase tracking-[0.18em] text-accent-300 font-bold">Proof Pack</p>
		<h1 class="text-3xl font-bold text-ink-100">Executive and technical proof for buyer diligence</h1>
		<p class="text-ink-300 max-w-3xl">
			This page consolidates high-signal proof categories used during evaluation cycles across
			leadership, security, finance, and platform teams.
		</p>
	</header>

	<div class="grid gap-6 md:grid-cols-2">
		<article class="glass-panel space-y-3">
			<h2 class="text-xl font-semibold">Economic Control Integrity</h2>
			<p class="text-ink-300">
				Signals, ownership, and policy checks are linked in one deterministic loop so financial
				decisions are made before month-end surprises.
			</p>
			<ul class="text-sm text-ink-300 space-y-1 list-disc pl-5">
				<li>Cross-surface visibility across cloud, SaaS, ITAM/license, and platform tooling.</li>
				<li>Buyer-mode narratives for CTO, FinOps, Security, and CFO priorities.</li>
				<li>Controlled section narratives for experimentation without message drift.</li>
			</ul>
		</article>

		<article class="glass-panel space-y-3">
			<h2 class="text-xl font-semibold">Deterministic Execution</h2>
			<p class="text-ink-300">
				Execution pathways remain policy-led and replayable, with explicit approval contexts and
				snapshot-level traceability.
			</p>
			<ul class="text-sm text-ink-300 space-y-1 list-disc pl-5">
				<li>Realtime Signal Map snapshots with explicit lane severity classes.</li>
				<li>Lane-level detail drilldowns for operational interpretation.</li>
				<li>Deterministic variant assignment for controlled go-to-market experiments.</li>
			</ul>
		</article>

		<article class="glass-panel space-y-3">
			<h2 class="text-xl font-semibold">Funnel and Attribution Telemetry</h2>
			<p class="text-ink-300">
				Landing analytics capture first-touch UTM context, stage-level progression, and CTA intent
				while keeping interaction dispatch non-blocking.
			</p>
			<ul class="text-sm text-ink-300 space-y-1 list-disc pl-5">
				<li>Tracked stages: view, engaged, CTA, and signup intent.</li>
				<li>Session funnel summary for conversion progression visibility.</li>
				<li>Telemetry payload context includes persona and experiment lineage.</li>
			</ul>
		</article>

		<article class="glass-panel space-y-3">
			<h2 class="text-xl font-semibold">Operational Resilience and Accessibility</h2>
			<p class="text-ink-300">
				Landing UX hardening includes cleanup-safe intervals, tab semantics, reduced-motion behavior,
				and mobile-first tap target sizing.
			</p>
			<ul class="text-sm text-ink-300 space-y-1 list-disc pl-5">
				<li>No unbounded timers; lifecycle cleanup is tested.</li>
				<li>Interactive controls provide keyboard and ARIA pathways.</li>
				<li>Lazy section rendering improves perceived performance on long pages.</li>
			</ul>
		</article>
	</div>

	<div class="glass-panel space-y-3">
		<h2 class="text-xl font-semibold">Next validation surfaces</h2>
		<p class="text-ink-300">
			Use the links below for deeper implementation evidence and API-level details.
		</p>
		<div class="flex flex-wrap gap-3">
			<a href={`${base}/docs`} class="btn btn-secondary">Documentation</a>
			<a href={`${base}/docs/api`} class="btn btn-secondary">API Reference</a>
			<a href={`${base}/pricing`} class="btn btn-secondary">Pricing</a>
			<a href={`${base}/`} class="btn btn-primary">Back to Landing</a>
		</div>
	</div>
</section>
