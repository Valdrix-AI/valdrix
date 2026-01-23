<!--
  Login Page - Premium SaaS Design
  
  Features:
  - Clean centered card layout
  - Smooth form interactions
  - Motion-enhanced transitions
-->

<script lang="ts">
	import { createSupabaseBrowserClient } from '$lib/supabase';
	import { goto, invalidateAll } from '$app/navigation';
	import { base } from '$app/paths';

	let email = $state('');
	let password = $state('');
	let loading = $state(false);
	let error = $state('');
	let success = $state('');
	let mode: 'login' | 'signup' = $state('login');

	const supabase = createSupabaseBrowserClient();

	async function handleSubmit() {
		loading = true;
		error = '';
		success = '';

		try {
			if (mode === 'login') {
				const { error: authError } = await supabase.auth.signInWithPassword({
					email,
					password
				});

				if (authError) throw authError;

				// Invalidate all load functions to refresh user data, then navigate
				await invalidateAll();
				await goto(`${base}/`);
			} else {
				const { error: authError } = await supabase.auth.signUp({
					email,
					password
				});

				if (authError) throw authError;
				success = 'Check your email for the confirmation link.';
			}
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			loading = false;
		}
	}
</script>

<svelte:head>
	<title>{mode === 'login' ? 'Sign In' : 'Create Account'} | Valdrix</title>
</svelte:head>

<div class="min-h-[85vh] flex items-center justify-center px-4">
	<div class="w-full max-w-sm">
		<!-- Card -->
		<div class="card stagger-enter">
			<!-- Header -->
			<div class="text-center mb-6">
				<span class="text-4xl mb-3 block">☁️</span>
				<h1 class="text-xl font-semibold">
					{mode === 'login' ? 'Welcome back' : 'Create your account'}
				</h1>
				<p class="text-ink-400 text-sm mt-1">
					{mode === 'login' ? 'Sign in to continue' : 'Start your free trial'}
				</p>
			</div>

			{#if error}
				<div
					role="alert"
					class="mb-4 p-3 rounded-lg bg-danger-500/10 border border-danger-500/30 text-danger-400 text-sm"
				>
					{error}
				</div>
			{/if}

			{#if success}
				<div
					role="status"
					class="mb-4 p-3 rounded-lg bg-success-500/10 border border-success-500/30 text-success-400 text-sm"
				>
					{success}
				</div>
			{/if}

			<!-- Form -->
			<form onsubmit={handleSubmit} class="space-y-4">
				<div>
					<label for="email" class="label">Email</label>
					<input
						id="email"
						type="email"
						bind:value={email}
						required
						class="input"
						placeholder="you@company.com"
						aria-label="Email address"
					/>
				</div>

				<div>
					<label for="password" class="label">Password</label>
					<input
						id="password"
						type="password"
						bind:value={password}
						required
						minlength="6"
						class="input"
						placeholder="••••••••"
						aria-label="Password"
					/>
				</div>

				<button
					type="submit"
					disabled={loading}
					class="btn btn-primary w-full py-2.5"
					aria-label={mode === 'login' ? 'Sign in' : 'Create account'}
				>
					{#if loading}
						<span class="spinner" aria-hidden="true"></span>
						<span>Please wait...</span>
					{:else}
						{mode === 'login' ? 'Sign In' : 'Create Account'}
					{/if}
				</button>
			</form>

			<!-- Toggle Mode -->
			<p class="mt-6 text-center text-sm text-ink-400">
				{#if mode === 'login'}
					Don't have an account?
					<button
						type="button"
						onclick={() => (mode = 'signup')}
						class="text-accent-400 hover:underline font-medium"
					>
						Sign up
					</button>
				{:else}
					Already have an account?
					<button
						type="button"
						onclick={() => (mode = 'login')}
						class="text-accent-400 hover:underline font-medium"
					>
						Sign in
					</button>
				{/if}
			</p>
		</div>

		<!-- Footer -->
		<p class="text-center text-xs text-ink-500 mt-6 stagger-enter" style="animation-delay: 100ms;">
			By continuing, you agree to our Terms and Privacy Policy.
		</p>
	</div>
</div>

<style>
	.text-ink-400 {
		color: var(--color-ink-400);
	}
	.text-ink-500 {
		color: var(--color-ink-500);
	}
	.text-accent-400 {
		color: var(--color-accent-400);
	}
	.text-danger-400 {
		color: var(--color-danger-400);
	}
	.text-success-400 {
		color: var(--color-success-400);
	}
	.bg-danger-500\/10 {
		background-color: rgb(244 63 94 / 0.1);
	}
	.bg-success-500\/10 {
		background-color: rgb(16 185 129 / 0.1);
	}
	.border-danger-500\/30 {
		border-color: rgb(244 63 94 / 0.3);
	}
	.border-success-500\/30 {
		border-color: rgb(16 185 129 / 0.3);
	}
</style>
