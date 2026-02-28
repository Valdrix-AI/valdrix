<script lang="ts">
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { api } from '$lib/api';
	import { edgeApiPath } from '$lib/edgeProxy';
	import { TimeoutError } from '$lib/fetchWithTimeout';

	const ENFORCEMENT_OPS_REQUEST_TIMEOUT_MS = 8000;

	let {
		accessToken,
		tier
	}: {
		accessToken?: string | null;
		tier?: string | null;
	} = $props();

	type ActiveReservation = {
		decision_id: string;
		source: string;
		environment: string;
		project_id: string;
		action: string;
		resource_reference: string;
		reason_codes: string[];
		reserved_allocation_usd: number | string;
		reserved_credit_usd: number | string;
		reserved_total_usd: number | string;
		created_at: string;
		age_seconds: number;
	};

	type DriftException = {
		decision_id: string;
		source: string;
		environment: string;
		project_id: string;
		action: string;
		resource_reference: string;
		expected_reserved_usd: number | string;
		actual_monthly_delta_usd: number | string;
		drift_usd: number | string;
		status: string;
		reconciled_at: string | null;
		notes: string | null;
	};

	function isProPlus(currentTier: string | null | undefined): boolean {
		return ['pro', 'enterprise'].includes((currentTier ?? '').toLowerCase());
	}

	function extractErrorMessage(data: unknown, fallback: string): string {
		if (!data || typeof data !== 'object') return fallback;
		const payload = data as Record<string, unknown>;
		if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail;
		if (typeof payload.message === 'string' && payload.message.trim()) return payload.message;
		return fallback;
	}

	function formatUsd(value: number | string): string {
		const amount = Number(value ?? 0);
		if (!Number.isFinite(amount)) return '$0.00';
		return `$${amount.toFixed(2)}`;
	}

	function formatAge(seconds: number): string {
		const total = Math.max(0, Number(seconds || 0));
		const hours = Math.floor(total / 3600);
		const minutes = Math.floor((total % 3600) / 60);
		if (hours > 0) return `${hours}h ${minutes}m`;
		return `${minutes}m`;
	}

	async function getHeaders() {
		return { Authorization: `Bearer ${accessToken}` };
	}

	let loading = $state(true);
	let refreshing = $state(false);
	let runningSweep = $state(false);
	let reconcilingDecisionId = $state<string | null>(null);
	let error = $state('');
	let success = $state('');
	let activeReservations = $state<ActiveReservation[]>([]);
	let driftExceptions = $state<DriftException[]>([]);

	async function loadActiveReservations() {
		const headers = await getHeaders();
		const response = await api.get(edgeApiPath('/enforcement/reservations/active'), {
			headers,
			timeoutMs: ENFORCEMENT_OPS_REQUEST_TIMEOUT_MS
		});
		if (response.status === 403 || response.status === 404) {
			activeReservations = [];
			return;
		}
		if (!response.ok) {
			const data = await response.json().catch(() => ({}));
			throw new Error(extractErrorMessage(data, 'Failed to load active reservations'));
		}
		activeReservations = ((await response.json()) as ActiveReservation[]) ?? [];
	}

	async function loadDriftExceptions() {
		const headers = await getHeaders();
		const response = await api.get(
			edgeApiPath('/enforcement/reservations/reconciliation-exceptions?limit=200'),
			{
				headers,
				timeoutMs: ENFORCEMENT_OPS_REQUEST_TIMEOUT_MS
			}
		);
		if (response.status === 403 || response.status === 404) {
			driftExceptions = [];
			return;
		}
		if (!response.ok) {
			const data = await response.json().catch(() => ({}));
			throw new Error(extractErrorMessage(data, 'Failed to load drift exceptions'));
		}
		driftExceptions = ((await response.json()) as DriftException[]) ?? [];
	}

	async function loadAll() {
		if (!accessToken || !isProPlus(tier)) {
			loading = false;
			return;
		}
		loading = true;
		error = '';
		success = '';
		try {
			await Promise.all([loadActiveReservations(), loadDriftExceptions()]);
		} catch (e) {
			if (e instanceof TimeoutError) {
				error = 'Enforcement ops request timed out. Please retry.';
			} else {
				const err = e as Error;
				error = err.message || 'Failed to load enforcement ops data';
			}
		} finally {
			loading = false;
		}
	}

	async function refreshData() {
		refreshing = true;
		await loadAll();
		refreshing = false;
	}

	async function runOverdueAutoReconciliation() {
		runningSweep = true;
		error = '';
		success = '';
		try {
			const headers = await getHeaders();
			const response = await api.post(
				edgeApiPath('/enforcement/reservations/reconcile-overdue'),
				{ limit: 200 },
				{ headers }
			);
			if (!response.ok) {
				const data = await response.json().catch(() => ({}));
				throw new Error(extractErrorMessage(data, 'Failed to run overdue reconciliation'));
			}
			const data = (await response.json().catch(() => ({}))) as {
				released_count?: number;
			};
			success = `Overdue reconciliation complete (${Number(data.released_count ?? 0)} released).`;
			await loadAll();
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to run overdue reconciliation';
		} finally {
			runningSweep = false;
		}
	}

	async function reconcileAsMatched(row: ActiveReservation) {
		reconcilingDecisionId = row.decision_id;
		error = '';
		success = '';
		try {
			const headers = await getHeaders();
			const response = await api.post(
				edgeApiPath(`/enforcement/reservations/${row.decision_id}/reconcile`),
				{
					actual_monthly_delta_usd: Number(row.reserved_total_usd ?? 0),
					notes: 'ops_matched_reconcile'
				},
				{ headers }
			);
			if (!response.ok) {
				const data = await response.json().catch(() => ({}));
				throw new Error(extractErrorMessage(data, 'Failed to reconcile reservation'));
			}
			success = `Reservation ${row.decision_id} reconciled.`;
			await loadAll();
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to reconcile reservation';
		} finally {
			reconcilingDecisionId = null;
		}
	}

	onMount(() => {
		void loadAll();
	});
