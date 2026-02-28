<script lang="ts">
	import { base } from '$app/paths';

	type ValidationItem = {
		capability: string;
		apiSurface: string;
		validationScope: string;
	};

	const VALIDATION_ITEMS: readonly ValidationItem[] = Object.freeze([
		{
			capability: 'Cost Intelligence and Forecasting',
			apiSurface: '/api/v1/costs, /api/v1/attribution, /api/v1/usage, /api/v1/currency',
			validationScope: 'Spend ingestion, anomaly routing, attribution coverage, forecast output'
		},
		{
			capability: 'GreenOps Execution',
			apiSurface: '/api/v1/carbon, /api/v1/settings/carbon',
			validationScope: 'Carbon budget logic, intensity references, scheduling recommendations'
		},
		{
			capability: 'Cloud Hygiene and Remediation',
			apiSurface: '/api/v1/zombies, /api/v1/strategies, /api/v1/enforcement/actions',
			validationScope: 'Discovery, owner workflow, approval path, remediation lifecycle'
		},
		{
			capability: 'SaaS and ITAM License Control',
			apiSurface: '/api/v1/settings/connections/* (saas, license, platform, hybrid)',
			validationScope: 'Connector verification, usage feed handling, license governance flow'
		},
		{
			capability: 'Financial Guardrails',
			apiSurface:
				'/api/v1/enforcement/gate, /api/v1/enforcement/policies, /api/v1/enforcement/budgets, /api/v1/enforcement/credits, /api/v1/enforcement/approvals, /api/v1/enforcement/reservations',
			validationScope: 'Budget/credit checks, approval routing, reservation integrity, decision ledger'
		},
		{
			capability: 'Savings Proof for Leadership',
			apiSurface: '/api/v1/savings, /api/v1/leaderboards, /api/v1/leadership',
			validationScope: 'Realized savings events, KPI reporting, executive review outputs'
		},
		{
			capability: 'Operational Integrations',
			apiSurface: '/api/v1/settings/notifications, /api/v1/jobs',
			validationScope: 'Slack/Teams/Jira workflows, alert pathways, background processing status'
		},
		{
			capability: 'Security and Identity',
			apiSurface: '/scim/v2, /api/v1/settings/identity, /api/v1/audit',
			validationScope: 'Identity lifecycle, role-scoped access, audit retrieval and export controls'
		}
	]);
</script>

<svelte:head>
	<title>Technical Validation | Valdrics</title>
	<meta
		name="description"
		content="Public technical validation summary mapping Valdrics capabilities to API surface areas used in buyer and security diligence."
	/>
</svelte:head>

<section class="container mx-auto px-6 py-12 space-y-8">
	<header class="space-y-3">
		<p class="text-xs uppercase tracking-[0.18em] text-accent-300 font-bold">Technical Validation</p>
		<h1 class="text-3xl font-bold text-ink-100">Public capability validation summary</h1>
		<p class="text-ink-300 max-w-3xl">
			This page shows how public product capabilities map to active API surface areas used in
			technical, security, and buyer diligence.
		</p>
	</header>

	<div class="glass-panel overflow-x-auto">
		<table class="w-full text-sm">
			<thead>
				<tr class="text-left text-ink-500 border-b border-ink-800">
					<th class="py-3 pr-4 font-semibold">Capability</th>
					<th class="py-3 pr-4 font-semibold">API Surface</th>
					<th class="py-3 font-semibold">Validation Scope</th>
				</tr>
			</thead>
			<tbody>
				{#each VALIDATION_ITEMS as item (item.capability)}
					<tr class="border-b border-ink-900/60 align-top">
						<td class="py-3 pr-4 text-ink-100 font-medium">{item.capability}</td>
						<td class="py-3 pr-4 text-ink-300">{item.apiSurface}</td>
						<td class="py-3 text-ink-300">{item.validationScope}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<div class="glass-panel space-y-3">
		<h2 class="text-xl font-semibold">What this page is and is not</h2>
		<ul class="text-sm text-ink-300 space-y-1 list-disc pl-5">
			<li>It is a public, buyer-safe validation map for capability coverage.</li>
			<li>It does not expose internal incident data, private traces, or tenant-sensitive evidence.</li>
			<li>For implementation detail, use API docs and private diligence channels as appropriate.</li>
		</ul>
		<div class="flex flex-wrap gap-3 pt-1">
			<a href={`${base}/docs/api`} class="btn btn-secondary">API Reference</a>
			<a href={`${base}/docs`} class="btn btn-secondary">Documentation</a>
			<a href={`${base}/`} class="btn btn-primary">Back to Landing</a>
		</div>
	</div>
</section>
