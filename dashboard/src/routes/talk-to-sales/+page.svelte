<script lang="ts">
	import { base } from '$app/paths';

	const salesMailHref =
		'mailto:sales@valdrics.ai?subject=Valdrics%20Enterprise%20Briefing&body=Team%20size%3A%0ACloud%2FSaaS%20scope%3A%0ATarget%20timeline%3A';
</script>

<svelte:head>
	<title>Talk to Sales | Valdrics</title>
	<meta
		name="description"
		content="Book a Valdrics enterprise briefing for cloud and software spend control, rollout planning, and procurement-ready implementation guidance."
	/>
</svelte:head>

<section class="container mx-auto px-6 py-12 space-y-8">
	<header class="space-y-3 max-w-3xl">
		<h1 class="text-3xl font-bold text-ink-100">Talk to Sales</h1>
		<p class="text-ink-300">
			Plan an enterprise rollout with shared finance and engineering ownership, procurement-ready trust
			answers, and a realistic implementation model.
		</p>
	</header>

	<div class="grid gap-6 md:grid-cols-3">
		<article class="glass-panel space-y-2">
			<p class="text-xs uppercase tracking-[0.12em] text-ink-500">Procurement</p>
			<h2 class="text-xl font-semibold">Compliance and security review</h2>
			<p class="text-ink-300">
				Walk through SSO, SCIM, role approvals, retention controls, and legal documentation with your
				security and legal teams.
			</p>
		</article>
		<article class="glass-panel space-y-2">
			<p class="text-xs uppercase tracking-[0.12em] text-ink-500">Implementation</p>
			<h2 class="text-xl font-semibold">Rollout and ownership model</h2>
			<p class="text-ink-300">
				Define first sources, owner routing, and governance checkpoints so your first value cycle lands
				in days, not quarters.
			</p>
		</article>
		<article class="glass-panel space-y-2">
			<p class="text-xs uppercase tracking-[0.12em] text-ink-500">Finance</p>
			<h2 class="text-xl font-semibold">TCO and ROI planning</h2>
			<p class="text-ink-300">
				Review subscription, rollout effort, and controllable-spend opportunity with assumptions tailored
				to your environment.
			</p>
		</article>
	</div>

	<div class="glass-panel space-y-4">
		<h2 class="text-xl font-semibold">Choose your preferred path</h2>
		<div class="flex flex-wrap gap-3">
			<a href={salesMailHref} class="btn btn-primary">Email Sales</a>
			<a href={`${base}/resources`} class="btn btn-secondary">Open Sales Resources</a>
			<a href={`${base}/auth/login?intent=talk_to_sales&entry=talk_to_sales`} class="btn btn-secondary">
				Start Free Instead
			</a>
		</div>
		<p class="text-sm text-ink-400">
			Enterprise inquiries typically receive a response within one business day.
		</p>
	</div>
</section>
