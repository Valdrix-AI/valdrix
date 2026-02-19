<script lang="ts">
	import { Activity, RefreshCw, Server, Wallet, Cloud } from '@lucide/svelte';
	import AuthGate from '$lib/components/AuthGate.svelte';
	import { PUBLIC_API_URL } from '$env/static/public';
	import { TimeoutError, fetchWithTimeout } from '$lib/fetchWithTimeout';

	type HealthDashboard = {
		generated_at: string;
		system: {
			status: string;
			uptime_hours: number;
			last_check: string;
		};
		tenants: {
			total_tenants: number;
			active_last_24h: number;
			active_last_7d: number;
			free_tenants: number;
			paid_tenants: number;
			churn_risk: number;
		};
		job_queue: {
			pending_jobs: number;
			running_jobs: number;
			failed_last_24h: number;
			dead_letter_count: number;
			avg_processing_time_ms: number;
			p50_processing_time_ms: number;
			p95_processing_time_ms: number;
			p99_processing_time_ms: number;
		};
		llm_usage: {
			total_requests_24h: number;
			cache_hit_rate: number;
			estimated_cost_24h: number;
			budget_utilization: number;
		};
		aws_connections: {
			total_connections: number;
			verified_connections: number;
			failed_connections: number;
		};
	};

	type FairUseRuntime = {
		generated_at: string;
		guards_enabled: boolean;
		tenant_tier: string;
		tier_eligible: boolean;
		active_for_tenant: boolean;
		thresholds: {
			pro_daily_soft_cap: number | null;
			enterprise_daily_soft_cap: number | null;
			per_minute_cap: number | null;
			per_tenant_concurrency_cap: number | null;
			concurrency_lease_ttl_seconds: number;
			enforced_tiers: string[];
		};
	};

	let { data } = $props();
	const ADMIN_HEALTH_TIMEOUT_MS = 10000;
	let dashboard = $state<HealthDashboard | null>(null);
	let fairUse = $state<FairUseRuntime | null>(null);
	let fairUseError = $state('');
	let error = $state('');
	let forbidden = $state(false);
	let loading = $state(false);
	let refreshing = $state(false);
	let healthRequestId = 0;

	function extractApiError(payload: unknown): string | null {
		if (!payload || typeof payload !== 'object') return null;
		const maybe = payload as Record<string, unknown>;
		if (typeof maybe.detail === 'string' && maybe.detail.trim()) return maybe.detail;
		if (typeof maybe.message === 'string' && maybe.message.trim()) return maybe.message;
		if (typeof maybe.error === 'string' && maybe.error.trim()) return maybe.error;
		return null;
	}

	async function loadHealthDashboard(accessToken: string | undefined, hasUser: boolean) {
		const requestId = ++healthRequestId;

		if (!hasUser || !accessToken) {
			dashboard = null;
			fairUse = null;
			fairUseError = '';
			error = '';
			forbidden = false;
			loading = false;
			refreshing = false;
			return;
		}

		loading = true;
		error = '';
		fairUseError = '';

		try {
			const res = await fetchWithTimeout(
				fetch,
				`${PUBLIC_API_URL}/admin/health-dashboard`,
				{
					headers: {
						Authorization: `Bearer ${accessToken}`
					}
				},
				ADMIN_HEALTH_TIMEOUT_MS
			);

			if (requestId !== healthRequestId) return;

			if (res.status === 403) {
				dashboard = null;
				fairUse = null;
				fairUseError = '';
				forbidden = true;
				error = 'Admin role required to access system health metrics.';
				return;
			}

			if (res.status === 401) {
				dashboard = null;
				fairUse = null;
				fairUseError = '';
				forbidden = false;
				error = 'Session expired. Please sign in again.';
				return;
			}

			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				dashboard = null;
				fairUse = null;
				fairUseError = '';
				forbidden = false;
				error = extractApiError(payload) || `Failed to load health metrics (HTTP ${res.status}).`;
				return;
			}

			dashboard = (await res.json()) as HealthDashboard;
			forbidden = false;
			error = '';

			try {
				const fairUseRes = await fetchWithTimeout(
					fetch,
					`${PUBLIC_API_URL}/admin/health-dashboard/fair-use`,
					{
						headers: {
							Authorization: `Bearer ${accessToken}`
						}
					},
					ADMIN_HEALTH_TIMEOUT_MS
				);

				if (requestId !== healthRequestId) return;

				if (!fairUseRes.ok) {
					const payload = await fairUseRes.json().catch(() => ({}));
					fairUse = null;
					fairUseError =
						extractApiError(payload) ||
						`Fair-use runtime status unavailable (HTTP ${fairUseRes.status}).`;
					return;
				}

				fairUse = (await fairUseRes.json()) as FairUseRuntime;
				fairUseError = '';
			} catch (fairUseErr) {
				if (requestId !== healthRequestId) return;
				fairUse = null;
				fairUseError =
					fairUseErr instanceof TimeoutError
						? 'Fair-use runtime request timed out. Please try again.'
						: (fairUseErr as Error).message || 'Fair-use runtime status unavailable.';
			}
		} catch (err) {
			if (requestId !== healthRequestId) return;
			dashboard = null;
			fairUse = null;
			fairUseError = '';
			forbidden = false;
			error =
				err instanceof TimeoutError
					? 'Health metrics request timed out. Please try again.'
					: (err as Error).message || 'Failed to load health metrics.';
		} finally {
			if (requestId === healthRequestId) {
				loading = false;
				refreshing = false;
			}
		}
	}

	function formatDate(value: string): string {
		return new Date(value).toLocaleString();
	}

	function formatUsd(value: number): string {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: 'USD',
			maximumFractionDigits: 2
		}).format(value || 0);
	}

	function formatMs(value: number): string {
		return `${Math.round(value || 0).toLocaleString()} ms`;
	}

	function formatLimit(value: number | null | undefined): string {
		if (!value || value <= 0) return 'disabled';
		return value.toLocaleString();
	}

	function statusBadgeClass(status: string | undefined): string {
		switch ((status || '').toLowerCase()) {
			case 'healthy':
				return 'badge badge-success';
			case 'degraded':
				return 'badge badge-warning';
			case 'critical':
				return 'badge badge-error';
			default:
				return 'badge badge-default';
		}
	}

	async function refreshMetrics() {
		if (refreshing) return;
		refreshing = true;
		const accessToken = data.session?.access_token;
		const hasUser = !!data.user;
		await loadHealthDashboard(accessToken, hasUser);
	}

	$effect(() => {
		const accessToken = data.session?.access_token;
		const hasUser = !!data.user;
		void loadHealthDashboard(accessToken, hasUser);
	});
