<script lang="ts">
	import { base } from '$app/paths';

	type ResourceEntry = {
		category: string;
		title: string;
		summary: string;
		href: string;
		ctaLabel: string;
	};

	const resources: readonly ResourceEntry[] = [
		{
			category: 'Playbook',
			title: 'Cloud Waste Review Checklist',
			summary:
				'Run a weekly 30-minute review that aligns finance and engineering on top waste risks and owners.',
			href: `${base}/docs`,
			ctaLabel: 'Open Resource'
		},
		{
			category: 'Guide',
			title: 'GreenOps Decision Framework',
			summary:
				'Balance cost, reliability, and carbon impact with decision rules that teams can execute safely.',
			href: `${base}/greenops`,
			ctaLabel: 'Open Resource'
		},
		{
			category: 'Template',
			title: 'SaaS and License Governance Starter Pack',
			summary:
				'Use role-based approval and owner-routing templates for software renewals and license optimization.',
			href: `${base}/docs/technical-validation`,
			ctaLabel: 'Open Resource'
		},
		{
			category: 'Collateral',
			title: 'Executive One-Pager (Download)',
			summary:
				'Share a concise procurement and rollout brief with finance, engineering, and leadership stakeholders.',
			href: `${base}/resources/valdrics-enterprise-one-pager.md`,
			ctaLabel: 'Download One-Pager'
		},
		{
			category: 'Template',
			title: 'ROI Assumptions Worksheet (CSV)',
			summary:
				'Model TCO assumptions and controllable spend opportunity before procurement and budget review.',
			href: `${base}/resources/valdrics-roi-assumptions.csv`,
			ctaLabel: 'Download Worksheet'
		}
	];
</script>

<svelte:head>
	<title>Resources | Valdrics</title>
	<meta
		name="description"
		content="Valdrics resources: practical playbooks, templates, and guides for cloud, SaaS, license, and GreenOps cost control."
	/>
</svelte:head>

<section class="container mx-auto px-6 py-12 space-y-8">
	<header class="space-y-3 max-w-3xl">
		<h1 class="text-3xl font-bold text-ink-100">Resources</h1>
		<p class="text-ink-300">
			Practical guidance for teams that want to reduce cloud and software waste without slowing
			delivery.
		</p>
	</header>

	<div class="grid gap-6 md:grid-cols-3">
		{#each resources as resource (resource.title)}
			<article class="glass-panel space-y-3">
				<p class="text-xs uppercase tracking-[0.12em] text-ink-500">{resource.category}</p>
				<h2 class="text-xl font-semibold">{resource.title}</h2>
				<p class="text-ink-300">{resource.summary}</p>
				<a href={resource.href} class="btn btn-secondary w-fit">{resource.ctaLabel}</a>
			</article>
		{/each}
	</div>

	<div class="glass-panel space-y-3">
		<h2 class="text-xl font-semibold">Need a guided walkthrough?</h2>
		<p class="text-ink-300">
			Start free and run your own ROI plan and remediation loop in a live workspace, or talk to
			sales for enterprise procurement support.
		</p>
		<div class="flex flex-wrap gap-3">
			<a
				href={`${base}/auth/login?intent=resource_signup&entry=resources`}
				class="btn btn-primary w-fit"
			>
				Start Free
			</a>
			<a href={`${base}/talk-to-sales?entry=resources&source=resource_hub`} class="btn btn-secondary w-fit">
				Talk to Sales
			</a>
			<a href={`${base}/insights`} class="btn btn-secondary w-fit">Open Insights</a>
		</div>
	</div>
</section>
