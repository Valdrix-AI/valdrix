<!--
  LLM Usage Page - Premium SaaS Design
  
  Features:
  - Stats cards for LLM metrics
  - Usage by model breakdown
  - Recent API calls table
-->

<script lang="ts">
	import { PUBLIC_API_URL } from '$env/static/public';
	import { createSupabaseBrowserClient } from '$lib/supabase';

	let { data } = $props();

	const supabase = createSupabaseBrowserClient();

	let usage = $derived(data.usage || []);
	let summary = $derived(
		data.summary || {
			total_cost: 0,
			total_tokens: 0,
			by_model: {} as Record<string, { tokens: number; cost: number; calls: number }>
		}
	);
	let error = $derived(data.error || '');
	let loading = $derived(false); // Data is pre-fetched
</script>

<svelte:head>
	<title>LLM Usage | Valdrix</title>
</svelte:head>

<div class="space-y-8">
	<!-- Page Header -->
	<div>
		<h1 class="text-2xl font-bold mb-1">LLM Usage</h1>
		<p class="text-ink-400 text-sm">Track your AI model costs and token usage</p>
	</div>

	{#if !data.user}
		<div class="card text-center py-12">
			<p class="text-ink-400">
				Please <a href="/auth/login" class="text-accent-400 hover:underline">sign in</a> to view LLM usage.
			</p>
		</div>
	{:else if loading}
		<!-- Loading Skeletons -->
		<div class="grid gap-5 md:grid-cols-3">
			{#each [1, 2, 3] as i}
				<div class="card">
					<div class="skeleton h-4 w-20 mb-3"></div>
					<div class="skeleton h-8 w-32"></div>
				</div>
			{/each}
		</div>
	{:else if error}
		<div class="card border-danger-500/50 bg-danger-500/10">
			<p class="text-danger-400">{error}</p>
		</div>
	{:else}
		<!-- Stats Grid -->
		<div class="grid gap-5 md:grid-cols-3">
			<div class="card card-stat stagger-enter" style="animation-delay: 0ms;">
				<p class="text-sm text-ink-400 mb-1">Total LLM Cost</p>
				<p class="text-3xl font-bold" style="color: var(--color-accent-400);">
					${summary.total_cost.toFixed(4)}
				</p>
			</div>

			<div class="card card-stat stagger-enter" style="animation-delay: 50ms;">
				<p class="text-sm text-ink-400 mb-1">Total Tokens</p>
				<p class="text-3xl font-bold" style="color: var(--color-success-400);">
					{summary.total_tokens.toLocaleString()}
				</p>
			</div>

			<div class="card card-stat stagger-enter" style="animation-delay: 100ms;">
				<p class="text-sm text-ink-400 mb-1">API Calls</p>
				<p class="text-3xl font-bold" style="color: var(--color-warning-400);">
					{usage.length}
				</p>
			</div>
		</div>

		<!-- Usage by Model -->
		{#if Object.keys(summary.by_model).length > 0}
			<div class="card stagger-enter" style="animation-delay: 150ms;">
				<h2 class="text-lg font-semibold mb-5">Usage by Model</h2>
				<div class="overflow-x-auto">
					<table class="table">
						<thead>
							<tr>
								<th>Model</th>
								<th>Calls</th>
								<th>Tokens</th>
								<th>Cost</th>
							</tr>
						</thead>
						<tbody>
							{#each Object.entries(summary.by_model) as [model, stats]}
								<tr>
									<td>
										<span class="font-mono text-xs px-2 py-1 bg-ink-800 rounded">{model}</span>
									</td>
									<td>{stats.calls}</td>
									<td>{stats.tokens.toLocaleString()}</td>
									<td class="text-accent-400">${stats.cost.toFixed(4)}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}

		<!-- Recent Calls -->
		<div class="card stagger-enter" style="animation-delay: 200ms;">
			<div class="flex items-center justify-between mb-5">
				<h2 class="text-lg font-semibold">Recent API Calls</h2>
				<span class="badge badge-default">{usage.length} total</span>
			</div>

			{#if usage.length === 0}
				<div class="text-center py-12">
					<span class="text-4xl mb-3 block">🤖</span>
					<p class="text-ink-400">No LLM usage recorded yet.</p>
					<p class="text-ink-500 text-sm mt-1">Usage will appear here when you use AI features.</p>
				</div>
			{:else}
				<div class="overflow-x-auto">
					<table class="table">
						<thead>
							<tr>
								<th>Time</th>
								<th>Model</th>
								<th>Input</th>
								<th>Output</th>
								<th>Cost</th>
								<th>Type</th>
							</tr>
						</thead>
						<tbody>
							{#each usage.slice(0, 20) as record}
								<tr>
									<td class="text-ink-400 text-xs">
										{new Date(record.created_at).toLocaleString()}
									</td>
									<td>
										<span class="font-mono text-xs">{record.model}</span>
									</td>
									<td>{record.input_tokens?.toLocaleString() || 0}</td>
									<td>{record.output_tokens?.toLocaleString() || 0}</td>
									<td class="text-accent-400">${record.cost_usd?.toFixed(6) || 0}</td>
									<td>
										<span class="badge badge-default">{record.request_type || 'unknown'}</span>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.text-ink-400 {
		color: var(--color-ink-400);
	}
	.text-ink-500 {
		color: var(--color-ink-500);
	}
	.text-accent-400 {
		color: var(--color-accent-400);
	}
	.text-danger-400 {
		color: var(--color-danger-400);
	}
	.bg-ink-800 {
		background-color: var(--color-ink-800);
	}
	.bg-danger-500\/10 {
		background-color: rgb(244 63 94 / 0.1);
	}
	.border-danger-500\/50 {
		border-color: rgb(244 63 94 / 0.5);
	}
</style>
