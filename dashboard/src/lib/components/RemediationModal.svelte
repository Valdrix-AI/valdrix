<script lang="ts">
	import { AlertTriangle, Clock } from '@lucide/svelte';
	import { api } from '$lib/api';
	import { PUBLIC_API_URL } from '$env/static/public';

	type RemediationFinding = {
		resource_id: string;
		resource_type?: string;
		provider?: string;
		connection_id?: string;
		monthly_cost?: string | number;
		recommended_action?: string;
	};

	type RemediationPreview = {
		decision: string;
		summary: string;
		tier: string;
		rule_hits: Array<{ rule_id: string; message?: string }>;
	};

	let { 
		isOpen = $bindable(false), 
		finding, 
		accessToken,
		onClose
	} = $props<{
		isOpen: boolean;
		finding: RemediationFinding | null;
		accessToken: string | undefined;
		onClose: () => void;
	}>();

	let previewLoading = $state(false);
	let submitting = $state(false);
	let previewError = $state('');
	let actionError = $state('');
	let actionSuccess = $state('');
	let preview = $state<RemediationPreview | null>(null);

	$effect(() => {
		if (isOpen && finding && !preview && !previewLoading) {
			runPreview();
		}
	});

	function deriveRemediationAction(finding: RemediationFinding): string {
		const suggested = finding.recommended_action?.toLowerCase() ?? '';
		const resourceType = finding.resource_type?.toLowerCase() ?? '';

		if (suggested.includes('delete')) {
			if (resourceType.includes('snapshot')) return 'delete_snapshot';
			if (resourceType.includes('ecr')) return 'delete_ecr_image';
			if (resourceType.includes('sagemaker')) return 'delete_sagemaker_endpoint';
			if (resourceType.includes('redshift')) return 'delete_redshift_cluster';
			if (resourceType.includes('nat')) return 'delete_nat_gateway';
			if (resourceType.includes('load balancer')) return 'delete_load_balancer';
			if (resourceType.includes('s3')) return 'delete_s3_bucket';
			if (resourceType.includes('rds')) return 'delete_rds_instance';
			return 'delete_volume';
		}

		if (resourceType.includes('elastic ip') || resourceType.includes('eip')) {
			return 'release_elastic_ip';
		}
		if (resourceType.includes('rds')) {
			return 'stop_rds_instance';
		}
		return 'stop_instance';
	}

	function parseMonthlyCost(value: string | number | undefined): number {
		if (typeof value === 'number') return value;
		return Number.parseFloat(String(value ?? '0').replace(/[^0-9.-]/g, '')) || 0;
	}

	function policyDecisionClass(decision: string | undefined): string {
		switch ((decision || '').toLowerCase()) {
			case 'allow':
				return 'badge badge-success';
			case 'warn':
				return 'badge badge-warning';
			case 'escalate':
				return 'badge badge-default';
			case 'block':
				return 'badge badge-error';
			default:
				return 'badge badge-default';
		}
	}

	async function runPreview() {
		if (!accessToken || !finding) {
			previewError = 'Not authenticated.';
			return;
		}

		previewLoading = true;
		previewError = '';
		actionError = '';
		actionSuccess = '';

		try {
			const headers = {
				Authorization: `Bearer ${accessToken}`,
				'Content-Type': 'application/json'
			};
			const action = deriveRemediationAction(finding);
			const previewResponse = await api.post(
				`${PUBLIC_API_URL}/zombies/policy-preview`,
				{
					resource_id: finding.resource_id,
					resource_type: finding.resource_type || 'unknown',
					provider: finding.provider || 'aws',
					action
				},
				{ headers }
			);

			if (!previewResponse.ok) {
				const payload = await previewResponse.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Policy preview failed.');
			}

			preview = await previewResponse.json();
		} catch (e) {
			const err = e as Error;
			preview = null;
			previewError = err.message || 'Policy preview failed.';
		} finally {
			previewLoading = false;
		}
	}

	async function submitRequest() {
		if (!finding || submitting) return;
		if (preview?.decision?.toLowerCase() === 'block') {
			actionError = 'Policy blocks this remediation request.';
			return;
		}

		if (!accessToken) {
			actionError = 'Not authenticated.';
			return;
		}

		submitting = true;
		actionError = '';
		actionSuccess = '';

		try {
			const headers = {
				Authorization: `Bearer ${accessToken}`,
				'Content-Type': 'application/json'
			};
			const action = deriveRemediationAction(finding);
			const response = await api.post(
				`${PUBLIC_API_URL}/zombies/request`,
				{
					resource_id: finding.resource_id,
					resource_type: finding.resource_type || 'unknown',
					provider: finding.provider || 'aws',
					connection_id: finding.connection_id,
					action,
					estimated_savings: parseMonthlyCost(finding.monthly_cost),
					create_backup: true
				},
				{ headers }
			);

			if (!response.ok) {
				const payload = await response.json().catch(() => ({}));
				throw new Error(
					payload.detail ||
						payload.message ||
						(response.status === 403
							? 'Upgrade required: Auto-remediation requires Pro tier or higher.'
							: 'Failed to create remediation request.')
				);
			}

			const result = await response.json();
			const decisionValue = preview?.decision?.toUpperCase();
			const summaryText = preview?.summary || '';
			actionSuccess = `Request ${result.request_id} created.${
				decisionValue ? ` Policy: ${decisionValue}${summaryText ? ` - ${summaryText}` : ''}.` : ''
			}`;
		} catch (e) {
			const err = e as Error;
			actionError = err.message || 'Failed to create remediation request.';
		} finally {
			submitting = false;
		}
	}

	function handleClose() {
		if (submitting) return;
		isOpen = false;
		preview = null;
		previewError = '';
		actionError = '';
		actionSuccess = '';
		onClose();
	}