</script>

<svelte:head>
	<title>System Health | Valdrix</title>
</svelte:head>

<AuthGate authenticated={!!data.user} action="view system health metrics">
	{#if forbidden}
		<div class="card border-warning-500/50 bg-warning-500/10">
			<h2 class="text-lg font-semibold mb-2">Admin Access Required</h2>
			<p class="text-ink-300 text-sm">
				This dashboard is restricted to tenant admins and owners. Contact your workspace owner if
				you need access.
			</p>
		</div>
	{:else if loading}
		<div class="card">
			<div class="skeleton h-8 w-48 mb-3"></div>
			<div class="skeleton h-5 w-full mb-2"></div>
			<div class="skeleton h-5 w-4/5"></div>
		</div>
	{:else if error}
		<div class="card border-danger-500/50 bg-danger-500/10">
			<p class="text-danger-400">{error}</p>
		</div>
	{:else if !dashboard}
		<div class="card">
			<p class="text-ink-400">No health metrics available right now.</p>
		</div>
	{:else}
		<div class="space-y-8 page-enter">
			<div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
				<div>
					<h1 class="text-2xl font-bold mb-1">Investor Health Dashboard</h1>
					<p class="text-ink-400 text-sm">
						Operational metrics pulled from live governance telemetry.
					</p>
				</div>
				<div class="flex items-center gap-2">
					<span class={statusBadgeClass(dashboard.system.status)}>
						{dashboard.system.status.toUpperCase()}
					</span>
					<button class="btn btn-secondary text-xs" onclick={refreshMetrics} disabled={refreshing}>
						<RefreshCw class="h-3.5 w-3.5" />
						{refreshing ? 'Refreshing...' : 'Refresh'}
					</button>
				</div>
			</div>

			<div class="text-xs text-ink-500">
				Generated: {formatDate(dashboard.generated_at)} | Last check:
				{formatDate(dashboard.system.last_check)}
			</div>

			<div class="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
				<div class="card card-stat">
					<div class="flex items-center justify-between mb-2">
						<p class="text-xs text-ink-400 uppercase tracking-wide">System Uptime</p>
						<Activity class="h-4 w-4 text-ink-400" />
					</div>
					<p class="text-3xl font-bold">{dashboard.system.uptime_hours.toLocaleString()}h</p>
				</div>
				<div class="card card-stat">
					<div class="flex items-center justify-between mb-2">
						<p class="text-xs text-ink-400 uppercase tracking-wide">Jobs Running</p>
						<Server class="h-4 w-4 text-ink-400" />
					</div>
					<p class="text-3xl font-bold text-accent-400">{dashboard.job_queue.running_jobs}</p>
					<p class="text-xs text-danger-400 mt-1">
						{dashboard.job_queue.failed_last_24h} failed in last 24h
					</p>
				</div>
				<div class="card card-stat">
					<div class="flex items-center justify-between mb-2">
						<p class="text-xs text-ink-400 uppercase tracking-wide">LLM Cost (24h)</p>
						<Wallet class="h-4 w-4 text-ink-400" />
					</div>
					<p class="text-3xl font-bold text-warning-400">
						{formatUsd(dashboard.llm_usage.estimated_cost_24h)}
					</p>
					<p class="text-xs text-ink-500 mt-1">
						{dashboard.llm_usage.total_requests_24h.toLocaleString()} requests
					</p>
				</div>
				<div class="card card-stat">
					<div class="flex items-center justify-between mb-2">
						<p class="text-xs text-ink-400 uppercase tracking-wide">AWS Connections</p>
						<Cloud class="h-4 w-4 text-ink-400" />
					</div>
					<p class="text-3xl font-bold text-success-400">
						{dashboard.aws_connections.verified_connections}/{dashboard.aws_connections
							.total_connections}
					</p>
					<p class="text-xs text-ink-500 mt-1">
						{dashboard.aws_connections.failed_connections} failed
					</p>
				</div>
			</div>

			<div class="grid gap-5 lg:grid-cols-2">
				<div class="card space-y-4">
					<h2 class="text-lg font-semibold">Tenant Activity</h2>
					<div class="grid grid-cols-2 gap-3 text-sm">
						<div class="frosted-glass rounded-lg p-3">
							<p class="text-ink-400 text-xs uppercase">Total</p>
							<p class="text-xl font-bold">{dashboard.tenants.total_tenants}</p>
						</div>
						<div class="frosted-glass rounded-lg p-3">
							<p class="text-ink-400 text-xs uppercase">Paid</p>
							<p class="text-xl font-bold text-success-400">{dashboard.tenants.paid_tenants}</p>
						</div>
						<div class="frosted-glass rounded-lg p-3">
							<p class="text-ink-400 text-xs uppercase">Active 24h</p>
							<p class="text-xl font-bold">{dashboard.tenants.active_last_24h}</p>
						</div>
						<div class="frosted-glass rounded-lg p-3">
							<p class="text-ink-400 text-xs uppercase">Churn Risk</p>
							<p class="text-xl font-bold text-warning-400">{dashboard.tenants.churn_risk}</p>
						</div>
					</div>
				</div>

				<div class="card space-y-4">
					<h2 class="text-lg font-semibold">Job Queue Latency</h2>
					<div class="space-y-2 text-sm">
						<div class="flex items-center justify-between">
							<span class="text-ink-400">Pending jobs</span>
							<span>{dashboard.job_queue.pending_jobs}</span>
						</div>
						<div class="flex items-center justify-between">
							<span class="text-ink-400">Dead-letter queue</span>
							<span>{dashboard.job_queue.dead_letter_count}</span>
						</div>
						<div class="flex items-center justify-between">
							<span class="text-ink-400">Average</span>
							<span>{formatMs(dashboard.job_queue.avg_processing_time_ms)}</span>
						</div>
						<div class="flex items-center justify-between">
							<span class="text-ink-400">P50</span>
							<span>{formatMs(dashboard.job_queue.p50_processing_time_ms)}</span>
						</div>
						<div class="flex items-center justify-between">
							<span class="text-ink-400">P95</span>
							<span>{formatMs(dashboard.job_queue.p95_processing_time_ms)}</span>
						</div>
						<div class="flex items-center justify-between">
							<span class="text-ink-400">P99</span>
							<span>{formatMs(dashboard.job_queue.p99_processing_time_ms)}</span>
						</div>
					</div>
				</div>
			</div>

			<div class="card">
				<h2 class="text-lg font-semibold mb-3">LLM Budget Position</h2>
				<div class="space-y-2 text-sm">
					<div class="flex items-center justify-between">
						<span class="text-ink-400">Budget utilization</span>
						<span>{dashboard.llm_usage.budget_utilization.toFixed(2)}%</span>
					</div>
					<div class="w-full bg-ink-800 rounded-full h-2 overflow-hidden">
						<div
							class="h-full transition-all duration-500"
							class:bg-success-500={dashboard.llm_usage.budget_utilization < 70}
							class:bg-warning-500={dashboard.llm_usage.budget_utilization >= 70 &&
								dashboard.llm_usage.budget_utilization < 90}
							class:bg-danger-500={dashboard.llm_usage.budget_utilization >= 90}
							style="width: {Math.min(dashboard.llm_usage.budget_utilization, 100)}%"
						></div>
					</div>
					<div class="flex items-center justify-between">
						<span class="text-ink-400">Cache hit rate</span>
						<span>{(dashboard.llm_usage.cache_hit_rate * 100).toFixed(1)}%</span>
					</div>
				</div>
			</div>

			<div class="card">
				<h2 class="text-lg font-semibold mb-3">LLM Fair-Use Runtime</h2>
				{#if fairUse}
					<div class="space-y-2 text-sm">
						<div class="flex items-center justify-between">
							<span class="text-ink-400">Guardrails</span>
							<span class={statusBadgeClass(fairUse.guards_enabled ? 'healthy' : 'degraded')}>
								{fairUse.guards_enabled ? 'ON' : 'OFF'}
							</span>
						</div>
						<div class="flex items-center justify-between">
							<span class="text-ink-400">Tenant tier</span>
							<span>{fairUse.tenant_tier.toUpperCase()}</span>
						</div>
						<div class="flex items-center justify-between">
							<span class="text-ink-400">Enforced for this tenant</span>
							<span class={statusBadgeClass(fairUse.active_for_tenant ? 'healthy' : 'degraded')}>
								{fairUse.active_for_tenant ? 'YES' : 'NO'}
							</span>
						</div>
						<div class="pt-2 border-t border-ink-800">
							<p class="text-ink-500 text-xs uppercase mb-2 tracking-wide">Thresholds</p>
							<div class="space-y-2">
								<div class="flex items-center justify-between">
									<span class="text-ink-400">Pro daily soft cap</span>
									<span>{formatLimit(fairUse.thresholds.pro_daily_soft_cap)}</span>
								</div>
								<div class="flex items-center justify-between">
									<span class="text-ink-400">Enterprise daily soft cap</span>
									<span>{formatLimit(fairUse.thresholds.enterprise_daily_soft_cap)}</span>
								</div>
								<div class="flex items-center justify-between">
									<span class="text-ink-400">Per-minute cap</span>
									<span>{formatLimit(fairUse.thresholds.per_minute_cap)}</span>
								</div>
								<div class="flex items-center justify-between">
									<span class="text-ink-400">Per-tenant concurrency cap</span>
									<span>{formatLimit(fairUse.thresholds.per_tenant_concurrency_cap)}</span>
								</div>
								<div class="flex items-center justify-between">
									<span class="text-ink-400">Concurrency lease TTL</span>
									<span>{fairUse.thresholds.concurrency_lease_ttl_seconds}s</span>
								</div>
							</div>
						</div>
					</div>
				{:else if fairUseError}
					<p class="text-danger-400 text-sm">{fairUseError}</p>
				{:else}
					<p class="text-ink-400 text-sm">Fair-use runtime status is not available.</p>
				{/if}
			</div>
		</div>
	{/if}
</AuthGate>

<style>
	.border-warning-500\/50 {
		border-color: rgb(245 158 11 / 0.5);
	}

	.bg-warning-500\/10 {
		background-color: rgb(245 158 11 / 0.1);
	}
</style>
