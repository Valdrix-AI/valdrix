<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import AuthGate from '$lib/components/AuthGate.svelte';
	import { buildCompliancePackPath } from '$lib/compliancePack';
	import { edgeApiPath } from '$lib/edgeProxy';
	import { buildFocusExportPath } from '$lib/focusExport';
	import { filenameFromContentDispositionHeader } from '$lib/utils';

	type AuditLog = {
		id: string;
		event_type: string;
		event_timestamp: string;
		actor_email?: string | null;
		resource_type?: string | null;
		resource_id?: string | null;
		success: boolean;
		correlation_id?: string | null;
	};

	type AuditDetail = {
		id: string;
		event_type: string;
		event_timestamp: string;
		actor_email?: string | null;
		actor_ip?: string | null;
		request_method?: string | null;
		request_path?: string | null;
		resource_type?: string | null;
		resource_id?: string | null;
		success: boolean;
		error_message?: string | null;
		details?: Record<string, unknown> | null;
	};

	let { data } = $props();
	const AUDIT_REQUEST_TIMEOUT_MS = 8000;
	let loading = $state(true);
	let loadingDetail = $state(false);
	let exporting = $state(false);
	let exportingPack = $state(false);
	let exportingFocus = $state(false);
	let error = $state('');
	let success = $state('');

	let logs = $state<AuditLog[]>([]);
	let eventTypes = $state<string[]>([]);
	let selectedEventType = $state('');
	let limit = $state(50);
	let offset = $state(0);

	let selectedLogId = $state<string | null>(null);
	let selectedDetail = $state<AuditDetail | null>(null);

	let focusStartDate = $state(
		new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
	);
	let focusEndDate = $state(new Date().toISOString().slice(0, 10));
	let focusProvider = $state('');
	let focusIncludePreliminary = $state(false);
	let packIncludeFocus = $state(false);
	let packIncludeSavingsProof = $state(false);
	let packIncludeClosePackage = $state(false);
	let packCloseEnforceFinalized = $state(true);
	let packCloseMaxRestatements = $state(5000);

	const savingsProviderAllowed = ['aws', 'azure', 'gcp', 'saas', 'license'];

	function getHeaders() {
		return {
			Authorization: `Bearer ${data.session?.access_token}`
		};
	}

	async function getWithTimeout(url: string, headers: Record<string, string>) {
		return api.get(url, { headers, timeoutMs: AUDIT_REQUEST_TIMEOUT_MS });
	}

	function formatDate(value: string): string {
		return new Date(value).toLocaleString();
	}

	async function loadEventTypes() {
		const headers = getHeaders();
		const res = await getWithTimeout(edgeApiPath('/audit/event-types'), headers);
		if (res.ok) {
			const payload = await res.json();
			eventTypes = payload.event_types || [];
		}
	}

	async function loadLogs() {
		if (!data.user || !data.session?.access_token) {
			loading = false;
			return;
		}

		loading = true;
		error = '';
		try {
			const headers = getHeaders();
			const queryParts = [`limit=${limit}`, `offset=${offset}`, 'order=desc'];
			if (selectedEventType) {
				queryParts.push(`event_type=${encodeURIComponent(selectedEventType)}`);
			}

			const res = await getWithTimeout(edgeApiPath(`/audit/logs?${queryParts.join('&')}`), headers);
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to load audit logs.');
			}

			logs = await res.json();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			loading = false;
		}
	}

	async function viewDetail(id: string) {
		selectedLogId = id;
		selectedDetail = null;
		loadingDetail = true;
		error = '';
		try {
			const headers = getHeaders();
			const res = await getWithTimeout(edgeApiPath(`/audit/logs/${id}`), headers);
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to load audit log detail.');
			}
			selectedDetail = await res.json();
		} catch (e) {
			const err = e as Error;
			error = err.message;
			selectedLogId = null;
		} finally {
			loadingDetail = false;
		}
	}

	function closeDetail() {
		selectedLogId = null;
		selectedDetail = null;
	}

	async function exportCsv() {
		exporting = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const query = selectedEventType ? `event_type=${encodeURIComponent(selectedEventType)}` : '';

			const res = await getWithTimeout(edgeApiPath(`/audit/export?${query}`), headers);
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to export audit logs.');
			}

			const csv = await res.text();
			const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = `audit_logs_${new Date().toISOString().slice(0, 10)}.csv`;
			link.click();
			URL.revokeObjectURL(url);
			success = 'Audit log export downloaded.';
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			exporting = false;
		}
	}

	async function exportCompliancePack() {
		exportingPack = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const selectedSavingsProvider =
				focusProvider && savingsProviderAllowed.includes(focusProvider) ? focusProvider : undefined;
			const path = buildCompliancePackPath({
				includeFocusExport: packIncludeFocus,
				focusProvider: focusProvider || undefined,
				focusIncludePreliminary,
				focusMaxRows: 50000,
				focusStartDate,
				focusEndDate,
				includeSavingsProof: packIncludeSavingsProof,
				savingsProvider: selectedSavingsProvider,
				savingsStartDate: focusStartDate,
				savingsEndDate: focusEndDate,
				includeClosePackage: packIncludeClosePackage,
				closeProvider: focusProvider || undefined,
				closeStartDate: focusStartDate,
				closeEndDate: focusEndDate,
				closeEnforceFinalized: packCloseEnforceFinalized,
				closeMaxRestatements: packCloseMaxRestatements
			});

			const res = await getWithTimeout(edgeApiPath(path), headers);
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(
					payload.detail ||
						payload.message ||
						(res.status === 403
							? 'Owner role required to export compliance pack.'
							: 'Failed to export compliance pack.')
				);
			}

			const buffer = await res.arrayBuffer();
			const blob = new Blob([buffer], { type: 'application/zip' });
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = filenameFromContentDispositionHeader(
				res.headers.get('content-disposition'),
				`compliance-pack_${new Date().toISOString().slice(0, 10)}.zip`
			);
			link.click();
			URL.revokeObjectURL(url);
			success = 'Compliance pack downloaded.';
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			exportingPack = false;
		}
	}

	async function exportFocusCsv() {
		exportingFocus = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const path = buildFocusExportPath({
				startDate: focusStartDate,
				endDate: focusEndDate,
				provider: focusProvider,
				includePreliminary: focusIncludePreliminary
			});
			const res = await getWithTimeout(edgeApiPath(path), headers);
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(
					payload.detail ||
						payload.message ||
						(res.status === 403
							? 'Pro plan + admin role required to export FOCUS.'
							: 'Failed to export FOCUS CSV.')
				);
			}

			const csv = await res.text();
			const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
			const url = URL.createObjectURL(blob);
			const link = document.createElement('a');
			link.href = url;
			link.download = filenameFromContentDispositionHeader(
				res.headers.get('content-disposition'),
				`focus-v1.3-core_${focusStartDate}_${focusEndDate}.csv`
			);
			link.click();
			URL.revokeObjectURL(url);
			success = 'FOCUS export downloaded.';
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			exportingFocus = false;
		}
	}

	async function applyFilters() {
		offset = 0;
		await loadLogs();
	}

	async function previousPage() {
		offset = Math.max(0, offset - limit);
		await loadLogs();
	}

	async function nextPage() {
		offset = offset + limit;
		await loadLogs();
	}

	onMount(() => {
		void loadEventTypes();
		void loadLogs();
	});
