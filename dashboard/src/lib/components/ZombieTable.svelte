<script lang="ts">
	import CloudLogo from '$lib/components/CloudLogo.svelte';

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
		// Specific fields
		db_class?: string;
		lb_type?: string;
		is_gpu?: boolean;
		instance_type?: string;
	};

	let { 
		zombies, 
		zombieCount, 
		onRemediate 
	} = $props<{
		zombies: any;
		zombieCount: number;
		onRemediate: (finding: RemediationFinding) => void;
	}>();
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
				<!-- Volumes -->
				{#each zombies?.unattached_volumes ?? [] as vol (vol.resource_id)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={vol.provider} size={12} />
							<span
								class="text-[10px] font-bold uppercase {vol.provider === 'aws'
									? 'text-orange-400'
									: vol.provider === 'azure'
										? 'text-blue-400'
										: 'text-yellow-400'}"
							>
								{vol.provider || 'AWS'}
							</span>
						</td>
						<td class="font-mono text-xs">{vol.resource_id}</td>
						<td><span class="badge badge-default">EBS Volume</span></td>
						<td class="text-danger-400">${vol.monthly_cost}</td>
						<td class="text-xs text-ink-400">{vol.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-[10px] leading-tight text-ink-300">
									{vol.explainability_notes || 'Resource detached and accruing idle costs.'}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {vol.confidence_score ? vol.confidence_score * 100 : 0}%"
										></div>
									</div>
									<span class="text-[10px] font-bold text-accent-400"
										>{vol.confidence_score
											? Math.round(vol.confidence_score * 100) + '% Match'
											: 'N/A'}</span
									>
								</div>
							</div>
						</td>
						<td>
							<button class="btn btn-ghost text-xs" onclick={() => onRemediate(vol)}>Review</button>
						</td>
					</tr>
				{/each}

				<!-- Snapshots -->
				{#each zombies?.old_snapshots ?? [] as snap (snap.resource_id)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={snap.provider} size={12} />
							<span
								class="text-[10px] font-bold uppercase {snap.provider === 'aws'
									? 'text-orange-400'
									: snap.provider === 'azure'
										? 'text-blue-400'
										: 'text-yellow-400'}"
							>
								{snap.provider || 'AWS'}
							</span>
						</td>
						<td class="font-mono text-xs">{snap.resource_id}</td>
						<td><span class="badge badge-default">Snapshot</span></td>
						<td class="text-danger-400">${snap.monthly_cost}</td>
						<td class="text-xs text-ink-400">{snap.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-[10px] leading-tight text-ink-300">
									{snap.explainability_notes || 'Snapshot age exceeds standard retention policy.'}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {snap.confidence_score ? snap.confidence_score * 100 : 0}%"
										></div>
									</div>
									<span class="text-[10px] font-bold text-accent-400"
										>{snap.confidence_score
											? Math.round(snap.confidence_score * 100) + '% Match'
											: 'N/A'}</span
									>
								</div>
							</div>
						</td>
						<td>
							<button class="btn btn-ghost text-xs" onclick={() => onRemediate(snap)}>Review</button>
						</td>
					</tr>
				{/each}

				<!-- EIPs -->
				{#each zombies?.unused_elastic_ips ?? [] as eip (eip.resource_id)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={eip.provider} size={12} />
							<span
								class="text-[10px] font-bold uppercase {eip.provider === 'aws'
									? 'text-orange-400'
									: eip.provider === 'azure'
										? 'text-blue-400'
										: 'text-yellow-400'}"
							>
								{eip.provider || 'AWS'}
							</span>
						</td>
						<td class="font-mono text-xs">{eip.resource_id}</td>
						<td><span class="badge badge-default">Elastic IP</span></td>
						<td class="text-danger-400">${eip.monthly_cost}</td>
						<td class="text-xs text-ink-400">{eip.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-[10px] leading-tight text-ink-300">
									{eip.explainability_notes || 'Unassociated EIP address found.'}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {eip.confidence_score ? eip.confidence_score * 100 : 0}%"
										></div>
									</div>
									<span class="text-[10px] font-bold text-accent-400"
										>{eip.confidence_score
											? Math.round(eip.confidence_score * 100) + '% Match'
											: 'N/A'}</span
									>
								</div>
							</div>
						</td>
						<td>
							<button class="btn btn-ghost text-xs" onclick={() => onRemediate(eip)}>Review</button>
						</td>
					</tr>
				{/each}

				<!-- Instances -->
				{#each zombies?.idle_instances ?? [] as ec2 (ec2.resource_id)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={ec2.provider} size={12} />
							<span
								class="text-[10px] font-bold uppercase {ec2.provider === 'aws'
									? 'text-orange-400'
									: ec2.provider === 'azure'
										? 'text-blue-400'
										: 'text-yellow-400'}"
							>
								{ec2.provider || 'AWS'}
							</span>
						</td>
						<td class="font-mono text-xs">{ec2.resource_id}</td>
						<td>
							<div class="flex items-center gap-1.5">
								<span class="badge badge-default">Idle EC2 ({ec2.instance_type})</span>
								{#if ec2.is_gpu}
									<span class="badge badge-error py-0 text-[9px] uppercase font-bold">GPU</span>
								{/if}
							</div>
						</td>
						<td class="text-danger-400">${ec2.monthly_cost}</td>
						<td class="text-xs text-ink-400">{ec2.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-[10px] leading-tight text-ink-300">
									{ec2.explainability_notes || 'Low CPU and network utilization detected over 7 days.'}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {ec2.confidence_score ? ec2.confidence_score * 100 : 0}%"
										></div>
									</div>
									<span class="text-[10px] font-bold text-accent-400"
										>{ec2.confidence_score
											? Math.round(ec2.confidence_score * 100) + '% Match'
											: 'N/A'}</span
									>
								</div>
							</div>
						</td>
						<td>
							<button class="btn btn-ghost text-xs" onclick={() => onRemediate(ec2)}>Review</button>
						</td>
					</tr>
				{/each}

				<!-- Load Balancers -->
				{#each zombies?.orphan_load_balancers ?? [] as lb (lb.resource_id)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={lb.provider} size={12} />
							<span
								class="text-[10px] font-bold uppercase {lb.provider === 'aws'
									? 'text-orange-400'
									: lb.provider === 'azure'
										? 'text-blue-400'
										: 'text-yellow-400'}"
							>
								{lb.provider || 'AWS'}
							</span>
						</td>
						<td class="font-mono text-xs">{lb.resource_id}</td>
						<td><span class="badge badge-default">Orphan {lb.lb_type?.toUpperCase()}</span></td>
						<td class="text-danger-400">${lb.monthly_cost}</td>
						<td class="text-xs text-ink-400">{lb.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-[10px] leading-tight text-ink-300">
									{lb.explainability_notes || 'Load balancer has no healthy targets associated.'}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {lb.confidence_score ? lb.confidence_score * 100 : 0}%"
										></div>
									</div>
									<span class="text-[10px] font-bold text-accent-400"
										>{lb.confidence_score
											? Math.round(lb.confidence_score * 100) + '% Match'
											: 'N/A'}</span
									>
								</div>
							</div>
						</td>
						<td>
							<button class="btn btn-ghost text-xs" onclick={() => onRemediate(lb)}>Review</button>
						</td>
					</tr>
				{/each}

				<!-- RDS -->
				{#each zombies?.idle_rds_databases ?? [] as rds (rds.resource_id)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={rds.provider} size={12} />
							<span
								class="text-[10px] font-bold uppercase {rds.provider === 'aws'
									? 'text-orange-400'
									: rds.provider === 'azure'
										? 'text-blue-400'
										: 'text-yellow-400'}"
							>
								{rds.provider || 'AWS'}
							</span>
						</td>
						<td class="font-mono text-xs">{rds.resource_id}</td>
						<td><span class="badge badge-default">Idle RDS ({rds.db_class})</span></td>
						<td class="text-danger-400">${rds.monthly_cost}</td>
						<td class="text-xs text-ink-400">{rds.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-[10px] leading-tight text-ink-300">
									{rds.explainability_notes || 'No connections detected in the last billing cycle.'}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {rds.confidence_score ? rds.confidence_score * 100 : 0}%"
										></div>
									</div>
									<span class="text-[10px] font-bold text-accent-400"
										>{rds.confidence_score
											? Math.round(rds.confidence_score * 100) + '% Match'
											: 'N/A'}</span
									>
								</div>
							</div>
						</td>
						<td>
							<button class="btn btn-ghost text-xs" onclick={() => onRemediate(rds)}>Review</button>
						</td>
					</tr>
				{/each}

				<!-- NAT -->
				{#each zombies?.underused_nat_gateways ?? [] as nat (nat.resource_id)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={nat.provider} size={12} />
							<span
								class="text-[10px] font-bold uppercase {nat.provider === 'aws'
									? 'text-orange-400'
									: nat.provider === 'azure'
										? 'text-blue-400'
										: 'text-yellow-400'}"
							>
								{nat.provider || 'AWS'}
							</span>
						</td>
						<td class="font-mono text-xs">{nat.resource_id}</td>
						<td><span class="badge badge-default">Idle NAT Gateway</span></td>
						<td class="text-danger-400">${nat.monthly_cost}</td>
						<td class="text-xs text-ink-400">{nat.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-[10px] leading-tight text-ink-300">
									{nat.explainability_notes || 'Minimal data processing detected compared to runtime cost.'}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {nat.confidence_score ? nat.confidence_score * 100 : 0}%"
										></div>
									</div>
									<span class="text-[10px] font-bold text-accent-400"
										>{nat.confidence_score
											? Math.round(nat.confidence_score * 100) + '% Match'
											: 'N/A'}</span
									>
								</div>
							</div>
						</td>
						<td>
							<button class="btn btn-ghost text-xs" onclick={() => onRemediate(nat)}>Review</button>
						</td>
					</tr>
				{/each}

				<!-- S3 -->
				{#each zombies?.idle_s3_buckets ?? [] as s3 (s3.resource_id)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={s3.provider} size={12} />
							<span
								class="text-[10px] font-bold uppercase {s3.provider === 'aws'
									? 'text-orange-400'
									: s3.provider === 'azure'
										? 'text-blue-400'
										: 'text-yellow-400'}"
							>
								{s3.provider || 'AWS'}
							</span>
						</td>
						<td class="font-mono text-xs">{s3.resource_id}</td>
						<td><span class="badge badge-default">Idle S3 Bucket</span></td>
						<td class="text-danger-400">${s3.monthly_cost}</td>
						<td class="text-xs text-ink-400">{s3.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-[10px] leading-tight text-ink-300">
									{s3.explainability_notes || 'No GET/PUT requests recorded in the last 30 days.'}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {s3.confidence_score ? s3.confidence_score * 100 : 0}%"
										></div>
									</div>
									<span class="text-[10px] font-bold text-accent-400"
										>{s3.confidence_score
											? Math.round(s3.confidence_score * 100) + '% Match'
											: 'N/A'}</span
									>
								</div>
							</div>
						</td>
						<td>
							<button class="btn btn-ghost text-xs" onclick={() => onRemediate(s3)}>Review</button>
						</td>
					</tr>
				{/each}

				<!-- ECR -->
				{#each zombies?.stale_ecr_images ?? [] as ecr (ecr.resource_id)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={ecr.provider} size={12} />
							<span
								class="text-[10px] font-bold uppercase {ecr.provider === 'aws'
									? 'text-orange-400'
									: ecr.provider === 'azure'
										? 'text-blue-400'
										: 'text-yellow-400'}"
							>
								{ecr.provider || 'AWS'}
							</span>
						</td>
						<td class="font-mono text-xs truncate max-w-[150px]">{ecr.resource_id}</td>
						<td><span class="badge badge-default">ECR Image</span></td>
						<td class="text-danger-400">${ecr.monthly_cost}</td>
						<td class="text-xs text-ink-400">{ecr.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-[10px] leading-tight text-ink-300">
									{ecr.explainability_notes || 'Untagged or superseded by multiple newer versions.'}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {ecr.confidence_score ? ecr.confidence_score * 100 : 0}%"
										></div>
									</div>
									<span class="text-[10px] font-bold text-accent-400"
										>{ecr.confidence_score
											? Math.round(ecr.confidence_score * 100) + '% Match'
											: 'N/A'}</span
									>
								</div>
							</div>
						</td>
						<td>
							<button class="btn btn-ghost text-xs" onclick={() => onRemediate(ecr)}>Review</button>
						</td>
					</tr>
				{/each}

				<!-- SageMaker -->
				{#each zombies?.idle_sagemaker_endpoints ?? [] as sm (sm.resource_id)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={sm.provider} size={12} />
							<span
								class="text-[10px] font-bold uppercase {sm.provider === 'aws'
									? 'text-orange-400'
									: sm.provider === 'azure'
										? 'text-blue-400'
										: 'text-yellow-400'}"
							>
								{sm.provider || 'AWS'}
							</span>
						</td>
						<td class="font-mono text-xs">{sm.resource_id}</td>
						<td><span class="badge badge-default">SageMaker Endpoint</span></td>
						<td class="text-danger-400">${sm.monthly_cost}</td>
						<td class="text-xs text-ink-400">{sm.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-[10px] leading-tight text-ink-300">
									{sm.explainability_notes || 'Endpoint has not processed any inference requests recently.'}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {sm.confidence_score ? sm.confidence_score * 100 : 0}%"
										></div>
									</div>
									<span class="text-[10px] font-bold text-accent-400"
										>{sm.confidence_score
											? Math.round(sm.confidence_score * 100) + '% Match'
											: 'N/A'}</span
									>
								</div>
							</div>
						</td>
						<td>
							<button class="btn btn-ghost text-xs" onclick={() => onRemediate(sm)}>Review</button>
						</td>
					</tr>
				{/each}

				<!-- Redshift -->
				{#each zombies?.cold_redshift_clusters ?? [] as rs (rs.resource_id)}
					<tr>
						<td class="flex items-center gap-1.5">
							<CloudLogo provider={rs.provider} size={12} />
							<span
								class="text-[10px] font-bold uppercase {rs.provider === 'aws'
									? 'text-orange-400'
									: rs.provider === 'azure'
										? 'text-blue-400'
										: 'text-yellow-400'}"
							>
								{rs.provider || 'AWS'}
							</span>
						</td>
						<td class="font-mono text-xs">{rs.resource_id}</td>
						<td><span class="badge badge-default">Redshift Cluster</span></td>
						<td class="text-danger-400">${rs.monthly_cost}</td>
						<td class="text-xs text-ink-400">{rs.owner || 'unknown'}</td>
						<td>
							<div class="flex flex-col gap-1 max-w-xs">
								<p class="text-[10px] leading-tight text-ink-300">
									{rs.explainability_notes || 'Cluster has been in idle state for over 14 days.'}
								</p>
								<div class="flex items-center gap-2">
									<div class="h-1 w-16 bg-ink-700 rounded-full overflow-hidden">
										<div
											class="h-full bg-accent-500"
											style="width: {rs.confidence_score ? rs.confidence_score * 100 : 0}%"
										></div>
									</div>
									<span class="text-[10px] font-bold text-accent-400"
										>{rs.confidence_score
											? Math.round(rs.confidence_score * 100) + '% Match'
											: 'N/A'}</span
									>
								</div>
							</div>
						</td>
						<td>
							<button class="btn btn-ghost text-xs" onclick={() => onRemediate(rs)}>Review</button>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>
