<script lang="ts">
	import { base } from '$app/paths';

	const salesMailHref =
		'mailto:enterprise@valdrics.com?cc=sales@valdrics.com&subject=Valdrics%20Enterprise%20Briefing&body=Team%20size%3A%0ACloud%2FSaaS%20scope%3A%0ATarget%20timeline%3A';
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
			Whether you're starting on Starter, Growth, or Pro, or running a formal enterprise review, we
			help you choose the right rollout path with clear security, governance, and pricing expectations.
		</p>
	</header>

	<div class="grid gap-6 md:grid-cols-3">
		<article class="glass-panel space-y-2">
			<p class="text-xs uppercase tracking-[0.12em] text-ink-500">Self-Serve Path</p>
			<h2 class="text-xl font-semibold">Starter/Growth/Pro onboarding and rollout</h2>
			<p class="text-ink-300">
				Align first sources, owner routing, and action workflows so smaller teams can launch quickly
				and expand controls over time.
			</p>
		</article>
		<article class="glass-panel space-y-2">
			<p class="text-xs uppercase tracking-[0.12em] text-ink-500">Security and Controls</p>
			<h2 class="text-xl font-semibold">Security and governance review</h2>
			<p class="text-ink-300">
				Walk through SSO, SCIM, role-based approvals, retention controls, and evidence requirements
				with your security and platform stakeholders.
			</p>
		</article>
		<article class="glass-panel space-y-2">
			<p class="text-xs uppercase tracking-[0.12em] text-ink-500">Commercial Diligence</p>
			<h2 class="text-xl font-semibold">Commercial and procurement diligence</h2>
			<p class="text-ink-300">
				Review tier fit, rollout effort, and due-diligence artifacts so finance, legal, and
				procurement teams can move with confidence.
			</p>
		</article>
	</div>

	<div class="glass-panel space-y-4">
		<h2 class="text-xl font-semibold">Choose your preferred path</h2>
		<div class="flex flex-wrap gap-3">
			<a href={salesMailHref} class="btn btn-primary">Email Sales</a>
			<a href={`${base}/resources`} class="btn btn-secondary">Open Sales Resources</a>
			<a
				href={`${base}/auth/login?intent=talk_to_sales&entry=talk_to_sales`}
				class="btn btn-secondary"
			>
				Start Free Instead
			</a>
		</div>
		<p class="text-sm text-ink-400">
			Most inquiries receive a response within one business day.
		</p>
	</div>
</section>
