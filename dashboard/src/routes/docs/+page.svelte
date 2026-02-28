<script lang="ts">
	import { base } from '$app/paths';
</script>

<svelte:head>
	<title>Documentation | Valdrics</title>
	<meta
		name="description"
		content="Valdrics documentation for setup, dashboard workflows, API usage, and operational guidance."
	/>
</svelte:head>

<section class="container mx-auto px-6 py-12 space-y-8">
	<header class="space-y-3">
		<h1 class="text-3xl font-bold text-ink-100">Documentation</h1>
		<p class="text-ink-300 max-w-3xl">
			Use these guides to set up Valdrics quickly, align teams on spend ownership, and execute
			reliable cost decisions with confidence.
		</p>
	</header>

	<div class="grid gap-6 md:grid-cols-2">
		<article class="glass-panel space-y-3">
			<h2 class="text-xl font-semibold">Quick Start</h2>
			<p class="text-ink-300">
				Connect providers, select your operating window, and prioritize the biggest cost and risk
				signals first.
			</p>
			<a href={`${base}/`} class="btn btn-secondary w-fit">Open Dashboard</a>
		</article>

		<article class="glass-panel space-y-3">
			<h2 class="text-xl font-semibold">API Reference</h2>
			<p class="text-ink-300">
				Review endpoint groups and request examples for product and platform integrations.
			</p>
			<a href={`${base}/docs/api`} class="btn btn-secondary w-fit">Open API Docs</a>
		</article>

		<article class="glass-panel space-y-3">
			<h2 class="text-xl font-semibold">Plan & Access</h2>
			<p class="text-ink-300">
				See current plan capabilities, billing model, and upgrade paths for advanced workflows.
			</p>
			<a href={`${base}/pricing`} class="btn btn-secondary w-fit">View Pricing</a>
		</article>

		<article class="glass-panel space-y-3">
			<h2 class="text-xl font-semibold">Policies & Legal</h2>
			<p class="text-ink-300">
				Review service terms, privacy commitments, and data handling posture.
			</p>
			<div class="flex flex-wrap gap-3">
				<a href={`${base}/terms`} class="btn btn-secondary w-fit">Terms</a>
				<a href={`${base}/privacy`} class="btn btn-secondary w-fit">Privacy</a>
			</div>
		</article>
	</div>

	<div class="glass-panel space-y-3">
		<h2 class="text-xl font-semibold">Repository Docs</h2>
		<p class="text-ink-300">
			Deployment and runbook documentation is maintained in the project repository.
		</p>
		<a
			href="https://github.com/Valdrix-AI/valdrix/tree/main/docs"
			target="_blank"
			rel="noreferrer"
			class="btn btn-secondary w-fit"
		>
			Browse GitHub Docs
		</a>
	</div>
</section>
