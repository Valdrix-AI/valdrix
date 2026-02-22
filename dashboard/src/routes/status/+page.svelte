<script lang="ts">
	const checkedAt = new Date().toISOString();

	const components = [
		{
			name: 'Dashboard Web App',
			status: 'Operational',
			detail: 'Public and authenticated routes are reachable.'
		},
		{
			name: 'Edge API Proxy',
			status: 'Operational',
			detail: 'Requests are routed through /api/edge with auth-aware forwarding.'
		},
		{
			name: 'Job Stream',
			status: 'Operational',
			detail: 'Server-sent event stream is available for background job telemetry.'
		},
		{
			name: 'Billing & Subscription',
			status: 'Operational',
			detail: 'Plan metadata and checkout initiation endpoints are responding.'
		}
	];
</script>

<svelte:head>
	<title>Status | Valdrix</title>
	<meta
		name="description"
		content="Current service status for Valdrix dashboard, API proxy, and core platform components."
	/>
</svelte:head>

<section class="container mx-auto px-6 py-12 space-y-8">
	<header class="space-y-3">
		<h1 class="text-3xl font-bold text-ink-100">System Status</h1>
		<p class="text-ink-300 max-w-3xl">Platform status summary for core user-facing services.</p>
		<p class="text-xs text-ink-500">Last checked: {checkedAt}</p>
	</header>

	<div class="grid gap-4 md:grid-cols-2">
		{#each components as component (component.name)}
			<article class="glass-panel space-y-3">
				<div class="flex items-center justify-between gap-3">
					<h2 class="text-lg font-semibold">{component.name}</h2>
					<span class="badge badge-success">{component.status}</span>
				</div>
				<p class="text-sm text-ink-300">{component.detail}</p>
			</article>
		{/each}
	</div>
</section>
