<!--
  Leaderboards Page - Team Savings Rankings
  
  Features:
  - "Who Saved the Most?" gamification
  - Period filter (7d, 30d, 90d, all)
  - Medal rankings with animations
-->

<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { base } from '$app/paths';
	import { goto } from '$app/navigation';
	import AuthGate from '$lib/components/AuthGate.svelte';
	import { PUBLIC_API_URL } from '$env/static/public';
	import { TimeoutError, fetchWithTimeout } from '$lib/fetchWithTimeout';

	let { data } = $props();

	const LEADERBOARD_TIMEOUT_MS = 8000;

	type LeaderboardEntry = {
		rank: number;
		user_email: string;
		savings_usd: number;
		remediation_count: number;
	};

	type LeaderboardPayload = {
		period: string;
		entries: LeaderboardEntry[];
		total_team_savings: number;
	};

	let period = $derived(data.period || '30d');
	let leaderboard = $state<LeaderboardPayload>({
		period: 'Last 30 Days',
		entries: [],
		total_team_savings: 0
	});
	let error = $state('');
	let loading = $state(false);
	let leaderboardRequestId = 0;

	function toAppPath(path: string): string {
		const normalizedPath = path.startsWith('/') ? path : `/${path}`;
		const normalizedBase = base === '/' ? '' : base;
		return `${normalizedBase}${normalizedPath}`;
	}

	function resetLeaderboardState() {
		leaderboard = {
			period: 'Last 30 Days',
			entries: [],
			total_team_savings: 0
		};
	}

	async function loadLeaderboard(
		accessToken: string | undefined,
		hasUser: boolean,
		currentPeriod: string
	) {
		const requestId = ++leaderboardRequestId;
		if (!hasUser || !accessToken) {
			resetLeaderboardState();
			error = '';
			loading = false;
			return;
		}

		loading = true;
		error = '';

		try {
			const res = await fetchWithTimeout(
				fetch,
				`${PUBLIC_API_URL}/leaderboards?period=${currentPeriod}`,
				{
					headers: {
						Authorization: `Bearer ${accessToken}`
					}
				},
				LEADERBOARD_TIMEOUT_MS
			);

			if (requestId !== leaderboardRequestId) return;

			if (!res.ok) {
				resetLeaderboardState();
				error = `Failed to load leaderboard (HTTP ${res.status})`;
				return;
			}

			leaderboard = (await res.json()) as LeaderboardPayload;
		} catch (err) {
			if (requestId !== leaderboardRequestId) return;
			resetLeaderboardState();
			error =
				err instanceof TimeoutError
					? 'Leaderboard request timed out. Please try again.'
					: 'Network error loading leaderboard';
		} finally {
			if (requestId === leaderboardRequestId) loading = false;
		}
	}

	function handlePeriodChange(e: Event) {
		const target = e.target as HTMLSelectElement;
		goto(`${toAppPath('/leaderboards')}?period=${target.value}`, {
			keepFocus: true,
			noScroll: true
		});
	}

	function getMedal(rank: number): string {
		if (rank === 1) return '🥇';
		if (rank === 2) return '🥈';
		if (rank === 3) return '🥉';
		return `#${rank}`;
	}

	function formatEmail(email: string): string {
		const [name] = email.split('@');
		return name;
	}

	$effect(() => {
		const accessToken = data.session?.access_token;
		const hasUser = !!data.user;
		void loadLeaderboard(accessToken, hasUser, period);
	});
</script>

<svelte:head>
	<title>Leaderboards | Valdrix</title>
</svelte:head>