</script>

<div
	class="card stagger-enter relative"
	class:opacity-60={!isProPlus(tier)}
	class:pointer-events-none={!isProPlus(tier)}
>
	<div class="flex items-center justify-between mb-3">
		<h2 class="text-lg font-semibold flex items-center gap-2">
			<span>🧭</span> Enforcement Ops Reconciliation
		</h2>
		{#if !isProPlus(tier)}
			<span class="badge badge-warning text-xs">Pro Plan Required</span>
		{/if}
	</div>

	{#if !isProPlus(tier)}
		<div class="absolute inset-0 z-10 flex items-center justify-center bg-transparent">
			<a href={`${base}/billing`} class="btn btn-primary shadow-lg pointer-events-auto">
				Upgrade to Unlock Enforcement Ops Views
			</a>
		</div>
	{/if}

	<p class="text-xs text-ink-400 mb-5">
		Monitor active reservations and reconciliation drift exceptions, then trigger overdue
		auto-reconciliation.
	</p>

	{#if error}
		<div role="alert" class="card border-danger-500/50 bg-danger-500/10 mb-4">
			<p class="text-danger-400 text-sm">{error}</p>
		</div>
	{/if}

	{#if success}
		<div role="status" class="card border-success-500/50 bg-success-500/10 mb-4">
			<p class="text-success-400 text-sm">{success}</p>
		</div>
	{/if}

	<div class="flex flex-wrap gap-3 items-center mb-4">
		<button
			type="button"
			class="btn btn-secondary"
			onclick={refreshData}
			disabled={refreshing || loading}
			aria-label="Refresh enforcement ops data"
		>
			{refreshing ? '⏳ Refreshing...' : 'Refresh'}
		</button>
		<button
			type="button"
			class="btn btn-primary"
			onclick={runOverdueAutoReconciliation}
			disabled={runningSweep || loading}
			aria-label="Run overdue auto-reconciliation"
		>
			{runningSweep ? '⏳ Running...' : 'Run Overdue Auto-Reconciliation'}
		</button>
		<span class="text-xs text-ink-500">
			Active: {activeReservations.length} • Drift exceptions: {driftExceptions.length}
		</span>
	</div>

	{#if loading}
		<div class="skeleton h-4 w-72"></div>
	{:else}
		<div class="space-y-6">
			<div class="pt-2 border-t border-ink-700">
				<h3 class="text-sm font-semibold mb-3">Active Reservations</h3>
				{#if activeReservations.length === 0}
					<p class="text-xs text-ink-500">No active reservations.</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead>
								<tr class="text-left text-ink-500">
									<th class="py-2">Decision</th>
									<th class="py-2">Resource</th>
									<th class="py-2">Age</th>
									<th class="py-2">Reserved</th>
									<th class="py-2">Action</th>
								</tr>
							</thead>
							<tbody>
								{#each activeReservations as row (row.decision_id)}
									<tr class="border-t border-ink-700">
										<td class="py-2 font-mono text-xs">{row.decision_id}</td>
										<td class="py-2">{row.resource_reference}</td>
										<td class="py-2">{formatAge(row.age_seconds)}</td>
										<td class="py-2">{formatUsd(row.reserved_total_usd)}</td>
										<td class="py-2">
											<button
												type="button"
												class="btn btn-xs btn-outline"
												onclick={() => reconcileAsMatched(row)}
												disabled={reconcilingDecisionId === row.decision_id}
												aria-label={`Reconcile as matched ${row.decision_id}`}
											>
												{reconcilingDecisionId === row.decision_id
													? '⏳ Reconciling...'
													: 'Reconcile as matched'}
											</button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>

			<div class="pt-2 border-t border-ink-700">
				<h3 class="text-sm font-semibold mb-3">Reconciliation Drift Exceptions</h3>
				{#if driftExceptions.length === 0}
					<p class="text-xs text-ink-500">No drift exceptions.</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead>
								<tr class="text-left text-ink-500">
									<th class="py-2">Decision</th>
									<th class="py-2">Resource</th>
									<th class="py-2">Status</th>
									<th class="py-2">Drift</th>
									<th class="py-2">Reconciled</th>
									<th class="py-2">Notes</th>
								</tr>
							</thead>
							<tbody>
								{#each driftExceptions as row (row.decision_id)}
									<tr class="border-t border-ink-700">
										<td class="py-2 font-mono text-xs">{row.decision_id}</td>
										<td class="py-2">{row.resource_reference}</td>
										<td class="py-2">{row.status}</td>
										<td class="py-2">{formatUsd(row.drift_usd)}</td>
										<td class="py-2">
											{row.reconciled_at ? new Date(row.reconciled_at).toLocaleString() : 'n/a'}
										</td>
										<td class="py-2">{row.notes ?? 'none'}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
