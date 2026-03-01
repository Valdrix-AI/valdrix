<!--
  Login Page - Premium SaaS Design
  
  Features:
  - Clean centered card layout
  - Smooth form interactions
  - Motion-enhanced transitions
-->

<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { createSupabaseBrowserClient } from '$lib/supabase';
	import { getTurnstileToken } from '$lib/security/turnstile';
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/stores';
	import { base } from '$app/paths';
	import { edgeApiPath } from '$lib/edgeProxy';
	import {
		buildAuthCallbackPath,
		buildPostAuthRedirectPath,
		describePublicIntent,
		describePublicPersona,
		parsePublicAuthContext,
		type PublicAuthContext
	} from '$lib/auth/publicAuthIntent';
	import { emitLandingTelemetry } from '$lib/landing/landingTelemetry';

	let email = $state('');
	let password = $state('');
	let loading = $state(false);
	let ssoLoading = $state(false);
	let magicLinkLoading = $state(false);
	let error = $state('');
	let success = $state('');
	let authContext = $derived<PublicAuthContext>(parsePublicAuthContext($page.url));
	let mode: 'login' | 'signup' = $state(parsePublicAuthContext($page.url).mode);
	let intentLabel = $derived<string | null>(describePublicIntent(authContext.intent));
	let personaLabel = $derived<string | null>(describePublicPersona(authContext.persona));

	const supabase = createSupabaseBrowserClient();

	$effect(() => {
		mode = authContext.mode;
		const oauthError = $page.url.searchParams.get('error');
		if (oauthError) {
			error = oauthError;
		}
	});

	type SsoDiscoveryResponse = {
		available: boolean;
		mode: 'domain' | 'provider_id' | null;
		domain: string | null;
		provider_id: string | null;
		reason: string | null;
	};

	function normalizeDomain(value: string): string {
		const normalized = value.trim().toLowerCase();
		if (!normalized.includes('@')) return '';
		return (
			normalized
				.split('@')[1]
				?.trim()
				.toLowerCase()
				.replace(/^\.+|\.+$/g, '') ?? ''
		);
	}

	function callbackRedirectTo(): string {
		if (typeof window === 'undefined') {
			return `${base}/auth/callback`;
		}
		const callbackPath = buildAuthCallbackPath(authContext);
		return `${window.location.origin}${base}${callbackPath}`;
	}

	function emitAuthEvent(action: string, value?: string): void {
		emitLandingTelemetry(action, 'auth', value, {
			persona: authContext.persona,
			funnelStage: 'signup_intent',
			pagePath: $page.url.pathname,
			experiment: undefined,
			utm: authContext.utm
		});
	}

	async function handleSubmit() {
		loading = true;
		error = '';
		success = '';

		try {
			if (mode === 'login') {
				emitAuthEvent('auth_password_submit', 'login');
				const { error: authError } = await supabase.auth.signInWithPassword({
					email,
					password
				});

				if (authError) throw authError;

				// Invalidate all load functions to refresh user data, then navigate
				await invalidateAll();
				const nextPath = buildPostAuthRedirectPath(authContext);
				await goto(`${base}${nextPath}`);
			} else {
				emitAuthEvent('auth_password_submit', 'signup');
				const { error: authError } = await supabase.auth.signUp({
					email,
					password,
					options: { emailRedirectTo: callbackRedirectTo() }
				});

				if (authError) throw authError;
				success =
					'Check your email for the confirmation link. Your setup flow will continue after verification.';
			}
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			loading = false;
		}
	}

	async function handleMagicLinkSubmit() {
		magicLinkLoading = true;
		error = '';
		success = '';
		try {
			const normalizedEmail = email.trim().toLowerCase();
			if (!normalizedEmail) {
				throw new Error('Enter your work email to continue.');
			}
			emitAuthEvent('auth_magic_link_submit', mode);
			const { error: authError } = await supabase.auth.signInWithOtp({
				email: normalizedEmail,
				options: {
					emailRedirectTo: callbackRedirectTo(),
					shouldCreateUser: mode === 'signup'
				}
			});
			if (authError) throw authError;
			success = 'Secure sign-in link sent. Check your inbox to continue.';
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			magicLinkLoading = false;
		}
	}

	async function handleSsoSubmit() {
		ssoLoading = true;
		error = '';
		success = '';
		try {
			if (!email.trim()) {
				throw new Error('Enter your work email to continue with SSO.');
			}

			const turnstileToken = await getTurnstileToken('sso_discovery');
			const res = await fetch(edgeApiPath('/public/sso/discovery'), {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					...(turnstileToken ? { 'X-Turnstile-Token': turnstileToken } : {})
				},
				body: JSON.stringify({ email: email.trim().toLowerCase() })
			});
			if (!res.ok) {
				throw new Error('Unable to discover SSO configuration. Try again.');
			}
			const discovery = (await res.json()) as SsoDiscoveryResponse;
			if (!discovery.available || !discovery.mode) {
				throw new Error(
					discovery.reason === 'sso_not_configured_for_domain'
						? 'No SSO configuration was found for your domain.'
						: 'SSO is not ready for this domain. Contact your admin.'
				);
			}

			const redirectTo = callbackRedirectTo();
			emitAuthEvent('auth_sso_submit', discovery.mode);
			if (discovery.mode === 'provider_id') {
				if (!discovery.provider_id) {
					throw new Error('SSO provider configuration is incomplete.');
				}
				const { data, error: authError } = await supabase.auth.signInWithSSO({
					providerId: discovery.provider_id,
					options: { redirectTo }
				});
				if (authError) throw authError;
				if (data?.url) window.location.assign(data.url);
				return;
			}

			const domain = discovery.domain || normalizeDomain(email);
			if (!domain) {
				throw new Error('Unable to determine your SSO domain.');
			}
			const { data, error: authError } = await supabase.auth.signInWithSSO({
				domain,
				options: { redirectTo }
			});
			if (authError) throw authError;
			if (data?.url) window.location.assign(data.url);
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			ssoLoading = false;
		}
	}
