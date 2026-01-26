<script lang="ts">
	import CloudLogo from './CloudLogo.svelte';
	import DOMPurify from 'dompurify';
	import { Terminal, Copy, Check } from '@lucide/svelte';

	interface ZombieFinding {
		provider: 'aws' | 'azure' | 'gcp';
		resource_id: string;
		resource_type?: string;
		monthly_cost?: string | number;
		confidence?: 'high' | 'medium' | 'low';
		risk_if_deleted?: 'high' | 'medium' | 'low';
		explanation: string;
		confidence_reason?: string;
		recommended_action?: string;
		connection_id?: string;
		owner?: string;
		is_gpu?: boolean;
	}

	let {
		resources = [],
		onRemediate,
		remediating = null
	}: {
		resources: ZombieFinding[];
		onRemediate: (finding: ZombieFinding) => Promise<void>;
		remediating?: string | null;
	} = $props();

	let currentPage = $state(0);
	let copiedId = $state<string | null>(null);
	const pageSize = 10;

	let totalPages = $derived(Math.ceil(resources.length / pageSize));
	let paginatedResources = $derived(
		resources.slice(currentPage * pageSize, (currentPage + 1) * pageSize)
	);

	function generateSniperCommand(finding: ZombieFinding): string {
		const id = finding.resource_id;
		const type = finding.resource_type?.toLowerCase() || '';

		if (finding.provider === 'aws') {
			if (type.includes('volume') || type.includes('ebs')) {
				return `aws ec2 delete-volume --volume-id ${id}`;
			}
			if (type.includes('instance')) {
				return `aws ec2 terminate-instances --instance-ids ${id}`;
			}
			if (type.includes('snapshot')) {
				return `aws ec2 delete-snapshot --snapshot-id ${id}`;
			}
			if (type.includes('eip') || type.includes('address')) {
				return `aws ec2 release-address --allocation-id ${id}`;
			}
			return `# AWS Snipe: ${id}\naws resourcegroupstaggingapi untag-resources --resource-arn-list ${id}`;
		}

		if (finding.provider === 'azure') {
			return `az resource delete --ids ${id}`;
		}

		if (finding.provider === 'gcp') {
			return `gcloud compute instances delete ${id} --quiet`;
		}

		return `# Sniper Command for ${id} not generated`;
	}

	async function copyToClipboard(text: string, id: string) {
		try {
			await navigator.clipboard.writeText(text);
			copiedId = id;
			setTimeout(() => {
				if (copiedId === id) copiedId = null;
			}, 2000);
		} catch (err) {
			console.error('Failed to copy: ', err);
		}
	}
</script>

