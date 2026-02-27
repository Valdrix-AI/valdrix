<script lang="ts">
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { api } from '$lib/api';
	import { edgeApiPath } from '$lib/edgeProxy';
	import { TimeoutError } from '$lib/fetchWithTimeout';
	import { z } from 'zod';

	const ENFORCEMENT_REQUEST_TIMEOUT_MS = 8000;

	let {
		accessToken,
		tier
	}: {
		accessToken?: string | null;
		tier?: string | null;
	} = $props();

	type EnforcementPolicy = {
		terraform_mode: 'shadow' | 'soft' | 'hard';
		k8s_admission_mode: 'shadow' | 'soft' | 'hard';
		require_approval_for_prod: boolean;
		require_approval_for_nonprod: boolean;
		auto_approve_below_monthly_usd: number;
		hard_deny_above_monthly_usd: number;
		default_ttl_seconds: number;
		policy_version?: number;
		updated_at?: string;
	};

	type EnforcementBudget = {
		id: string;
		scope_key: string;
		monthly_limit_usd: number | string;
		active: boolean;
	};

	type EnforcementCredit = {
		id: string;
		scope_key: string;
		total_amount_usd: number | string;
		remaining_amount_usd: number | string;
		expires_at: string | null;
		reason: string | null;
		active: boolean;
	};

	const PolicySchema = z.object({
		terraform_mode: z.enum(['shadow', 'soft', 'hard']),
		k8s_admission_mode: z.enum(['shadow', 'soft', 'hard']),
		require_approval_for_prod: z.boolean(),
		require_approval_for_nonprod: z.boolean(),
		auto_approve_below_monthly_usd: z.number().min(0),
		hard_deny_above_monthly_usd: z.number().gt(0),
		default_ttl_seconds: z.number().int().min(60).max(86400)
	});

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

	async function getHeaders() {
		return { Authorization: `Bearer ${accessToken}` };
	}

	async function getWithTimeout(url: string, headers?: Record<string, string>) {
		return api.get(url, {
			...(headers ? { headers } : {}),
			timeoutMs: ENFORCEMENT_REQUEST_TIMEOUT_MS
		});
	}

	let loading = $state(true);
	let savingPolicy = $state(false);
	let savingBudget = $state(false);
	let savingCredit = $state(false);
	let error = $state('');
	let success = $state('');

	let policy = $state<EnforcementPolicy>({
		terraform_mode: 'soft',
		k8s_admission_mode: 'soft',
		require_approval_for_prod: true,
		require_approval_for_nonprod: false,
		auto_approve_below_monthly_usd: 25,
		hard_deny_above_monthly_usd: 5000,
		default_ttl_seconds: 900
	});
	let budgets = $state<EnforcementBudget[]>([]);
	let credits = $state<EnforcementCredit[]>([]);

	let budgetForm = $state({
		scope_key: 'default',
		monthly_limit_usd: 0,
		active: true
	});

	let creditForm = $state({
		scope_key: 'default',
		total_amount_usd: 0,
		expires_at: '',
		reason: ''
	});

	async function loadPolicy() {
		const headers = await getHeaders();
		const res = await getWithTimeout(edgeApiPath('/enforcement/policies'), headers);
		if (res.status === 403 || res.status === 404) return;
		if (!res.ok) {
			const data = await res.json().catch(() => ({}));
			throw new Error(extractErrorMessage(data, 'Failed to load enforcement policy'));
		}
		const loaded = (await res.json()) as EnforcementPolicy;
		policy = {
			...policy,
			...loaded,
			auto_approve_below_monthly_usd: Number(loaded.auto_approve_below_monthly_usd ?? 0),
			hard_deny_above_monthly_usd: Number(loaded.hard_deny_above_monthly_usd ?? 0),
			default_ttl_seconds: Number(loaded.default_ttl_seconds ?? 900)
		};
	}

	async function loadBudgets() {
		const headers = await getHeaders();
		const res = await getWithTimeout(edgeApiPath('/enforcement/budgets'), headers);
		if (res.status === 403 || res.status === 404) return;
		if (!res.ok) {
			const data = await res.json().catch(() => ({}));
			throw new Error(extractErrorMessage(data, 'Failed to load enforcement budgets'));
		}
		budgets = ((await res.json()) as EnforcementBudget[]) ?? [];
	}

	async function loadCredits() {
		const headers = await getHeaders();
		const res = await getWithTimeout(edgeApiPath('/enforcement/credits'), headers);
		if (res.status === 403 || res.status === 404) return;
		if (!res.ok) {
			const data = await res.json().catch(() => ({}));
			throw new Error(extractErrorMessage(data, 'Failed to load enforcement credits'));
		}
		credits = ((await res.json()) as EnforcementCredit[]) ?? [];
	}

	async function loadAll() {
		loading = true;
		error = '';
		success = '';
		try {
			if (!accessToken || !isProPlus(tier)) return;
			await Promise.all([loadPolicy(), loadBudgets(), loadCredits()]);
		} catch (e) {
			if (e instanceof TimeoutError) {
				error = 'Enforcement settings request timed out. Please retry.';
			} else {
				const err = e as Error;
				error = err.message || 'Failed to load enforcement settings';
			}
		} finally {
			loading = false;
		}
	}

	async function savePolicy() {
		savingPolicy = true;
		error = '';
		success = '';
		try {
			const validated = PolicySchema.parse(policy);
			const headers = await getHeaders();
			const res = await api.post(edgeApiPath('/enforcement/policies'), validated, { headers });
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				throw new Error(extractErrorMessage(data, 'Failed to save enforcement policy'));
			}
			await loadPolicy();
			success = 'Enforcement policy saved.';
		} catch (e) {
			if (e instanceof z.ZodError) {
				error = e.issues.map((issue) => issue.message).join(', ');
			} else {
				const err = e as Error;
				error = err.message || 'Failed to save enforcement policy';
			}
		} finally {
			savingPolicy = false;
		}
	}

	async function upsertBudget() {
		savingBudget = true;
		error = '';
		success = '';
		try {
			const payload = {
				scope_key: budgetForm.scope_key.trim() || 'default',
				monthly_limit_usd: Number(budgetForm.monthly_limit_usd),
				active: budgetForm.active
			};
			const headers = await getHeaders();
			const res = await api.post(edgeApiPath('/enforcement/budgets'), payload, { headers });
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				throw new Error(extractErrorMessage(data, 'Failed to save enforcement budget'));
			}
			await loadBudgets();
			success = 'Enforcement budget saved.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to save enforcement budget';
		} finally {
			savingBudget = false;
		}
	}

	async function createCredit() {
		savingCredit = true;
		error = '';
		success = '';
		try {
			const payload = {
				scope_key: creditForm.scope_key.trim() || 'default',
				total_amount_usd: Number(creditForm.total_amount_usd),
				expires_at: creditForm.expires_at ? new Date(creditForm.expires_at).toISOString() : null,
				reason: creditForm.reason.trim() || null
			};
			const headers = await getHeaders();
			const res = await api.post(edgeApiPath('/enforcement/credits'), payload, { headers });
			if (!res.ok) {
				const data = await res.json().catch(() => ({}));
				throw new Error(extractErrorMessage(data, 'Failed to create enforcement credit'));
			}
			creditForm = {
				scope_key: creditForm.scope_key,
				total_amount_usd: 0,
				expires_at: '',
				reason: ''
			};
			await loadCredits();
			success = 'Enforcement credit created.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to create enforcement credit';
		} finally {
			savingCredit = false;
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
			<span>🛡️</span> Enforcement Control Plane
		</h2>
		{#if !isProPlus(tier)}
			<span class="badge badge-warning text-xs">Pro Plan Required</span>
		{/if}
	</div>

	{#if !isProPlus(tier)}
		<div class="absolute inset-0 z-10 flex items-center justify-center bg-transparent">
			<a href={`${base}/billing`} class="btn btn-primary shadow-lg pointer-events-auto">
				Upgrade to Unlock Enforcement Controls
			</a>
		</div>
	{/if}

	<p class="text-xs text-ink-400 mb-5">
		Configure pre-provision gate policy, monthly budget envelopes, and temporary enforcement
		credits.
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

	{#if loading}
		<div class="skeleton h-4 w-64"></div>
	{:else}
		<div class="space-y-6">
			<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
				<div class="form-group">
					<label for="enforcement_terraform_mode">Terraform Gate Mode</label>
					<select
						id="enforcement_terraform_mode"
						class="select"
						bind:value={policy.terraform_mode}
						aria-label="Terraform gate mode"
					>
						<option value="shadow">shadow</option>
						<option value="soft">soft</option>
						<option value="hard">hard</option>
					</select>
				</div>
				<div class="form-group">
					<label for="enforcement_k8s_mode">K8s Admission Mode</label>
					<select
						id="enforcement_k8s_mode"
						class="select"
						bind:value={policy.k8s_admission_mode}
						aria-label="Kubernetes admission mode"
					>
						<option value="shadow">shadow</option>
						<option value="soft">soft</option>
						<option value="hard">hard</option>
					</select>
				</div>
			</div>

			<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
				<div class="form-group">
					<label for="enforcement_auto_approve_threshold">Auto-Approve Below (USD/month)</label>
					<input
						type="number"
						id="enforcement_auto_approve_threshold"
						min="0"
						step="0.01"
						bind:value={policy.auto_approve_below_monthly_usd}
						aria-label="Auto approve threshold per month"
					/>
				</div>
				<div class="form-group">
					<label for="enforcement_hard_deny_threshold">Hard-Deny Above (USD/month)</label>
					<input
						type="number"
						id="enforcement_hard_deny_threshold"
						min="0.01"
						step="0.01"
						bind:value={policy.hard_deny_above_monthly_usd}
						aria-label="Hard deny threshold per month"
					/>
				</div>
				<div class="form-group">
					<label for="enforcement_ttl_seconds">Approval TTL (seconds)</label>
					<input
						type="number"
						id="enforcement_ttl_seconds"
						min="60"
						max="86400"
						step="1"
						bind:value={policy.default_ttl_seconds}
						aria-label="Approval TTL in seconds"
					/>
				</div>
			</div>

			<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
				<label class="flex items-center gap-3 cursor-pointer">
					<input
						type="checkbox"
						class="toggle"
						bind:checked={policy.require_approval_for_prod}
						aria-label="Require approval for prod"
					/>
					<span>Require approval for prod</span>
				</label>
				<label class="flex items-center gap-3 cursor-pointer">
					<input
						type="checkbox"
						class="toggle"
						bind:checked={policy.require_approval_for_nonprod}
						aria-label="Require approval for nonprod"
					/>
					<span>Require approval for non-prod</span>
				</label>
			</div>

			<div class="flex flex-wrap gap-3 items-center">
				<button
					class="btn btn-primary"
					onclick={savePolicy}
					disabled={savingPolicy}
					aria-label="Save enforcement policy"
				>
					{savingPolicy ? '⏳ Saving...' : '💾 Save Enforcement Policy'}
				</button>
				{#if policy.policy_version}
					<span class="text-xs text-ink-500">
						Policy v{policy.policy_version}{policy.updated_at
							? ` • updated ${new Date(policy.updated_at).toLocaleString()}`
							: ''}
					</span>
				{/if}
			</div>

			<div class="pt-4 border-t border-ink-700">
				<h3 class="text-sm font-semibold mb-3">Budget Allocations</h3>
				<div class="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
					<div class="form-group">
						<label for="enforcement_budget_scope">Scope Key</label>
						<input
							id="enforcement_budget_scope"
							bind:value={budgetForm.scope_key}
							aria-label="Enforcement budget scope key"
						/>
					</div>
					<div class="form-group">
						<label for="enforcement_budget_limit">Monthly Limit (USD)</label>
						<input
							type="number"
							id="enforcement_budget_limit"
							min="0"
							step="0.01"
							bind:value={budgetForm.monthly_limit_usd}
							aria-label="Enforcement budget monthly limit"
						/>
					</div>
					<label class="flex items-center gap-3 cursor-pointer mt-7">
						<input
							type="checkbox"
							class="toggle"
							bind:checked={budgetForm.active}
							aria-label="Enforcement budget active"
						/>
						<span>Active</span>
					</label>
				</div>
				<button
					class="btn btn-secondary mb-3"
					onclick={upsertBudget}
					disabled={savingBudget}
					aria-label="Save enforcement budget"
				>
					{savingBudget ? '⏳ Saving...' : 'Save Budget'}
				</button>

				{#if budgets.length === 0}
					<p class="text-xs text-ink-500">No budgets configured yet.</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead>
								<tr class="text-left text-ink-500">
									<th class="py-2">Scope</th>
									<th class="py-2">Monthly Limit</th>
									<th class="py-2">Active</th>
								</tr>
							</thead>
							<tbody>
								{#each budgets as row (row.id)}
									<tr class="border-t border-ink-700">
										<td class="py-2">{row.scope_key}</td>
										<td class="py-2">${Number(row.monthly_limit_usd).toFixed(2)}</td>
										<td class="py-2">{row.active ? 'yes' : 'no'}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>

			<div class="pt-4 border-t border-ink-700">
				<h3 class="text-sm font-semibold mb-3">Credits</h3>
				<div class="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
					<div class="form-group">
						<label for="enforcement_credit_scope">Scope Key</label>
						<input
							id="enforcement_credit_scope"
							bind:value={creditForm.scope_key}
							aria-label="Enforcement credit scope key"
						/>
					</div>
					<div class="form-group">
						<label for="enforcement_credit_total">Credit Amount (USD)</label>
						<input
							type="number"
							id="enforcement_credit_total"
							min="0.01"
							step="0.01"
							bind:value={creditForm.total_amount_usd}
							aria-label="Enforcement credit total amount"
						/>
					</div>
					<div class="form-group">
						<label for="enforcement_credit_expiry">Expiry (optional)</label>
						<input
							type="datetime-local"
							id="enforcement_credit_expiry"
							bind:value={creditForm.expires_at}
							aria-label="Enforcement credit expiry"
						/>
					</div>
					<div class="form-group">
						<label for="enforcement_credit_reason">Reason (optional)</label>
						<input
							id="enforcement_credit_reason"
							bind:value={creditForm.reason}
							aria-label="Enforcement credit reason"
						/>
					</div>
				</div>
				<button
					class="btn btn-secondary mb-3"
					onclick={createCredit}
					disabled={savingCredit}
					aria-label="Create enforcement credit"
				>
					{savingCredit ? '⏳ Saving...' : 'Create Credit'}
				</button>

				{#if credits.length === 0}
					<p class="text-xs text-ink-500">No credits available.</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead>
								<tr class="text-left text-ink-500">
									<th class="py-2">Scope</th>
									<th class="py-2">Remaining</th>
									<th class="py-2">Expires</th>
								</tr>
							</thead>
							<tbody>
								{#each credits as row (row.id)}
									<tr class="border-t border-ink-700">
										<td class="py-2">{row.scope_key}</td>
										<td class="py-2">${Number(row.remaining_amount_usd).toFixed(2)}</td>
										<td class="py-2">
											{row.expires_at ? new Date(row.expires_at).toLocaleString() : 'none'}
										</td>
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