</script>

{#if isOpen && finding}
	<div class="modal modal-open">
		<div class="modal-box max-w-2xl bg-ink-950 border border-ink-800 shadow-2xl">
			<div class="flex items-center justify-between mb-6">
				<h3 class="text-xl font-bold flex items-center gap-2">
					<AlertTriangle class="h-5 w-5 text-warning-400" />
					Remediate Resource
				</h3>
				<button class="btn btn-sm btn-ghost" onclick={handleClose} disabled={submitting}>✕</button>
			</div>

			<div class="space-y-6">
				<!-- Resource Info -->
				<div class="grid grid-cols-2 gap-4 p-4 bg-ink-900/50 rounded-lg border border-ink-800">
					<div>
						<p class="text-xs text-ink-400 uppercase font-bold mb-1">Resource ID</p>
						<p class="font-mono text-sm truncate">{finding.resource_id}</p>
					</div>
					<div>
						<p class="text-xs text-ink-400 uppercase font-bold mb-1">Type</p>
						<p class="text-sm">{finding.resource_type || 'Unknown'}</p>
					</div>
					<div>
						<p class="text-xs text-ink-400 uppercase font-bold mb-1">Provider</p>
						<p class="text-sm uppercase font-semibold">{finding.provider || 'AWS'}</p>
					</div>
					<div>
						<p class="text-xs text-ink-400 uppercase font-bold mb-1">Monthly Cost</p>
						<p class="text-sm text-danger-400 font-bold">${finding.monthly_cost || '0.00'}</p>
					</div>
				</div>

				<!-- Policy Preview -->
				<div class="space-y-3">
					<h4 class="text-sm font-semibold flex items-center gap-2 text-ink-200">
						<Clock class="h-4 w-4" />
						Policy Preview
					</h4>

					{#if previewLoading}
						<div class="flex items-center gap-3 p-4 bg-ink-900 rounded-lg border border-ink-800">
							<div class="spinner spinner-sm"></div>
							<p class="text-sm text-ink-400 italic">Running deterministic policy simulation...</p>
						</div>
					{:else if previewError}
						<div class="p-4 bg-danger-500/10 border border-danger-500/30 rounded-lg">
							<p class="text-sm text-danger-400">{previewError}</p>
							<button class="btn btn-xs btn-outline mt-2" onclick={runPreview}>Retry Preview</button>
						</div>
					{:else if preview}
						<div
							class="p-4 rounded-lg border {preview.decision === 'BLOCK'
								? 'bg-danger-500/10 border-danger-500/30'
								: 'bg-ink-900 border-ink-800'}"
						>
							<div class="flex items-center justify-between mb-2">
								<span class={policyDecisionClass(preview.decision)}>
									Decision: {preview.decision}
								</span>
								<span class="text-[10px] text-ink-500 font-mono">Tier: {preview.tier}</span>
							</div>
							<p class="text-sm text-ink-300 mb-3">{preview.summary}</p>

							{#if preview.rule_hits.length > 0}
								<div class="bg-black/20 p-2 rounded text-[10px] text-ink-400 space-y-1">
									<p class="font-bold opacity-60">Rule Hits:</p>
									{#each preview.rule_hits as hit (hit.rule_id)}
										<div class="flex gap-2">
											<span class="text-accent-500">[{hit.rule_id}]</span>
											<span>{hit.message || 'Rule matched condition'}</span>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
				</div>

				<!-- Global Actions -->
				{#if actionError}
					<div class="p-4 bg-danger-500/10 border border-danger-500/30 rounded-lg">
						<p class="text-sm text-danger-400 font-semibold">{actionError}</p>
					</div>
				{/if}

				{#if actionSuccess}
					<div class="p-4 bg-success-500/10 border border-success-500/30 rounded-lg">
						<p class="text-sm text-success-400 font-semibold">{actionSuccess}</p>
						<p class="text-xs text-success-400/70 mt-1">This request has been added to the operator queue.</p>
					</div>
				{/if}
			</div>

			<div class="modal-action">
				{#if actionSuccess}
					<button class="btn btn-primary" onclick={handleClose}>Close Queue</button>
				{:else}
					<button class="btn btn-ghost" onclick={handleClose} disabled={submitting}>Cancel</button>
					<button
						class="btn btn-primary min-w-[140px]"
						disabled={submitting ||
							previewLoading ||
							!!previewError ||
							preview?.decision?.toLowerCase() === 'block'}
						onclick={submitRequest}
					>
						{#if submitting}
							<span class="spinner spinner-xs mr-2"></span>
							Submitting...
						{:else}
							Approve & Queue
						{/if}
					</button>
				{/if}
			</div>
		</div>
	</div>
{/if}