<div class="card stagger-enter" style="animation-delay: 250ms;">
	<!-- Table Header -->
	<div class="flex items-center justify-between mb-4">
		<h3 class="text-lg font-semibold">
			🧟 Zombie Resources ({resources.length})
		</h3>
		<div class="flex items-center gap-2 text-xs text-ink-400">
			<span>Page {currentPage + 1} of {totalPages}</span>
		</div>
	</div>

	<!-- Responsive Table -->
	<div class="overflow-x-auto">
		<table class="w-full text-sm">
			<thead>
				<tr class="border-b border-ink-700 text-left text-xs text-ink-400 uppercase tracking-wider">
					<th class="pb-3 pr-4">Provider</th>
					<th class="pb-3 pr-4">Resource</th>
					<th class="pb-3 pr-4">Type</th>
					<th class="pb-3 pr-4">Cost</th>
					<th class="pb-3 pr-4">Confidence</th>
					<th class="pb-3 pr-4">Owner</th>
					<th class="pb-3 pr-4">Risk</th>
					<th class="pb-3 text-right">Action</th>
				</tr>
			</thead>
			<tbody>
				{#each paginatedResources as finding (finding.resource_id)}
					<tr class="border-b border-ink-800 hover:bg-ink-800/50 transition-colors">
						<!-- Provider -->
						<td class="py-3 pr-4">
							<div
								class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-tighter
                {finding.provider === 'aws'
									? 'bg-orange-500/10 text-orange-400 border border-orange-500/20'
									: finding.provider === 'azure'
										? 'bg-blue-500/10 text-blue-400 border border-blue-500/20'
										: 'bg-yellow-500/10 text-yellow-400 border border-yellow-500/20'}"
							>
								<CloudLogo provider={finding.provider} size={10} />
								<span
									>{finding.provider === 'aws'
										? 'AWS'
										: finding.provider === 'azure'
											? 'Azure'
											: 'GCP'}</span
								>
							</div>
						</td>
						<!-- Resource ID -->
						<td class="py-3 pr-4">
							<div class="font-mono text-xs truncate max-w-[150px]" title={finding.resource_id}>
								{finding.resource_id}
							</div>
							<!-- Expandable explanation -->
							<details class="mt-1">
								<summary class="text-xs text-ink-500 cursor-pointer hover:text-accent-400">
									View details
								</summary>
								<p class="text-xs text-ink-400 mt-1 max-w-xs">
									<!-- eslint-disable-next-line svelte/no-at-html-tags -->
									{@html DOMPurify.sanitize(finding.explanation, {
										ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'br', 'p', 'ul', 'li', 'code'],
										ALLOWED_ATTR: []
									})}
								</p>
								{#if finding.confidence_reason}
									<p class="text-xs text-ink-500 mt-1 italic">
										{finding.confidence_reason}
									</p>
								{/if}
							</details>
						</td>

						<!-- Type Badge -->
						<td class="py-3 pr-4">
							<span class="badge badge-default text-xs">
								{finding.resource_type || 'Resource'}
							</span>
							{#if finding.is_gpu}
								<span
									class="badge badge-error py-0.5 px-1.5 text-[10px] uppercase font-bold animate-pulse"
									>GPU</span
								>
							{/if}
						</td>

						<!-- Monthly Cost -->
						<td class="py-3 pr-4 font-semibold text-success-400">
							{finding.monthly_cost || '$0'}
						</td>

						<!-- Confidence -->
						<td class="py-3 pr-4">
							{#if finding.confidence}
								<span class="inline-flex items-center gap-1">
									<span
										class="w-2 h-2 rounded-full {finding.confidence === 'high'
											? 'bg-danger-400'
											: finding.confidence === 'medium'
												? 'bg-warning-400'
												: 'bg-success-400'}"
									></span>
									<span class="text-xs capitalize">{finding.confidence}</span>
								</span>
							{:else}
								<span class="text-xs text-ink-500 italic">N/A</span>
							{/if}
						</td>

						<td class="py-3 pr-4">
							<div class="flex flex-col">
								{#if finding.owner === 'Upgrade to Growth'}
									<span
										class="text-[10px] font-bold text-warning-400 flex items-center gap-1"
										title="Owner Attribution requires Growth tier"
									>
										<span class="w-1 h-1 rounded-full bg-warning-400 animate-ping"></span>
										LOCKED
									</span>
								{:else}
									<span
										class="text-xs text-ink-300 truncate max-w-[120px]"
										title={finding.owner || 'unknown'}
									>
										{finding.owner || 'unknown'}
									</span>
								{/if}
							</div>
						</td>

						<!-- Risk -->
						<td class="py-3 pr-4">
							<span
								class="text-xs {finding.risk_if_deleted === 'high'
									? 'text-danger-400'
									: finding.risk_if_deleted === 'medium'
										? 'text-warning-400'
										: 'text-ink-400'}"
							>
								{finding.risk_if_deleted || 'low'}
							</span>
						</td>

						<!-- Action Button -->
						<td class="py-3 text-right">
							<div class="flex items-center justify-end gap-2">
								<button
									class="btn btn-ghost btn-xs text-ink-400 hover:text-accent-400"
									onclick={() =>
										copyToClipboard(generateSniperCommand(finding), finding.resource_id)}
									title="Copy Sniper Command"
								>
									{#if copiedId === finding.resource_id}
										<Check size={14} class="text-success-400" />
									{:else}
										<Terminal size={14} />
									{/if}
								</button>
								<button
									class="btn btn-ghost text-xs hover:bg-accent-500/20 hover:text-accent-400"
									onclick={() => onRemediate(finding)}
									disabled={remediating === finding.resource_id}
								>
									{#if remediating === finding.resource_id}
										<span class="animate-pulse">...</span>
									{:else}
										{finding.recommended_action || 'Review'}
									{/if}
								</button>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- Pagination -->
	{#if totalPages > 1}
		<div class="flex items-center justify-between mt-4 pt-4 border-t border-ink-800">
			<button
				class="btn btn-ghost text-xs"
				disabled={currentPage === 0}
				onclick={() => (currentPage = Math.max(0, currentPage - 1))}
			>
				← Previous
			</button>

			<div class="flex items-center gap-1">
				<!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
				{#each Array(Math.min(totalPages, 5)) as _, p (p)}
					{@const pageNum =
						totalPages <= 5
							? p
							: currentPage < 3
								? p
								: currentPage > totalPages - 3
									? totalPages - 5 + p
									: currentPage - 2 + p}
					<button
						class="w-8 h-8 rounded text-xs {currentPage === pageNum
							? 'bg-accent-500 text-white'
							: 'hover:bg-ink-700'}"
						onclick={() => (currentPage = pageNum)}
					>
						{pageNum + 1}
					</button>
				{/each}
			</div>

			<button
				class="btn btn-ghost text-xs"
				disabled={currentPage >= totalPages - 1}
				onclick={() => (currentPage = Math.min(totalPages - 1, currentPage + 1))}
			>
				Next →
			</button>
		</div>
	{/if}
</div>
