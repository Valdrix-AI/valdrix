<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { PUBLIC_API_URL } from '$env/static/public';
	import { base } from '$app/paths';
	import { api } from '$lib/api';
	import {
		buildUnitEconomicsUrl,
		defaultDateWindow,
		formatDelta,
		hasInvalidUnitWindow,
		unitDeltaClass
	} from './unitEconomics';

	type PendingRequest = {
		id: string;
		resource_id: string;
		resource_type: string;
		action: string;
		estimated_savings: number;
		created_at: string | null;
	};

	type JobStatus = {
		pending: number;
		running: number;
		completed: number;
		failed: number;
		dead_letter: number;
	};

	type JobRecord = {
		id: string;
		job_type: string;
		status: string;
		attempts: number;
		created_at: string;
		error_message?: string;
	};

	type StrategyRecommendation = {
		id: string;
		resource_type: string;
		region: string;
		term: string;
		payment_option: string;
		estimated_monthly_savings: number;
		roi_percentage: number;
		status: string;
	};

	type UnitEconomicsMetric = {
		metric_key: string;
		label: string;
		denominator: number;
		total_cost: number;
		cost_per_unit: number;
		baseline_cost_per_unit: number;
		delta_percent: number;
		is_anomalous: boolean;
	};

	type UnitEconomicsResponse = {
		start_date: string;
		end_date: string;
		total_cost: number;
		baseline_total_cost: number;
		threshold_percent: number;
		anomaly_count: number;
		alert_dispatched: boolean;
		metrics: UnitEconomicsMetric[];
	};

	type UnitEconomicsSettings = {
		id: string;
		default_request_volume: number;
		default_workload_volume: number;
		default_customer_volume: number;
		anomaly_threshold_percent: number;
	};

	type IngestionSLAResponse = {
		window_hours: number;
		target_success_rate_percent: number;
		total_jobs: number;
		successful_jobs: number;
		failed_jobs: number;
		success_rate_percent: number;
		meets_sla: boolean;
		latest_completed_at: string | null;
		avg_duration_seconds: number | null;
		p95_duration_seconds: number | null;
		records_ingested: number;
	};

	const initialUnitWindow = defaultDateWindow(30);

	let { data } = $props();
	let loading = $state(true);
	let error = $state('');
	let success = $state('');
	let processingJobs = $state(false);
	let refreshingStrategies = $state(false);
	let refreshingUnitEconomics = $state(false);
	let refreshingIngestionSla = $state(false);
	let savingUnitSettings = $state(false);
	let actingId = $state<string | null>(null);

	let pendingRequests = $state<PendingRequest[]>([]);
	let jobStatus = $state<JobStatus | null>(null);
	let jobs = $state<JobRecord[]>([]);
	let recommendations = $state<StrategyRecommendation[]>([]);
	let unitStartDate = $state(initialUnitWindow.start);
	let unitEndDate = $state(initialUnitWindow.end);
	let unitAlertOnAnomaly = $state(true);
	let unitEconomics = $state<UnitEconomicsResponse | null>(null);
	let unitSettings = $state<UnitEconomicsSettings | null>(null);
	let ingestionSlaWindowHours = $state(24);
	let ingestionSla = $state<IngestionSLAResponse | null>(null);

	function getHeaders() {
		return {
			Authorization: `Bearer ${data.session?.access_token}`
		};
	}

	function formatDate(value: string | null): string {
		if (!value) return '-';
		return new Date(value).toLocaleString();
	}

	function formatUsd(value: number): string {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: 'USD',
			maximumFractionDigits: 2
		}).format(value || 0);
	}

	function formatNumber(value: number, fractionDigits = 2): string {
		return new Intl.NumberFormat('en-US', {
			maximumFractionDigits: fractionDigits
		}).format(value || 0);
	}

	function formatDuration(seconds: number | null): string {
		if (seconds === null || Number.isNaN(seconds)) return '-';
		if (seconds < 60) return `${Math.round(seconds)}s`;
		const minutes = Math.floor(seconds / 60);
		const remainder = Math.round(seconds % 60);
		if (minutes < 60) return `${minutes}m ${remainder}s`;
		const hours = Math.floor(minutes / 60);
		const mins = minutes % 60;
		return `${hours}h ${mins}m`;
	}

	function ingestionSlaBadgeClass(sla: IngestionSLAResponse): string {
		return sla.meets_sla ? 'badge badge-success' : 'badge badge-warning';
	}

	function buildIngestionSlaUrl(): string {
		const params = new URLSearchParams({
			window_hours: String(ingestionSlaWindowHours),
			target_success_rate_percent: '95'
		});
		return `${PUBLIC_API_URL}/costs/ingestion/sla?${params.toString()}`;
	}

	async function loadOpsData() {
		if (!data.user || !data.session?.access_token) {
			loading = false;
			return;
		}
		if (hasInvalidUnitWindow(unitStartDate, unitEndDate)) {
			error = 'Unit economics date range is invalid: start date must be on or before end date.';
			loading = false;
			return;
		}

		error = '';
		try {
			const headers = getHeaders();
			const [pendingRes, statusRes, jobsRes, recsRes, settingsRes, unitRes, ingestionSlaRes] =
				await Promise.all([
				api.get(`${PUBLIC_API_URL}/zombies/pending`, { headers }),
				api.get(`${PUBLIC_API_URL}/jobs/status`, { headers }),
				api.get(`${PUBLIC_API_URL}/jobs/list?limit=20`, { headers }),
				api.get(`${PUBLIC_API_URL}/strategies/recommendations?status=open`, { headers }),
				api.get(`${PUBLIC_API_URL}/costs/unit-economics/settings`, { headers }),
				api.get(buildUnitEconomicsUrl(PUBLIC_API_URL, unitStartDate, unitEndDate, unitAlertOnAnomaly), {
					headers
				}),
				api.get(buildIngestionSlaUrl(), { headers })
			]);

			pendingRequests = pendingRes.ok ? ((await pendingRes.json()).requests ?? []) : [];
			jobStatus = statusRes.ok ? await statusRes.json() : null;
			jobs = jobsRes.ok ? await jobsRes.json() : [];
			recommendations = recsRes.ok ? await recsRes.json() : [];
			unitSettings = settingsRes.ok ? await settingsRes.json() : null;
			unitEconomics = unitRes.ok ? await unitRes.json() : null;
			ingestionSla = ingestionSlaRes.ok ? await ingestionSlaRes.json() : null;
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to load operations data.';
		} finally {
			loading = false;
		}
	}

	async function refreshUnitEconomics() {
		if (!data.user || !data.session?.access_token) return;
		if (hasInvalidUnitWindow(unitStartDate, unitEndDate)) {
			error = 'Unit economics date range is invalid: start date must be on or before end date.';
			return;
		}

		refreshingUnitEconomics = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const [settingsRes, unitRes] = await Promise.all([
				api.get(`${PUBLIC_API_URL}/costs/unit-economics/settings`, { headers }),
				api.get(buildUnitEconomicsUrl(PUBLIC_API_URL, unitStartDate, unitEndDate, unitAlertOnAnomaly), {
					headers
				})
			]);

			if (!unitRes.ok) {
				const payload = await unitRes.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to load unit economics metrics.');
			}
			unitEconomics = await unitRes.json();

			if (settingsRes.ok) {
				unitSettings = await settingsRes.json();
			}
			success = 'Unit economics refreshed.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to refresh unit economics.';
		} finally {
			refreshingUnitEconomics = false;
		}
	}

	async function refreshIngestionSla() {
		if (!data.user || !data.session?.access_token) return;
		refreshingIngestionSla = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.get(buildIngestionSlaUrl(), { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to load ingestion SLA.');
			}
			ingestionSla = await res.json();
			success = 'Ingestion SLA refreshed.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to refresh ingestion SLA.';
		} finally {
			refreshingIngestionSla = false;
		}
	}

	async function saveUnitEconomicsSettings(event?: SubmitEvent) {
		event?.preventDefault();
		if (!unitSettings || !data.session?.access_token) return;

		savingUnitSettings = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const payload = {
				default_request_volume: Number(unitSettings.default_request_volume),
				default_workload_volume: Number(unitSettings.default_workload_volume),
				default_customer_volume: Number(unitSettings.default_customer_volume),
				anomaly_threshold_percent: Number(unitSettings.anomaly_threshold_percent)
			};
			const res = await api.put(`${PUBLIC_API_URL}/costs/unit-economics/settings`, payload, { headers });
			if (!res.ok) {
				const body = await res.json().catch(() => ({}));
				throw new Error(
					body.detail || body.message || 'Failed to save unit economics defaults. Admin role is required.'
				);
			}
			unitSettings = await res.json();
			success = 'Unit economics defaults saved.';
			await refreshUnitEconomics();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			savingUnitSettings = false;
		}
	}

	async function approveRequest(id: string) {
		actingId = id;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.post(
				`${PUBLIC_API_URL}/zombies/approve/${id}`,
				{ notes: 'Approved from Ops Center' },
				{ headers }
			);
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to approve request.');
			}
			success = `Request ${id.slice(0, 8)} approved.`;
			await loadOpsData();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			actingId = null;
		}
	}

	async function executeRequest(id: string) {
		actingId = id;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.post(`${PUBLIC_API_URL}/zombies/execute/${id}`, undefined, { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to execute request.');
			}
			success = `Request ${id.slice(0, 8)} execution started.`;
			await loadOpsData();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			actingId = null;
		}
	}

	async function processPendingJobs() {
		processingJobs = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.post(`${PUBLIC_API_URL}/jobs/process?limit=10`, undefined, { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to process jobs.');
			}
			const payload = await res.json();
			success = `Processed ${payload.processed} jobs (${payload.succeeded} succeeded, ${payload.failed} failed).`;
			await loadOpsData();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			processingJobs = false;
		}
	}

	async function refreshRecommendations() {
		refreshingStrategies = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.post(`${PUBLIC_API_URL}/strategies/refresh`, undefined, { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to refresh recommendations.');
			}
			const payload = await res.json();
			success = payload.message || 'Strategy refresh completed.';
			await loadOpsData();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			refreshingStrategies = false;
		}
	}

	async function applyRecommendation(id: string) {
		actingId = id;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.post(`${PUBLIC_API_URL}/strategies/apply/${id}`, undefined, {
				headers
			});
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to apply recommendation.');
			}
			success = `Recommendation ${id.slice(0, 8)} marked as applied.`;
			await loadOpsData();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			actingId = null;
		}
	}

	$effect(() => {
		void loadOpsData();
	});