</script>

<svelte:head>
	<title>Audit Logs | Valdrics</title>
</svelte:head>

<div class="space-y-8">
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold mb-1">Audit Logs</h1>
			<p class="text-ink-400 text-sm">
				Security and governance event trail for compliance workflows.
			</p>
		</div>
	</div>

	<AuthGate
		authenticated={!!data.user}
		action="access audit logs"
		className="card text-center py-10"
	>
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

		<div class="card">
			<div class="flex flex-wrap gap-3 items-end">
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-400 uppercase tracking-wide" for="event-type"
						>Event Type</label
					>
					<select id="event-type" bind:value={selectedEventType} class="select-input">
						<option value="">All events</option>
						{#each eventTypes as type (type)}
							<option value={type}>{type}</option>
						{/each}
					</select>
				</div>
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-400 uppercase tracking-wide" for="limit">Page Size</label>
					<select id="limit" bind:value={limit} class="select-input">
						<option value={20}>20</option>
						<option value={50}>50</option>
						<option value={100}>100</option>
					</select>
				</div>
				<div class="flex gap-2">
					<button class="btn btn-secondary text-xs" onclick={applyFilters}>Apply</button>
					<button class="btn btn-secondary text-xs" onclick={previousPage}> Prev </button>
					<button class="btn btn-secondary text-xs" onclick={nextPage}>Next</button>
					<button class="btn btn-primary text-xs" disabled={exporting} onclick={exportCsv}>
						{exporting ? 'Exporting...' : 'Export CSV'}
					</button>
					<button
						class="btn btn-primary text-xs"
						disabled={exportingPack}
						onclick={exportCompliancePack}
					>
						{exportingPack ? 'Exporting...' : 'Compliance Pack'}
					</button>
				</div>
			</div>
		</div>

		<div class="card">
			<h2 class="text-lg font-semibold mb-1">Compliance Exports</h2>
			<p class="text-ink-400 text-sm mb-4">
				Download FOCUS v1.3 core CSV (Pro+) or bundle exports into the Compliance Pack ZIP (Owner).
			</p>
			<div class="flex flex-wrap gap-3 items-end">
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-400 uppercase tracking-wide" for="focus-start">Start</label
					>
					<input id="focus-start" type="date" class="select-input" bind:value={focusStartDate} />
				</div>
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-400 uppercase tracking-wide" for="focus-end">End</label>
					<input id="focus-end" type="date" class="select-input" bind:value={focusEndDate} />
				</div>
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-400 uppercase tracking-wide" for="focus-provider"
						>Provider</label
					>
					<select id="focus-provider" bind:value={focusProvider} class="select-input">
						<option value="">All providers</option>
						<option value="aws">AWS</option>
						<option value="azure">Azure</option>
						<option value="gcp">GCP</option>
						<option value="saas">SaaS</option>
						<option value="license">License</option>
						<option value="platform">Platform</option>
						<option value="hybrid">Hybrid</option>
					</select>
				</div>
				<label class="flex items-center gap-2 text-xs text-ink-400">
					<input type="checkbox" class="accent-accent-500" bind:checked={focusIncludePreliminary} />
					<span>Include preliminary</span>
				</label>
				<button class="btn btn-primary text-xs" disabled={exportingFocus} onclick={exportFocusCsv}>
					{exportingFocus ? 'Exporting...' : 'FOCUS CSV'}
				</button>
			</div>

			<div class="mt-5 border-t border-ink-700/40 pt-4">
				<h3 class="text-sm font-semibold mb-2">Compliance Pack Add-ons</h3>
				<p class="text-ink-400 text-xs mb-3">
					Optional exports included inside the ZIP. Uses the same date/provider filters above.
				</p>
				<div class="flex flex-wrap gap-4 items-center">
					<label class="flex items-center gap-2 text-xs text-ink-300">
						<input type="checkbox" class="accent-accent-500" bind:checked={packIncludeFocus} />
						<span>Include FOCUS CSV</span>
					</label>
					<label class="flex items-center gap-2 text-xs text-ink-300">
						<input
							type="checkbox"
							class="accent-accent-500"
							bind:checked={packIncludeSavingsProof}
						/>
						<span>Include Savings Proof</span>
					</label>
					<label class="flex items-center gap-2 text-xs text-ink-300">
						<input
							type="checkbox"
							class="accent-accent-500"
							bind:checked={packIncludeClosePackage}
						/>
						<span>Include Close Package</span>
					</label>
					{#if packIncludeClosePackage}
						<label class="flex items-center gap-2 text-xs text-ink-300">
							<input
								type="checkbox"
								class="accent-accent-500"
								bind:checked={packCloseEnforceFinalized}
							/>
							<span>Enforce finalized</span>
						</label>
						<label class="flex items-center gap-2 text-xs text-ink-300">
							<span>Max restatements</span>
							<input
								type="number"
								min="0"
								max="200000"
								step="100"
								class="select-input w-28"
								bind:value={packCloseMaxRestatements}
							/>
						</label>
					{/if}
				</div>
			</div>
		</div>

		<div class="card">
			<h2 class="text-lg font-semibold mb-4">Events</h2>
			{#if loading}
				<div class="skeleton h-5 w-72 mb-2"></div>
				<div class="skeleton h-5 w-full mb-2"></div>
				<div class="skeleton h-5 w-full"></div>
			{:else}
				<div class="overflow-x-auto">
					<table class="table">
						<thead>
							<tr>
								<th>Timestamp</th>
								<th>Event</th>
								<th>Actor</th>
								<th>Resource</th>
								<th>Status</th>
								<th>Correlation</th>
								<th>Detail</th>
							</tr>
						</thead>
						<tbody>
							{#if logs.length === 0}
								<tr>
									<td colspan="7" class="text-ink-400 text-center py-4">No audit logs found.</td>
								</tr>
							{:else}
								{#each logs as log (log.id)}
									<tr>
										<td class="text-xs text-ink-500">{formatDate(log.event_timestamp)}</td>
										<td class="font-mono text-xs">{log.event_type}</td>
										<td>{log.actor_email || '-'}</td>
										<td>{log.resource_type || '-'} {log.resource_id || ''}</td>
										<td>
											<span class="badge {log.success ? 'badge-success' : 'badge-warning'}">
												{log.success ? 'SUCCESS' : 'FAILED'}
											</span>
										</td>
										<td class="text-xs font-mono">{log.correlation_id || '-'}</td>
										<td>
											<button class="btn btn-secondary text-xs" onclick={() => viewDetail(log.id)}>
												View
											</button>
										</td>
									</tr>
								{/each}
							{/if}
						</tbody>
					</table>
				</div>
			{/if}
		</div>
	</AuthGate>
</div>

{#if selectedLogId}
	<div class="fixed inset-0 z-[150] flex items-center justify-center p-4">
		<button
			type="button"
			class="absolute inset-0 bg-ink-950/70 backdrop-blur-sm border-0"
			aria-label="Close details"
			onclick={closeDetail}
		></button>
		<div
			class="relative w-full max-w-3xl max-h-[85vh] overflow-auto card border border-ink-700"
			role="dialog"
			aria-modal="true"
			aria-label="Audit log detail"
		>
			<div class="flex items-center justify-between mb-4">
				<h3 class="text-lg font-semibold">Audit Log Detail</h3>
				<button class="btn btn-secondary text-xs" onclick={closeDetail}>Close</button>
			</div>
			{#if loadingDetail}
				<div class="skeleton h-5 w-64 mb-2"></div>
				<div class="skeleton h-5 w-full mb-2"></div>
				<div class="skeleton h-5 w-full"></div>
			{:else if selectedDetail}
				<div class="space-y-3 text-sm">
					<div><strong>ID:</strong> <span class="font-mono text-xs">{selectedDetail.id}</span></div>
					<div><strong>Event:</strong> {selectedDetail.event_type}</div>
					<div><strong>Timestamp:</strong> {formatDate(selectedDetail.event_timestamp)}</div>
					<div><strong>Actor:</strong> {selectedDetail.actor_email || '-'}</div>
					<div><strong>IP:</strong> {selectedDetail.actor_ip || '-'}</div>
					<div>
						<strong>Request:</strong>
						{selectedDetail.request_method || '-'}
						{selectedDetail.request_path || '-'}
					</div>
					<div>
						<strong>Resource:</strong>
						{selectedDetail.resource_type || '-'}
						{selectedDetail.resource_id || ''}
					</div>
					<div><strong>Status:</strong> {selectedDetail.success ? 'SUCCESS' : 'FAILED'}</div>
					<div><strong>Error:</strong> {selectedDetail.error_message || '-'}</div>
					<div>
						<strong>Details JSON:</strong>
						<pre class="mt-2 p-3 rounded-lg bg-ink-900 text-xs overflow-auto">{JSON.stringify(
								selectedDetail.details || {},
								null,
								2
							)}</pre>
					</div>
				</div>
			{/if}
		</div>
	</div>
{/if}

<style>
	.select-input {
		min-width: 180px;
		border: 1px solid var(--color-ink-700);
		border-radius: 0.5rem;
		background: var(--color-ink-900);
		color: var(--color-ink-100);
		padding: 0.5rem 0.75rem;
	}
</style>