</script>

<svelte:head>
	<title>{mode === 'login' ? 'Sign In' : 'Create Account'} | Valdrics</title>
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
				<p class="text-ink-300 text-sm mt-1">
					{mode === 'login'
						? 'Sign in to continue with controlled execution'
						: 'Start free and activate governed economic workflows'}
				</p>
				{#if intentLabel || personaLabel}
					<p class="text-ink-200 text-xs mt-2">
						Starting with
						{#if intentLabel}
							<strong>{intentLabel}</strong>
						{/if}
						{#if intentLabel && personaLabel}
							for
						{/if}
						{#if personaLabel}
							<strong>{personaLabel}</strong>
						{/if}
					</p>
				{/if}
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
			<form
				onsubmit={(event) => {
					event.preventDefault();
					void handleSubmit();
				}}
				class="space-y-4"
			>
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

			<div class="my-4 flex items-center gap-3 text-xs text-ink-300">
				<div class="h-px flex-1 bg-ink-800/70"></div>
				<span>or</span>
				<div class="h-px flex-1 bg-ink-800/70"></div>
			</div>

			<button
				type="button"
				class="btn btn-secondary w-full py-2.5"
				disabled={magicLinkLoading}
				onclick={() => void handleMagicLinkSubmit()}
				aria-label={mode === 'login' ? 'Send secure sign-in link' : 'Send secure signup link'}
			>
				{#if magicLinkLoading}
					<span class="spinner" aria-hidden="true"></span>
					<span>Sending secure link...</span>
				{:else}
					{mode === 'login' ? 'Email me a secure sign-in link' : 'Email me a secure signup link'}
				{/if}
			</button>

			<button
				type="button"
				class="btn btn-secondary w-full py-2.5"
				disabled={ssoLoading}
				onclick={() => void handleSsoSubmit()}
				aria-label="Continue with SSO"
			>
				{#if ssoLoading}
					<span class="spinner" aria-hidden="true"></span>
					<span>Redirecting to IdP...</span>
				{:else}
					Continue with SSO
				{/if}
			</button>

			<!-- Toggle Mode -->
			<p class="mt-6 text-center text-sm text-ink-300">
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
		<p class="text-center text-xs text-ink-200 mt-6 stagger-enter" style="animation-delay: 100ms;">
			By continuing, you agree to our
			<a href={`${base}/terms`} class="text-ink-100 underline hover:text-accent-400">Terms</a>
			and
			<a href={`${base}/privacy`} class="text-ink-100 underline hover:text-accent-400">
				Privacy Policy
			</a>.
		</p>
	</div>
</div>

<style>
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