</script>

<svelte:head>
	<title>Ops Center | Valdrix</title>
</svelte:head>

<div class="space-y-8">
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold mb-1">Ops Center</h1>
			<p class="text-ink-400 text-sm">
				Operate remediation approvals, background jobs, and strategy recommendations.
			</p>
		</div>
	</div>

	{#if !data.user}
		<div class="card text-center py-10">
			<p class="text-ink-400">
				Please <a href="{base}/auth/login" class="text-accent-400 hover:underline">sign in</a> to access
				operations.
			</p>
		</div>
	{:else if loading}
		<div class="card">
			<div class="skeleton h-6 w-64 mb-4"></div>
			<div class="skeleton h-4 w-full mb-2"></div>
			<div class="skeleton h-4 w-4/5"></div>
		</div>
	{:else}
		{#if error}
			<div class="card border-danger-500/50 bg-danger-500/10">
				<p class="text-danger-400">{error}</p>
			</div>
		{/if}
		{#if success}
			<div class="card border-success-500/50 bg-success-500/10">
				<p class="text-success-400">{success}</p>
			</div>
		{/if}

		<div class="grid gap-5 md:grid-cols-5">
			<div class="card card-stat">
				<p class="text-xs text-ink-400 uppercase tracking-wide">Pending Remediation</p>
				<p class="text-3xl font-bold text-warning-400">{pendingRequests.length}</p>
			</div>
			<div class="card card-stat">
				<p class="text-xs text-ink-400 uppercase tracking-wide">Jobs Pending</p>
				<p class="text-3xl font-bold text-accent-400">{jobStatus?.pending ?? 0}</p>
			</div>
			<div class="card card-stat">
				<p class="text-xs text-ink-400 uppercase tracking-wide">Jobs Running</p>
				<p class="text-3xl font-bold text-warning-400">{jobStatus?.running ?? 0}</p>
			</div>
			<div class="card card-stat">
				<p class="text-xs text-ink-400 uppercase tracking-wide">Jobs Failed</p>
				<p class="text-3xl font-bold text-danger-400">{jobStatus?.failed ?? 0}</p>
			</div>
			<div class="card card-stat">
				<p class="text-xs text-ink-400 uppercase tracking-wide">Open Strategies</p>
				<p class="text-3xl font-bold text-success-400">{recommendations.length}</p>
			</div>
		</div>

		<div class="card space-y-5">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<div>
					<h2 class="text-lg font-semibold">Unit Economics Monitor</h2>
					<p class="text-xs text-ink-400">
						Track cost-per-request/workload/customer versus a previous window baseline.
					</p>
				</div>
				<div class="flex items-end gap-2">
					<label class="text-xs text-ink-400">
						<span class="block mb-1">Start</span>
						<input class="input text-xs" type="date" bind:value={unitStartDate} />
					</label>
					<label class="text-xs text-ink-400">
						<span class="block mb-1">End</span>
						<input class="input text-xs" type="date" bind:value={unitEndDate} />
					</label>
					<label class="flex items-center gap-2 text-xs text-ink-400 mb-1">
						<input type="checkbox" bind:checked={unitAlertOnAnomaly} />
						Alert on anomaly
					</label>
					<button
						class="btn btn-secondary text-xs"
						disabled={refreshingUnitEconomics}
						onclick={refreshUnitEconomics}
					>
						{refreshingUnitEconomics ? 'Refreshing...' : 'Refresh Unit Metrics'}
					</button>
				</div>
			</div>

			{#if unitEconomics}
				<div class="grid gap-3 md:grid-cols-4">
					<div class="card card-stat">
						<p class="text-xs text-ink-400 uppercase tracking-wide">Current Window Cost</p>
						<p class="text-2xl font-bold text-ink-100">{formatUsd(unitEconomics.total_cost)}</p>
					</div>
					<div class="card card-stat">
						<p class="text-xs text-ink-400 uppercase tracking-wide">Baseline Cost</p>
						<p class="text-2xl font-bold text-ink-100">{formatUsd(unitEconomics.baseline_total_cost)}</p>
					</div>
					<div class="card card-stat">
						<p class="text-xs text-ink-400 uppercase tracking-wide">Threshold</p>
						<p class="text-2xl font-bold text-accent-400">{unitEconomics.threshold_percent.toFixed(2)}%</p>
					</div>
					<div class="card card-stat">
						<p class="text-xs text-ink-400 uppercase tracking-wide">Anomalies</p>
						<p
							class={`text-2xl font-bold ${unitEconomics.anomaly_count > 0 ? 'text-danger-400' : 'text-success-400'}`}
						>
							{unitEconomics.anomaly_count}
						</p>
					</div>
				</div>

				<div class="overflow-x-auto">
					<table class="table">
						<thead>
							<tr>
								<th>Metric</th>
								<th>Denominator</th>
								<th>Current Cost/Unit</th>
								<th>Baseline Cost/Unit</th>
								<th>Delta</th>
								<th>Status</th>
							</tr>
						</thead>
						<tbody>
							{#if unitEconomics.metrics.length === 0}
								<tr>
									<td colspan="6" class="text-ink-400 text-center py-4">
										No unit metrics available for this window.
									</td>
								</tr>
							{:else}
								{#each unitEconomics.metrics as metric (metric.metric_key)}
									<tr>
										<td class="text-sm">{metric.label}</td>
										<td>{formatNumber(metric.denominator, 2)}</td>
										<td>{formatUsd(metric.cost_per_unit)}</td>
										<td>{formatUsd(metric.baseline_cost_per_unit)}</td>
										<td class={unitDeltaClass(metric)}>{formatDelta(metric.delta_percent)}</td>
										<td class={metric.is_anomalous ? 'text-danger-400' : 'text-success-400'}>
											{metric.is_anomalous ? 'Anomalous' : 'Normal'}
										</td>
									</tr>
								{/each}
							{/if}
						</tbody>
					</table>
				</div>
			{:else}
				<p class="text-sm text-ink-400">
					Unit economics data is unavailable for the selected window. Try refreshing.
				</p>
			{/if}

			{#if unitSettings}
				<form class="space-y-3" onsubmit={saveUnitEconomicsSettings}>
					<h3 class="text-sm font-semibold text-ink-200">Default Unit Volumes</h3>
					<p class="text-xs text-ink-500">
						Admins can set baseline denominators used when query overrides are not provided.
					</p>
					<div class="grid gap-3 md:grid-cols-4">
						<label class="text-xs text-ink-400">
							<span class="block mb-1">Request Volume</span>
							<input
								class="input text-xs"
								type="number"
								min="0.0001"
								step="0.0001"
								bind:value={unitSettings.default_request_volume}
							/>
						</label>
						<label class="text-xs text-ink-400">
							<span class="block mb-1">Workload Volume</span>
							<input
								class="input text-xs"
								type="number"
								min="0.0001"
								step="0.0001"
								bind:value={unitSettings.default_workload_volume}
							/>
						</label>
						<label class="text-xs text-ink-400">
							<span class="block mb-1">Customer Volume</span>
							<input
								class="input text-xs"
								type="number"
								min="0.0001"
								step="0.0001"
								bind:value={unitSettings.default_customer_volume}
							/>
						</label>
						<label class="text-xs text-ink-400">
							<span class="block mb-1">Anomaly Threshold %</span>
							<input
								class="input text-xs"
								type="number"
								min="0.01"
								step="0.01"
								bind:value={unitSettings.anomaly_threshold_percent}
							/>
						</label>
					</div>
					<div class="flex justify-end">
						<button class="btn btn-primary text-xs" type="submit" disabled={savingUnitSettings}>
							{savingUnitSettings ? 'Saving...' : 'Save Defaults'}
						</button>
					</div>
				</form>
			{/if}
		</div>

		<div class="card space-y-4">
			<div class="flex flex-wrap items-center justify-between gap-3">
				<div>
					<h2 class="text-lg font-semibold">Cost Ingestion SLA</h2>
					<p class="text-xs text-ink-400">
						Track ingestion reliability and processing latency against a 95% success target.
					</p>
				</div>
				<div class="flex items-end gap-2">
					<label class="text-xs text-ink-400">
						<span class="block mb-1">Window</span>
						<select
							class="input text-xs"
							bind:value={ingestionSlaWindowHours}
							aria-label="SLA Window"
						>
							<option value={24}>Last 24h</option>
							<option value={72}>Last 72h</option>
							<option value={168}>Last 7d</option>
						</select>
					</label>
					<button
						class="btn btn-secondary text-xs"
						disabled={refreshingIngestionSla}
						onclick={refreshIngestionSla}
					>
						{refreshingIngestionSla ? 'Refreshing...' : 'Refresh SLA'}
					</button>
				</div>
			</div>

			{#if ingestionSla}
				<div class="flex items-center gap-2">
					<span class={ingestionSlaBadgeClass(ingestionSla)}>
						{ingestionSla.meets_sla ? 'SLA Healthy' : 'SLA At Risk'}
					</span>
					<span class="text-xs text-ink-500">
						{ingestionSla.success_rate_percent.toFixed(2)}% success ({ingestionSla.successful_jobs}/
						{ingestionSla.total_jobs} jobs)
					</span>
				</div>
				<div class="grid gap-3 md:grid-cols-5">
					<div class="card card-stat">
						<p class="text-xs text-ink-400 uppercase tracking-wide">Jobs (Window)</p>
						<p class="text-2xl font-bold text-ink-100">{ingestionSla.total_jobs}</p>
					</div>
					<div class="card card-stat">
						<p class="text-xs text-ink-400 uppercase tracking-wide">Failed Jobs</p>
						<p class="text-2xl font-bold text-danger-400">{ingestionSla.failed_jobs}</p>
					</div>
					<div class="card card-stat">
						<p class="text-xs text-ink-400 uppercase tracking-wide">Records Ingested</p>
						<p class="text-2xl font-bold text-accent-400">{formatNumber(ingestionSla.records_ingested, 0)}</p>
					</div>
					<div class="card card-stat">
						<p class="text-xs text-ink-400 uppercase tracking-wide">Avg Duration</p>
						<p class="text-2xl font-bold text-ink-100">{formatDuration(ingestionSla.avg_duration_seconds)}</p>
					</div>
					<div class="card card-stat">
						<p class="text-xs text-ink-400 uppercase tracking-wide">P95 Duration</p>
						<p class="text-2xl font-bold text-warning-400">
							{formatDuration(ingestionSla.p95_duration_seconds)}
						</p>
					</div>
				</div>
				<p class="text-xs text-ink-500">
					Latest completed ingestion: {formatDate(ingestionSla.latest_completed_at)}
				</p>
			{:else}
				<p class="text-sm text-ink-400">No ingestion SLA data is available for this window yet.</p>
			{/if}
		</div>

		<div class="card">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-lg font-semibold">Remediation Queue</h2>
			</div>
			{#if pendingRequests.length === 0}
				<p class="text-ink-400 text-sm">No pending remediation requests.</p>
			{:else}
				<div class="overflow-x-auto">
					<table class="table">
						<thead>
							<tr>
								<th>Request</th>
								<th>Resource</th>
								<th>Action</th>
								<th>Savings</th>
								<th>Created</th>
								<th>Controls</th>
							</tr>
						</thead>
						<tbody>
							{#each pendingRequests as req (req.id)}
								<tr>
									<td class="font-mono text-xs">{req.id.slice(0, 8)}...</td>
									<td>
										<div class="text-sm">{req.resource_type}</div>
										<div class="text-xs text-ink-500 font-mono">{req.resource_id}</div>
									</td>
									<td class="capitalize">{req.action.replaceAll('_', ' ')}</td>
									<td>{formatUsd(req.estimated_savings)}</td>
									<td class="text-xs text-ink-500">{formatDate(req.created_at)}</td>
									<td class="flex gap-2">
										<button
											class="btn btn-secondary text-xs"
											disabled={actingId === req.id}
											onclick={() => approveRequest(req.id)}
										>
											Approve
										</button>
										<button
											class="btn btn-primary text-xs"
											disabled={actingId === req.id}
											onclick={() => executeRequest(req.id)}
										>
											Execute
										</button>
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		</div>

		<div class="card">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-lg font-semibold">Background Jobs</h2>
				<div class="flex gap-2">
					<button class="btn btn-secondary text-xs" disabled={processingJobs} onclick={loadOpsData}>
						Refresh
					</button>
					<button
						class="btn btn-primary text-xs"
						disabled={processingJobs}
						onclick={processPendingJobs}
					>
						{processingJobs ? 'Processing...' : 'Process Pending'}
					</button>
				</div>
			</div>
			<div class="overflow-x-auto">
				<table class="table">
					<thead>
						<tr>
							<th>Type</th>
							<th>Status</th>
							<th>Attempts</th>
							<th>Created</th>
							<th>Error</th>
						</tr>
					</thead>
					<tbody>
						{#if jobs.length === 0}
							<tr>
								<td colspan="5" class="text-ink-400 text-center py-4">No jobs found.</td>
							</tr>
						{:else}
							{#each jobs as job (job.id)}
								<tr>
									<td class="font-mono text-xs">{job.job_type}</td>
									<td class="capitalize">{job.status}</td>
									<td>{job.attempts}</td>
									<td class="text-xs text-ink-500">{formatDate(job.created_at)}</td>
									<td class="text-xs text-danger-400">{job.error_message || '-'}</td>
								</tr>
							{/each}
						{/if}
					</tbody>
				</table>
			</div>
		</div>

		<div class="card">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-lg font-semibold">RI/SP Strategy Recommendations</h2>
				<div class="flex gap-2">
					<button class="btn btn-secondary text-xs" onclick={loadOpsData}>Refresh</button>
					<button
						class="btn btn-primary text-xs"
						disabled={refreshingStrategies}
						onclick={refreshRecommendations}
					>
						{refreshingStrategies ? 'Refreshing...' : 'Regenerate'}
					</button>
				</div>
			</div>
			<div class="overflow-x-auto">
				<table class="table">
					<thead>
						<tr>
							<th>Resource</th>
							<th>Region</th>
							<th>Term</th>
							<th>Payment</th>
							<th>Savings</th>
							<th>ROI</th>
							<th>Action</th>
						</tr>
					</thead>
					<tbody>
						{#if recommendations.length === 0}
							<tr>
								<td colspan="7" class="text-ink-400 text-center py-4">
									No open strategy recommendations.
								</td>
							</tr>
						{:else}
							{#each recommendations as rec (rec.id)}
								<tr>
									<td class="text-sm">{rec.resource_type}</td>
									<td class="text-sm">{rec.region}</td>
									<td class="text-sm">{rec.term}</td>
									<td class="text-sm">{rec.payment_option}</td>
									<td class="text-success-400 font-semibold">
										{formatUsd(rec.estimated_monthly_savings)}
									</td>
									<td>{rec.roi_percentage.toFixed(1)}%</td>
									<td>
										<button
											class="btn btn-secondary text-xs"
											disabled={actingId === rec.id}
											onclick={() => applyRecommendation(rec.id)}
										>
											Apply
										</button>
									</td>
								</tr>
							{/each}
						{/if}
					</tbody>
				</table>
			</div>
		</div>
	{/if}
</div>
