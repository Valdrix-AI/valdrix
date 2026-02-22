<script lang="ts">
	import { base } from '$app/paths';

	const apiGroups = [
		{
			name: 'Cost & Carbon',
			endpoints: ['/costs', '/carbon', '/costs/attribution/summary', '/costs/unit-economics']
		},
		{
			name: 'Optimization',
			endpoints: ['/zombies', '/zombies/policy-preview', '/zombies/request']
		},
		{
			name: 'Operations & Governance',
			endpoints: ['/jobs/stream', '/jobs/status', '/settings/profile', '/billing/subscription']
		}
	];
</script>

<svelte:head>
	<title>API Reference | Valdrix</title>
	<meta
		name="description"
		content="Valdrix API usage guide with edge proxy paths, authentication requirements, and endpoint groups."
	/>
</svelte:head>

<section class="container mx-auto px-6 py-12 space-y-8">
	<header class="space-y-3">
		<h1 class="text-3xl font-bold text-ink-100">API Reference</h1>
		<p class="text-ink-300 max-w-3xl">
			Frontend requests should go through the Valdrix edge proxy at
			<code class="badge badge-default">/api/edge</code>. Authenticated calls require a bearer
			token.
		</p>
	</header>

	<div class="glass-panel space-y-3">
		<h2 class="text-xl font-semibold">Example Request</h2>
		<pre
			class="overflow-x-auto rounded-lg border border-ink-700 bg-ink-900 p-4 text-sm text-ink-200"><code
				>{`GET ${base}/api/edge/costs?start_date=2026-02-01&end_date=2026-02-22
Authorization: Bearer <access_token>`}</code
			></pre>
		<p class="text-ink-400 text-sm">
			API base prefixes are preserved automatically by the edge proxy builder.
		</p>
	</div>

	<div class="grid gap-6 md:grid-cols-3">
		{#each apiGroups as group (group.name)}
			<article class="glass-panel space-y-3">
				<h2 class="text-lg font-semibold">{group.name}</h2>
				<ul class="space-y-2 text-sm text-ink-300">
					{#each group.endpoints as endpoint (endpoint)}
						<li>
							<code class="badge badge-default">{endpoint}</code>
						</li>
					{/each}
				</ul>
			</article>
		{/each}
	</div>

	<div class="flex flex-wrap gap-3">
		<a href={`${base}/docs`} class="btn btn-secondary">Back to Docs</a>
		<a href={`${base}/status`} class="btn btn-secondary">System Status</a>
	</div>
</section>
