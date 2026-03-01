<script lang="ts">
	import CloudLogo from '$lib/components/CloudLogo.svelte';
	import { type ZombieCollectionKey, type ZombieCollections } from '$lib/zombieCollections';

	type RemediationFinding = {
		resource_id: string;
		resource_type?: string;
		provider?: string;
		connection_id?: string;
		monthly_cost?: string | number;
		recommended_action?: string;
		owner?: string;
		explainability_notes?: string;
		confidence_score?: number;
		db_class?: string;
		lb_type?: string;
		is_gpu?: boolean;
		instance_type?: string;
		recommended_instance_type?: string;
	};

	type RemediationZombieCollections = ZombieCollections<RemediationFinding>;

	type ZombieCategoryConfig = {
		key: ZombieCollectionKey;
		defaultExplainability: string;
		resourceClassName?: string;
		typeLabel: string | ((finding: RemediationFinding) => string);
	};

	const CATEGORY_CONFIG: ZombieCategoryConfig[] = [
		{
			key: 'unattached_volumes',
			typeLabel: 'EBS Volume',
			defaultExplainability: 'Resource detached and accruing idle costs.'
		},
		{
			key: 'old_snapshots',
			typeLabel: 'Snapshot',
			defaultExplainability: 'Snapshot age exceeds standard retention policy.'
		},
		{
			key: 'unused_elastic_ips',
			typeLabel: 'Elastic IP',
			defaultExplainability: 'Unassociated EIP address found.'
		},
		{
			key: 'idle_instances',
			typeLabel: (finding) =>
				`Idle EC2${finding.instance_type ? ` (${finding.instance_type})` : ''}`,
			defaultExplainability: 'Low CPU and network utilization detected over 7 days.'
		},
		{
			key: 'orphan_load_balancers',
			typeLabel: (finding) => `Orphan ${(finding.lb_type || 'load balancer').toUpperCase()}`,
			defaultExplainability: 'Load balancer has no healthy targets associated.'
		},
		{
			key: 'idle_rds_databases',
			typeLabel: (finding) => `Idle RDS${finding.db_class ? ` (${finding.db_class})` : ''}`,
			defaultExplainability: 'No connections detected in the last billing cycle.'
		},
		{
			key: 'underused_nat_gateways',
			typeLabel: 'Idle NAT Gateway',
			defaultExplainability: 'Minimal data processing detected compared to runtime cost.'
		},
		{
			key: 'idle_s3_buckets',
			typeLabel: 'Idle S3 Bucket',
			defaultExplainability: 'No GET/PUT requests recorded in the last 30 days.'
		},
		{
			key: 'stale_ecr_images',
			typeLabel: 'ECR Image',
			defaultExplainability: 'Untagged or superseded by multiple newer versions.',
			resourceClassName: 'truncate max-w-[150px]'
		},
		{
			key: 'idle_sagemaker_endpoints',
			typeLabel: 'SageMaker Endpoint',
			defaultExplainability: 'Endpoint has not processed any inference requests recently.'
		},
		{
			key: 'cold_redshift_clusters',
			typeLabel: 'Redshift Cluster',
			defaultExplainability: 'Cluster has been in idle state for over 14 days.'
		}
	];

	let { zombies, zombieCount, onRemediate } = $props<{
		zombies: RemediationZombieCollections | null | undefined;
		zombieCount: number;
		onRemediate: (finding: RemediationFinding) => void;
	}>();

	function providerColorClass(provider: string | undefined): string {
		if (provider === 'aws') return 'text-orange-400';
		if (provider === 'azure') return 'text-blue-400';
		return 'text-yellow-400';
	}

	function providerLabel(provider: string | undefined): string {
		return provider || 'AWS';
	}

	function confidenceRatio(score: number | undefined): number | null {
		if (typeof score !== 'number' || !Number.isFinite(score)) return null;
		return Math.max(0, Math.min(1, score));
	}

	function confidenceBarWidth(score: number | undefined): string {
		const ratio = confidenceRatio(score);
		return `${Math.round((ratio ?? 0) * 100)}%`;
	}

	function confidenceLabel(score: number | undefined): string {
		const ratio = confidenceRatio(score);
		if (ratio === null) return 'N/A';
		return `${Math.round(ratio * 100)}% Match`;
	}

	function typeLabel(config: ZombieCategoryConfig, finding: RemediationFinding): string {
		return typeof config.typeLabel === 'function' ? config.typeLabel(finding) : config.typeLabel;
	}

	function monthlyCostLabel(value: RemediationFinding['monthly_cost']): string {
		if (value === null || value === undefined || value === '') return '0';
		return String(value);
	}

	let zombieRows = $derived.by(() =>
		CATEGORY_CONFIG.flatMap((config) => {
			const findings = (zombies?.[config.key] ?? []) as RemediationFinding[];
			return findings.map((finding) => ({
				key: `${config.key}:${finding.resource_id}`,
				config,
				finding
			}));
		})
	);
</script>

<div class="card stagger-enter" style="animation-delay: 250ms;">
	<div class="flex items-center justify-between mb-5">
		<h2 class="text-lg font-semibold">Zombie Resources</h2>
		<span class="badge badge-warning">{zombieCount} found</span>
	</div>

	<div class="overflow-x-auto">
		<table class="table">
			<thead>
				<tr>
					<th>Cloud</th>
					<th>Resource</th>
					<th>Type</th>
					<th>Monthly Cost</th>
					<th>Owner</th>
					<th>AI Reasoning & Confidence</th>
					<th>Action</th>
				</tr>
			</thead>
			<tbody>
				{#each zombieRows as row (row.key)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={row.finding.provider} size={12} />
							<span class="text-xs font-bold uppercase {providerColorClass(row.finding.provider)}">
								{providerLabel(row.finding.provider)}
							</span>
						</td>
						<td class="font-mono text-xs {row.config.resourceClassName ?? ''}">
							{row.finding.resource_id}
						</td>
						<td>
							<div class="flex items-center gap-1.5">
								<span class="badge badge-default">{typeLabel(row.config, row.finding)}</span>
								{#if row.config.key === 'idle_instances' && row.finding.is_gpu}
									<span class="badge badge-error py-0 text-xs uppercase font-bold">GPU</span>
								{/if}
							</div>
						</td>
						<td class="text-danger-400">${monthlyCostLabel(row.finding.monthly_cost)}</td>
						<td class="text-xs text-ink-400">{row.finding.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-xs leading-tight text-ink-300">
									{row.finding.explainability_notes || row.config.defaultExplainability}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {confidenceBarWidth(row.finding.confidence_score)}"
										></div>
									</div>
									<span class="text-xs font-bold text-accent-400">
										{confidenceLabel(row.finding.confidence_score)}
									</span>
								</div>
							</div>
						</td>
						<td>
							<button
								type="button"
								class="btn btn-ghost text-xs"
								onclick={() => onRemediate(row.finding)}
							>
								Review
							</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
