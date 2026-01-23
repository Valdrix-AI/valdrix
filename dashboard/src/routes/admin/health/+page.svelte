<script lang="ts">
	import { onMount } from 'svelte';
	import { BarChart, Activity, ShieldAlert, Server } from '@lucide/svelte';

	let healthMetrics = {
		uptime: '99.98%',
		active_jobs: 0,
		failed_jobs: 0,
		llm_latency: '1.2s',
		db_connections: 0
	};

	let loading = $state(true);

	onMount(async () => {
		// In a real implementation, this would fetch from /api/v1/health-dashboard
		setTimeout(() => {
			healthMetrics = {
				uptime: '99.95%',
				active_jobs: 12,
				failed_jobs: 2,
				llm_latency: '1.4s',
				db_connections: 8
			};
			loading = false;
		}, 500);
	});
</script>

<div class="p-8 space-y-6 page-enter">
	<div class="flex items-center justify-between">
		<h1 class="text-3xl font-bold tracking-tight">Investor Health Dashboard</h1>
		<button class="btn btn-secondary">
			<Activity class="mr-2 h-4 w-4" />
			Refresh Metrics
		</button>
	</div>

	<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
		<div class="card card-stat">
			<div class="flex flex-row items-center justify-between space-y-0 pb-2">
				<h3 class="text-sm font-medium">System Uptime</h3>
				<Activity class="h-4 w-4 text-ink-400" />
			</div>
			<div>
				<div class="text-2xl font-bold">{healthMetrics.uptime}</div>
				<p class="text-xs text-ink-500">+0.01% from yesterday</p>
			</div>
		</div>

		<div class="card card-stat">
			<div class="flex flex-row items-center justify-between space-y-0 pb-2">
				<h3 class="text-sm font-medium">Background Jobs</h3>
				<Server class="h-4 w-4 text-ink-400" />
			</div>
			<div>
				<div class="text-2xl font-bold">{healthMetrics.active_jobs}</div>
				<p class="text-xs text-danger-400">{healthMetrics.failed_jobs} failed in last 24h</p>
			</div>
		</div>

		<div class="card card-stat">
			<div class="flex flex-row items-center justify-between space-y-0 pb-2">
				<h3 class="text-sm font-medium">LLM Performance</h3>
				<ShieldAlert class="h-4 w-4 text-ink-400" />
			</div>
			<div>
				<div class="text-2xl font-bold">{healthMetrics.llm_latency}</div>
				<p class="text-xs text-ink-500">p95 avg latency</p>
			</div>
		</div>

		<div class="card card-stat">
			<div class="flex flex-row items-center justify-between space-y-0 pb-2">
				<h3 class="text-sm font-medium">Active DB Connections</h3>
				<BarChart class="h-4 w-4 text-ink-400" />
			</div>
			<div>
				<div class="text-2xl font-bold">{healthMetrics.db_connections}</div>
				<p class="text-xs text-ink-500">out of 20 pool max</p>
			</div>
		</div>
	</div>

	<div class="card mt-8">
		<div class="mb-4">
			<h2 class="text-lg font-bold">System Logs & Anomalies</h2>
		</div>
		<div class="rounded-md border border-ink-800 p-4 font-mono text-sm">
			<div class="text-accent-400">
				[INFO] 2026-01-16 10:45:00 - Job#7782 started: finops_analysis for tenant_123
			</div>
			<div class="text-success-400">
				[SUCCESS] 2026-01-16 10:44:55 - Webhook retry successful: Paystack#REF_9982
			</div>
			<div class="text-danger-400">
				[ERROR] 2026-01-16 10:44:00 - Groq API Rate Limit Hit (Fallback to Gemini initialized)
			</div>
			<div class="text-warning-400">
				[WARN] 2026-01-16 10:43:55 - Delta Analysis skipped: No previous cache found for tenant_445
			</div>
		</div>
	</div>
</div>