<div class="space-y-8">
	<!-- Page Header -->
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold mb-1">🏆 Savings Leaderboard</h1>
			<p class="text-ink-400 text-sm">Who saved the most? Compete with your team!</p>
		</div>

		{#if data.user}
			<select
				class="period-select"
				value={period}
				onchange={handlePeriodChange}
				aria-label="Select leaderboard period"
			>
				<option value="7d">Last 7 Days</option>
				<option value="30d">Last 30 Days</option>
				<option value="90d">Last 90 Days</option>
				<option value="all">All Time</option>
			</select>
		{/if}
	</div>

	<AuthGate authenticated={!!data.user} action="view leaderboards">
		{#if loading}
			<div class="card">
				<div class="skeleton h-8 w-48 mb-4"></div>
				{#each [1, 2, 3] as i (i)}
					<div class="skeleton h-16 w-full mb-2"></div>
				{/each}
			</div>
		{:else if error}
			<div class="card border-danger-500/50 bg-danger-500/10">
				<p class="text-danger-400">{error}</p>
			</div>
		{:else}
			<!-- Total Team Savings Card -->
			<div
				class="card card-stat stagger-enter bg-gradient-to-r from-accent-500/20 to-success-500/20"
			>
				<div class="text-center">
					<p class="text-sm text-ink-400 mb-1">{leaderboard.period}</p>
					<p class="text-4xl font-bold text-success-400">
						${leaderboard.total_team_savings.toLocaleString(undefined, {
							minimumFractionDigits: 2,
							maximumFractionDigits: 2
						})}
					</p>
					<p class="text-ink-400 mt-1">Total Team Savings</p>
				</div>
			</div>

			<!-- Leaderboard -->
			{#if leaderboard.entries.length === 0}
				<div class="card text-center py-12">
					<span class="text-5xl mb-4 block">🚀</span>
					<h3 class="text-xl font-semibold mb-2">No savings yet!</h3>
					<p class="text-ink-400">
						Start approving remediation actions to see your team on the leaderboard.
					</p>
					<p class="text-ink-500 text-sm mt-2">
						Tip: Check the Dashboard for zombie resources to clean up.
					</p>
				</div>
			{:else}
				<div class="card stagger-enter" style="animation-delay: 50ms;">
					<h2 class="text-lg font-semibold mb-5">Top Savers</h2>

					<div class="leaderboard-list">
						{#each leaderboard.entries as entry, i (entry.user_email)}
							<div
								class="leaderboard-entry"
								class:top-3={entry.rank <= 3}
								style="animation-delay: {i * 50}ms;"
							>
								<div class="rank">
									<span class="medal">{getMedal(entry.rank)}</span>
								</div>

								<div class="user-info">
									<span class="username">{formatEmail(entry.user_email)}</span>
									<span class="remediation-count">{entry.remediation_count} actions</span>
								</div>

								<div class="savings">
									<span class="savings-amount"
										>${entry.savings_usd.toLocaleString(undefined, {
											minimumFractionDigits: 2,
											maximumFractionDigits: 2
										})}</span
									>
									<span class="savings-label">saved</span>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}

			<!-- Encouragement Section -->
			<div class="card stagger-enter text-center py-8" style="animation-delay: 100ms;">
				<h3 class="text-lg font-semibold mb-2">💡 Pro Tip</h3>
				<p class="text-ink-400">
					Approve zombie cleanup recommendations to climb the leaderboard and save your company
					money!
				</p>
			</div>
		{/if}
	</AuthGate>
</div>

<style>
	.text-ink-400 {
		color: var(--color-ink-400);
	}
	.text-ink-500 {
		color: var(--color-ink-500);
	}
	.text-success-400 {
		color: var(--color-success-400);
	}
	.text-danger-400 {
		color: var(--color-danger-400);
	}
	.bg-danger-500\/10 {
		background-color: rgb(244 63 94 / 0.1);
	}
	.border-danger-500\/50 {
		border-color: rgb(244 63 94 / 0.5);
	}

	.period-select {
		padding: 0.5rem 1rem;
		border: 1px solid var(--color-ink-700);
		border-radius: 0.5rem;
		background: var(--color-ink-900);
		color: white;
		cursor: pointer;
	}

	.leaderboard-list {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.leaderboard-entry {
		display: flex;
		align-items: center;
		gap: 1rem;
		padding: 1rem;
		background: var(--color-ink-900);
		border-radius: 0.75rem;
		animation: slideIn 0.3s ease-out forwards;
		opacity: 0;
		transform: translateX(-20px);
	}

	@keyframes slideIn {
		to {
			opacity: 1;
			transform: translateX(0);
		}
	}

	.leaderboard-entry.top-3 {
		background: linear-gradient(135deg, var(--color-ink-800), var(--color-ink-900));
		border: 1px solid var(--color-accent-500);
	}

	.rank {
		width: 3rem;
		text-align: center;
	}

	.medal {
		font-size: 1.5rem;
	}

	.user-info {
		flex: 1;
		display: flex;
		flex-direction: column;
	}

	.username {
		font-weight: 600;
		font-size: 1rem;
	}

	.remediation-count {
		font-size: 0.75rem;
		color: var(--color-ink-400);
	}

	.savings {
		text-align: right;
		display: flex;
		flex-direction: column;
	}

	.savings-amount {
		font-weight: 700;
		font-size: 1.125rem;
		color: var(--color-success-400);
	}

	.savings-label {
		font-size: 0.75rem;
		color: var(--color-ink-400);
	}

	.bg-gradient-to-r {
		background: linear-gradient(to right, rgba(99, 102, 241, 0.2), rgba(16, 185, 129, 0.2));
	}
</style>
