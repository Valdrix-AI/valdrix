<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { PUBLIC_API_URL } from '$env/static/public';
	import { base } from '$app/paths';
	import { api } from '$lib/api';

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
	let loading = $state(true);
	let loadingDetail = $state(false);
	let exporting = $state(false);
	let error = $state('');
	let success = $state('');

	let logs = $state<AuditLog[]>([]);
	let eventTypes = $state<string[]>([]);
	let selectedEventType = $state('');
	let limit = $state(50);
	let offset = $state(0);

	let selectedLogId = $state<string | null>(null);
	let selectedDetail = $state<AuditDetail | null>(null);

	function getHeaders() {
		return {
			Authorization: `Bearer ${data.session?.access_token}`
		};
	}

	function formatDate(value: string): string {
		return new Date(value).toLocaleString();
	}

	async function loadEventTypes() {
		const headers = getHeaders();
		const res = await api.get(`${PUBLIC_API_URL}/audit/event-types`, { headers });
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

			const res = await api.get(`${PUBLIC_API_URL}/audit/logs?${queryParts.join('&')}`, {
				headers
			});
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
			const res = await api.get(`${PUBLIC_API_URL}/audit/logs/${id}`, { headers });
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

			const res = await api.get(`${PUBLIC_API_URL}/audit/export?${query}`, { headers });
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

	$effect(() => {
		void loadEventTypes();
		void loadLogs();
	});
</script>

<svelte:head>
	<title>Audit Logs | Valdrix</title>
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

	{#if !data.user}
		<div class="card text-center py-10">
			<p class="text-ink-400">
				Please <a href="{base}/auth/login" class="text-accent-400 hover:underline">sign in</a> to access
				audit logs.
			</p>
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
					<button class="btn btn-secondary text-xs" onclick={loadLogs}>Apply</button>
					<button
						class="btn btn-secondary text-xs"
						onclick={() => (offset = Math.max(0, offset - limit))}
					>
						Prev
					</button>
					<button class="btn btn-secondary text-xs" onclick={() => (offset = offset + limit)}
						>Next</button
					>
					<button class="btn btn-primary text-xs" disabled={exporting} onclick={exportCsv}>
						{exporting ? 'Exporting...' : 'Export CSV'}
					</button>
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
	{/if}
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
