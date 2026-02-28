<!--
  Settings Page - Notification Preferences
  
  Features:
  - Slack notification toggle
  - Digest schedule (daily/weekly/disabled)
  - Alert preferences
  - Test notification button
-->

<script lang="ts">
	/* eslint-disable svelte/no-navigation-without-resolve */
	import { onMount } from 'svelte';
	import { base } from '$app/paths';
	import { invalidateAll } from '$app/navigation';
	import { api } from '$lib/api';
	import { edgeApiPath } from '$lib/edgeProxy';
	import AuthGate from '$lib/components/AuthGate.svelte';
	import EnforcementOpsCard from '$lib/components/EnforcementOpsCard.svelte';
	import EnforcementSettingsCard from '$lib/components/EnforcementSettingsCard.svelte';
	import IdentitySettingsCard from '$lib/components/IdentitySettingsCard.svelte';
	import { TimeoutError } from '$lib/fetchWithTimeout';
	import { z } from 'zod';

	let { data } = $props();
	const SETTINGS_REQUEST_TIMEOUT_MS = 8000;

	let loading = $state(false);
	let saving = $state(false);
	let testing = $state(false);
	let testingJira = $state(false);
	let testingTeams = $state(false);
	let testingWorkflow = $state(false);
	let diagnosticsLoading = $state(false);
	let error = $state('');
	let success = $state('');

	type PolicyChannelDiagnostics = {
		enabled_for_policy: boolean;
		enabled_in_notifications: boolean;
		ready: boolean;
		reasons: string[];
	};

	type PolicyDiagnostics = {
		tier: string;
		has_activeops_settings: boolean;
		has_notification_settings: boolean;
		policy_enabled: boolean;
		slack: PolicyChannelDiagnostics & {
			has_bot_token: boolean;
			has_default_channel: boolean;
			has_channel_override: boolean;
			selected_channel?: string | null;
			channel_source: string;
		};
		jira: PolicyChannelDiagnostics & {
			feature_allowed_by_tier: boolean;
			has_base_url: boolean;
			has_email: boolean;
			has_project_key: boolean;
			has_api_token: boolean;
			issue_type: string;
		};
	};

	type SafetyStatus = {
		circuit_state: string;
		failure_count: number;
		daily_savings_used: number;
		daily_savings_limit: number;
		last_failure_at: string | null;
		can_execute: boolean;
	};

	let policyDiagnostics = $state<PolicyDiagnostics | null>(null);
	let safetyStatus = $state<SafetyStatus | null>(null);
	let loadingSafety = $state(true);
	let resettingSafety = $state(false);
	let safetyError = $state('');
	let safetySuccess = $state('');

	async function getHeaders() {
		return {
			Authorization: `Bearer ${data.session?.access_token}`
		};
	}

	async function getWithTimeout(url: string, headers?: Record<string, string>) {
		return api.get(url, {
			...(headers ? { headers } : {}),
			timeoutMs: SETTINGS_REQUEST_TIMEOUT_MS
		});
	}

	async function loadSettings() {
		try {
			const headers = await getHeaders();
			const res = await getWithTimeout(edgeApiPath('/settings/notifications'), headers);
			if (res.ok) {
				const loaded = await res.json();
				settings = {
					...settings,
					...loaded,
					slack_channel_override: loaded.slack_channel_override ?? '',
					jira_base_url: loaded.jira_base_url ?? '',
					jira_email: loaded.jira_email ?? '',
					jira_project_key: loaded.jira_project_key ?? '',
					jira_issue_type: loaded.jira_issue_type ?? 'Task',
					jira_api_token: '',
					clear_jira_api_token: false,
					teams_enabled: loaded.teams_enabled ?? false,
					teams_webhook_url: loaded.teams_webhook_url ?? '',
					clear_teams_webhook_url: false,
					has_teams_webhook_url: loaded.has_teams_webhook_url ?? false,
					workflow_github_enabled: loaded.workflow_github_enabled ?? false,
					workflow_github_owner: loaded.workflow_github_owner ?? '',
					workflow_github_repo: loaded.workflow_github_repo ?? '',
					workflow_github_workflow_id: loaded.workflow_github_workflow_id ?? '',
					workflow_github_ref: loaded.workflow_github_ref ?? 'main',
					workflow_github_token: '',
					clear_workflow_github_token: false,
					workflow_has_github_token: loaded.workflow_has_github_token ?? false,
					workflow_gitlab_enabled: loaded.workflow_gitlab_enabled ?? false,
					workflow_gitlab_base_url: loaded.workflow_gitlab_base_url ?? 'https://gitlab.com',
					workflow_gitlab_project_id: loaded.workflow_gitlab_project_id ?? '',
					workflow_gitlab_ref: loaded.workflow_gitlab_ref ?? 'main',
					workflow_gitlab_trigger_token: '',
					clear_workflow_gitlab_trigger_token: false,
					workflow_has_gitlab_trigger_token: loaded.workflow_has_gitlab_trigger_token ?? false,
					workflow_webhook_enabled: loaded.workflow_webhook_enabled ?? false,
					workflow_webhook_url: loaded.workflow_webhook_url ?? '',
					workflow_webhook_bearer_token: '',
					clear_workflow_webhook_bearer_token: false,
					workflow_has_webhook_bearer_token: loaded.workflow_has_webhook_bearer_token ?? false
				};
			}
		} catch (e) {
			console.error('Failed to load settings:', e);
			error =
				e instanceof TimeoutError
					? 'Settings request timed out. Defaults are shown until data refresh succeeds.'
					: 'Failed to connect to backend service.';
		}
	}

	let persona = $derived(String(data.profile?.persona ?? 'engineering'));
	let savingPersona = $state(false);

	async function savePersona() {
		savingPersona = true;
		error = '';
		success = '';
		try {
			const headers = await getHeaders();
			const res = await api.put(edgeApiPath('/settings/profile'), { persona }, { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to save persona.');
			}
			success = `Persona updated: ${persona}.`;
			setTimeout(() => (success = ''), 3000);
			await invalidateAll();
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to save persona.';
		} finally {
			savingPersona = false;
		}
	}

	function formatCircuitState(state: string): string {
		const normalized = state.replaceAll('_', ' ');
		return normalized.charAt(0).toUpperCase() + normalized.slice(1);
	}

	function safetyUsagePercent(status: SafetyStatus | null): number {
		if (!status || status.daily_savings_limit <= 0) return 0;
		return Math.min((status.daily_savings_used / status.daily_savings_limit) * 100, 100);
	}

	function formatSafetyDate(value: string | null): string {
		if (!value) return 'None';
		const parsed = new Date(value);
		if (Number.isNaN(parsed.getTime())) return value;
		return parsed.toLocaleString();
	}

	const NotificationSettingsSchema = z.object({
		slack_enabled: z.boolean(),
		slack_channel_override: z.string().max(50).optional(),
		jira_enabled: z.boolean(),
		jira_base_url: z.string().max(255).optional(),
		jira_email: z.string().email().optional(),
		jira_project_key: z.string().max(32).optional(),
		jira_issue_type: z.string().max(64).optional(),
		jira_api_token: z.string().max(1024).optional(),
		clear_jira_api_token: z.boolean().optional(),
		teams_enabled: z.boolean(),
		teams_webhook_url: z.string().max(1024).optional(),
		clear_teams_webhook_url: z.boolean().optional(),
		workflow_github_enabled: z.boolean(),
		workflow_github_owner: z.string().max(100).optional(),
		workflow_github_repo: z.string().max(100).optional(),
		workflow_github_workflow_id: z.string().max(200).optional(),
		workflow_github_ref: z.string().max(100),
		workflow_github_token: z.string().max(1024).optional(),
		clear_workflow_github_token: z.boolean().optional(),
		workflow_gitlab_enabled: z.boolean(),
		workflow_gitlab_base_url: z.string().max(255),
		workflow_gitlab_project_id: z.string().max(128).optional(),
		workflow_gitlab_ref: z.string().max(100),
		workflow_gitlab_trigger_token: z.string().max(1024).optional(),
		clear_workflow_gitlab_trigger_token: z.boolean().optional(),
		workflow_webhook_enabled: z.boolean(),
		workflow_webhook_url: z.string().max(500).optional(),
		workflow_webhook_bearer_token: z.string().max(1024).optional(),
		clear_workflow_webhook_bearer_token: z.boolean().optional(),
		digest_schedule: z.enum(['daily', 'weekly', 'disabled']),
		digest_hour: z.number().min(0).max(23),
		digest_minute: z.number().min(0).max(59),
		alert_on_budget_warning: z.boolean(),
		alert_on_budget_exceeded: z.boolean(),
		alert_on_zombie_detected: z.boolean()
	});

	async function saveSettings() {
		saving = true;
		error = '';
		success = '';
		try {
			const payload = {
				...settings,
				slack_channel_override: settings.slack_channel_override || undefined,
				jira_base_url: settings.jira_base_url || undefined,
				jira_email: settings.jira_email || undefined,
				jira_project_key: settings.jira_project_key || undefined,
				jira_issue_type: settings.jira_issue_type || undefined,
				jira_api_token: settings.jira_api_token || undefined,
				teams_webhook_url: settings.teams_webhook_url || undefined,
				workflow_github_owner: settings.workflow_github_owner || undefined,
				workflow_github_repo: settings.workflow_github_repo || undefined,
				workflow_github_workflow_id: settings.workflow_github_workflow_id || undefined,
				workflow_github_ref: settings.workflow_github_ref || 'main',
				workflow_github_token: settings.workflow_github_token || undefined,
				workflow_gitlab_base_url: settings.workflow_gitlab_base_url || 'https://gitlab.com',
				workflow_gitlab_project_id: settings.workflow_gitlab_project_id || undefined,
				workflow_gitlab_ref: settings.workflow_gitlab_ref || 'main',
				workflow_gitlab_trigger_token: settings.workflow_gitlab_trigger_token || undefined,
				workflow_webhook_url: settings.workflow_webhook_url || undefined,
				workflow_webhook_bearer_token: settings.workflow_webhook_bearer_token || undefined
			};
			// FE-H2: Input Validation
			const validated = NotificationSettingsSchema.parse(payload);

			const headers = await getHeaders();
			const res = await api.put(edgeApiPath('/settings/notifications'), validated, { headers });
			if (!res.ok) {
				const data = await res.json();
				throw new Error(data.detail || 'Failed to save settings');
			}
			if (validated.jira_api_token) {
				settings.has_jira_api_token = true;
			}
			if (validated.clear_jira_api_token) {
				settings.has_jira_api_token = false;
			}
			settings.jira_api_token = '';
			settings.clear_jira_api_token = false;
			if (validated.teams_webhook_url) {
				settings.has_teams_webhook_url = true;
			}
			if (validated.clear_teams_webhook_url) {
				settings.has_teams_webhook_url = false;
			}
			settings.teams_webhook_url = '';
			settings.clear_teams_webhook_url = false;
			if (validated.workflow_github_token) {
				settings.workflow_has_github_token = true;
			}
			if (validated.clear_workflow_github_token) {
				settings.workflow_has_github_token = false;
			}
			settings.workflow_github_token = '';
			settings.clear_workflow_github_token = false;
			if (validated.workflow_gitlab_trigger_token) {
				settings.workflow_has_gitlab_trigger_token = true;
			}
			if (validated.clear_workflow_gitlab_trigger_token) {
				settings.workflow_has_gitlab_trigger_token = false;
			}
			settings.workflow_gitlab_trigger_token = '';
			settings.clear_workflow_gitlab_trigger_token = false;
			if (validated.workflow_webhook_bearer_token) {
				settings.workflow_has_webhook_bearer_token = true;
			}
			if (validated.clear_workflow_webhook_bearer_token) {
				settings.workflow_has_webhook_bearer_token = false;
			}
			settings.workflow_webhook_bearer_token = '';
			settings.clear_workflow_webhook_bearer_token = false;
			success = 'General settings saved!';
			setTimeout(() => (success = ''), 3000);
		} catch (e) {
			if (e instanceof z.ZodError) {
				error = e.issues.map((err: z.ZodIssue) => err.message).join(', ');
			} else {
				const err = e as Error;
				error = err.message;
			}
		} finally {
			saving = false;
		}
	}

	// Settings state
	let settings = $state({
		slack_enabled: true,
		slack_channel_override: '',
		jira_enabled: false,
		jira_base_url: '',
		jira_email: '',
		jira_project_key: '',
		jira_issue_type: 'Task',
		jira_api_token: '',
		clear_jira_api_token: false,
		has_jira_api_token: false,
		teams_enabled: false,
		teams_webhook_url: '',
		clear_teams_webhook_url: false,
		has_teams_webhook_url: false,
		workflow_github_enabled: false,
		workflow_github_owner: '',
		workflow_github_repo: '',
		workflow_github_workflow_id: '',
		workflow_github_ref: 'main',
		workflow_github_token: '',
		clear_workflow_github_token: false,
		workflow_has_github_token: false,
		workflow_gitlab_enabled: false,
		workflow_gitlab_base_url: 'https://gitlab.com',
		workflow_gitlab_project_id: '',
		workflow_gitlab_ref: 'main',
		workflow_gitlab_trigger_token: '',
		clear_workflow_gitlab_trigger_token: false,
		workflow_has_gitlab_trigger_token: false,
		workflow_webhook_enabled: false,
		workflow_webhook_url: '',
		workflow_webhook_bearer_token: '',
		clear_workflow_webhook_bearer_token: false,
		workflow_has_webhook_bearer_token: false,
		digest_schedule: 'daily',
		digest_hour: 9,
		digest_minute: 0,
		alert_on_budget_warning: true,
		alert_on_budget_exceeded: true,
		alert_on_zombie_detected: true
	});

	// LLM Settings state
	let llmSettings = $state({
		monthly_limit_usd: 10.0,
		alert_threshold_percent: 80,
		hard_limit: false,
		preferred_provider: 'groq',
		preferred_model: 'llama-3.3-70b-versatile',
		openai_api_key: '',
		claude_api_key: '',
		google_api_key: '',
		groq_api_key: '',
		has_openai_key: false,
		has_claude_key: false,
		has_google_key: false,
		has_groq_key: false
	});
	let loadingLLM = $state(true);
	let savingLLM = $state(false);

	// ActiveOps (Remediation) settings
	let activeOpsSettings = $state({
		auto_pilot_enabled: false,
		min_confidence_threshold: 0.95,
		policy_enabled: true,
		policy_block_production_destructive: true,
		policy_require_gpu_override: true,
		policy_low_confidence_warn_threshold: 0.9,
		policy_violation_notify_slack: true,
		policy_violation_notify_jira: false,
		policy_escalation_required_role: 'owner',
		license_auto_reclaim_enabled: false,
		license_inactive_threshold_days: 30,
		license_reclaim_grace_period_days: 3,
		license_downgrade_recommendations_enabled: true
	});
	let loadingActiveOps = $state(true);
	let savingActiveOps = $state(false);

	let providerModels = $state({
		groq: [],
		openai: [],
		anthropic: [],
		google: []
	});

	async function testSlack() {
		testing = true;
		error = '';

		try {
			const headers = await getHeaders();
			const res = await api.post(
				edgeApiPath('/settings/notifications/test-slack'),
				{},
				{ headers }
			);

			if (!res.ok) {
				const data = await res.json();
				throw new Error(data.detail || 'Failed to send test notification');
			}

			success = 'Test notification sent to Slack!';
			setTimeout(() => (success = ''), 3000);
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			testing = false;
		}
	}

	async function testJira() {
		testingJira = true;
		error = '';

		try {
			const headers = await getHeaders();
			const res = await api.post(edgeApiPath('/settings/notifications/test-jira'), {}, { headers });

			if (!res.ok) {
				const data = await res.json();
				throw new Error(data.detail || 'Failed to send Jira test issue');
			}

			success = 'Test issue created in Jira!';
			setTimeout(() => (success = ''), 3000);
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			testingJira = false;
		}
	}

	async function testTeams() {
		testingTeams = true;
		error = '';

		try {
			const headers = await getHeaders();
			const res = await api.post(
				edgeApiPath('/settings/notifications/test-teams'),
				{},
				{ headers }
			);

			if (!res.ok) {
				const data = await res.json();
				throw new Error(data.detail || 'Failed to send Teams test notification');
			}

			success = 'Test notification sent to Teams!';
			setTimeout(() => (success = ''), 3000);
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			testingTeams = false;
		}
	}

	async function testWorkflowDispatch() {
		testingWorkflow = true;
		error = '';

		try {
			const headers = await getHeaders();
			const res = await api.post(
				edgeApiPath('/settings/notifications/test-workflow'),
				{},
				{ headers }
			);

			if (!res.ok) {
				const data = await res.json();
				throw new Error(data.detail || 'Failed to dispatch workflow test event');
			}

			success = 'Workflow test event dispatched!';
			setTimeout(() => (success = ''), 3000);
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			testingWorkflow = false;
		}
	}

	async function runPolicyDiagnostics() {
		diagnosticsLoading = true;
		error = '';
		try {
			const headers = await getHeaders();
			const res = await api.get(edgeApiPath('/settings/notifications/policy-diagnostics'), {
				headers
			});
			if (!res.ok) {
				const data = await res.json();
				throw new Error(data.detail || 'Failed to run policy diagnostics');
			}
			policyDiagnostics = await res.json();
			success = 'Policy diagnostics refreshed.';
			setTimeout(() => (success = ''), 2000);
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			diagnosticsLoading = false;
		}
	}

	// Carbon settings state
	let carbonSettings = $state({
		carbon_budget_kg: 100,
		alert_threshold_percent: 80,
		default_region: 'us-east-1',
		email_enabled: false,
		email_recipients: ''
	});
	let loadingCarbon = $state(true);
	let savingCarbon = $state(false);

	async function loadCarbonSettings() {
		try {
			const headers = await getHeaders();
			const res = await getWithTimeout(edgeApiPath('/settings/carbon'), headers);

			if (res.ok) {
				carbonSettings = await res.json();
			}
		} catch (error_un) {
			console.error('Failed to load carbon settings:', error_un);
		} finally {
			loadingCarbon = false;
		}
	}

	const CarbonSettingsSchema = z.object({
		carbon_budget_kg: z.number().min(1).max(100000),
		alert_threshold_percent: z.number().min(1).max(100),
		default_region: z.string().min(2),
		email_enabled: z.boolean(),
		email_recipients: z.string().optional()
	});

	async function saveCarbonSettings() {
		savingCarbon = true;
		error = '';
		success = '';

		try {
			CarbonSettingsSchema.parse(carbonSettings);

			const headers = await getHeaders();
			const res = await api.put(edgeApiPath('/settings/carbon'), carbonSettings, { headers });

			if (!res.ok) {
				const data = await res.json();
				throw new Error(data.detail || 'Failed to save carbon settings');
			}

			success = 'Carbon settings saved successfully!';
			setTimeout(() => (success = ''), 3000);
		} catch (e) {
			if (e instanceof z.ZodError) {
				error = e.issues
					.map((err: z.ZodIssue) => `${err.path.join('.')}: ${err.message}`)
					.join(', ');
			} else {
				const err = e as Error;
				error = err.message;
			}
		} finally {
			savingCarbon = false;
		}
	}

	async function loadModels() {
		try {
			const res = await getWithTimeout(edgeApiPath('/settings/llm/models'));
			if (res.ok) {
				providerModels = await res.json();
			}
		} catch (e) {
			console.error('Failed to load LLM models:', e);
		}
	}

	async function loadLLMSettings() {
		try {
			const headers = await getHeaders();
			const res = await getWithTimeout(edgeApiPath('/settings/llm'), headers);

			if (res.ok) {
				llmSettings = await res.json();
			}
		} catch (error_un) {
			console.error('Failed to load LLM settings:', error_un);
		} finally {
			loadingLLM = false;
		}
	}

	const LLMSettingsSchema = z.object({
		monthly_limit_usd: z.number().min(0).max(10000),
		alert_threshold_percent: z.number().min(0).max(100),
		hard_limit: z.boolean(),
		preferred_provider: z.string(),
		preferred_model: z.string(),
		openai_api_key: z.string().min(20).optional().or(z.literal('')),
		claude_api_key: z.string().min(20).optional().or(z.literal('')),
		google_api_key: z.string().min(20).optional().or(z.literal('')),
		groq_api_key: z.string().min(20).optional().or(z.literal(''))
	});

	async function saveLLMSettings() {
		savingLLM = true;
		error = '';
		success = '';

		try {
			// FE-H2: Input Validation
			LLMSettingsSchema.parse(llmSettings);

			const headers = await getHeaders();
			const res = await api.put(edgeApiPath('/settings/llm'), llmSettings, { headers });

			if (!res.ok) {
				const data = await res.json();
				throw new Error(data.detail || 'Failed to save LLM settings');
			}

			const updated = await res.json();
			// SEC-04: Clear raw keys from state after successful save (FE-H4)
			llmSettings.openai_api_key = '';
			llmSettings.claude_api_key = '';
			llmSettings.google_api_key = '';
			llmSettings.groq_api_key = '';

			// Update has_key flags from response
			llmSettings.has_openai_key = updated.has_openai_key;
			llmSettings.has_claude_key = updated.has_claude_key;
			llmSettings.has_google_key = updated.has_google_key;
			llmSettings.has_groq_key = updated.has_groq_key;

			success = 'AI strategy settings saved!';
			setTimeout(() => (success = ''), 3000);
		} catch (e) {
			if (e instanceof z.ZodError) {
				error = e.issues
					.map((err: z.ZodIssue) => `${err.path.join('.')}: ${err.message}`)
					.join(', ');
			} else {
				const err = e as Error;
				error = err.message;
			}
		} finally {
			savingLLM = false;
		}
	}

	async function loadActiveOpsSettings() {
		try {
			const headers = await getHeaders();
			const res = await getWithTimeout(edgeApiPath('/settings/activeops'), headers);

			if (res.ok) {
				activeOpsSettings = await res.json();
			}
		} catch (error_un) {
			console.error('Failed to load ActiveOps settings:', error_un);
		} finally {
			loadingActiveOps = false;
		}
	}

	const ActiveOpsSettingsSchema = z.object({
		auto_pilot_enabled: z.boolean(),
		min_confidence_threshold: z.number().min(0.5).max(1.0),
		policy_enabled: z.boolean(),
		policy_block_production_destructive: z.boolean(),
		policy_require_gpu_override: z.boolean(),
		policy_low_confidence_warn_threshold: z.number().min(0.5).max(1.0),
		policy_violation_notify_slack: z.boolean(),
		policy_violation_notify_jira: z.boolean(),
		policy_escalation_required_role: z.enum(['owner', 'admin']),
		license_auto_reclaim_enabled: z.boolean(),
		license_inactive_threshold_days: z.number().min(7).max(365),
		license_reclaim_grace_period_days: z.number().min(1).max(30),
		license_downgrade_recommendations_enabled: z.boolean()
	});

	async function saveActiveOpsSettings() {
		savingActiveOps = true;
		error = '';
		success = '';

		try {
			ActiveOpsSettingsSchema.parse(activeOpsSettings);

			const headers = await getHeaders();
			const res = await api.put(edgeApiPath('/settings/activeops'), activeOpsSettings, {
				headers
			});

			if (!res.ok) {
				const data = await res.json();
				throw new Error(data.detail || 'Failed to save ActiveOps settings');
			}

			success = 'ActiveOps / Auto-Pilot settings saved!';
			setTimeout(() => (success = ''), 3000);
		} catch (e) {
			if (e instanceof z.ZodError) {
				error = e.issues
					.map((err: z.ZodIssue) => `${err.path.join('.')}: ${err.message}`)
					.join(', ');
			} else {
				const err = e as Error;
				error = err.message;
			}
		} finally {
			savingActiveOps = false;
		}
	}

	async function loadSafetyStatus() {
		loadingSafety = true;
		safetyError = '';
		try {
			const headers = await getHeaders();
			const res = await getWithTimeout(edgeApiPath('/settings/safety'), headers);
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to load safety status');
			}
			safetyStatus = (await res.json()) as SafetyStatus;
		} catch (e) {
			const err = e as Error;
			safetyError = err.message;
		} finally {
			loadingSafety = false;
		}
	}

	async function resetSafetyCircuitBreaker() {
		resettingSafety = true;
		safetyError = '';
		safetySuccess = '';
		try {
			const headers = await getHeaders();
			const res = await api.post(edgeApiPath('/settings/safety/reset'), {}, { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(
					payload.detail ||
						payload.message ||
						(res.status === 403
							? 'Admin role required to reset the circuit breaker.'
							: 'Failed to reset circuit breaker.')
				);
			}
			safetySuccess = 'Circuit breaker reset to closed state.';
			await loadSafetyStatus();
		} catch (e) {
			const err = e as Error;
			safetyError = err.message;
		} finally {
			resettingSafety = false;
		}
	}

	onMount(() => {
		if (data.user) {
			void loadSettings();
			void loadCarbonSettings();
			void loadModels();
			void loadLLMSettings();
			void loadSafetyStatus();
			if (['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)) {
				void loadActiveOpsSettings();
			} else {
				loadingActiveOps = false;
			}
		} else {
			loading = false;
			loadingCarbon = false;
			loadingLLM = false;
			loadingActiveOps = false;
			loadingSafety = false;
		}
	});
</script>

<svelte:head>
	<title>Settings | Valdrics</title>
</svelte:head>

<div class="space-y-8">
	<!-- Page Header -->
	<div>
		<h1 class="text-2xl font-bold mb-1">Preferences</h1>
		<p class="text-ink-400 text-sm">
			Configure your notifications, AI strategy, and GreenOps thresholds.
		</p>
	</div>

	<AuthGate authenticated={!!data.user} action="manage settings">
		{#if loading}
			<div class="card">
				<div class="skeleton h-8 w-48 mb-4"></div>
				<div class="skeleton h-4 w-full mb-2"></div>
				<div class="skeleton h-4 w-3/4"></div>
			</div>
		{:else}
			{#if error}
				<div role="alert" class="card border-danger-500/50 bg-danger-500/10">
					<p class="text-danger-400">{error}</p>
				</div>
			{/if}

			{#if success}
				<div role="status" class="card border-success-500/50 bg-success-500/10">
					<p class="text-success-400">{success}</p>
				</div>
			{/if}

			<!-- Persona Defaults -->
			<div class="card stagger-enter">
				<h2 class="text-lg font-semibold mb-2 flex items-center gap-2">
					<span>🧭</span> Default Persona
				</h2>
				<p class="text-xs text-ink-400 mb-4">
					Choose which workflows Valdrics prioritizes by default. This does not change access
					permissions.
				</p>
				<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
					<div class="form-group">
						<label for="persona">Persona</label>
						<select id="persona" bind:value={persona} class="select" aria-label="Default persona">
							<option value="engineering">Engineering (waste + remediation)</option>
							<option value="finance">Finance (allocation + unit economics)</option>
							<option value="platform">Platform (ops + guardrails)</option>
							<option value="leadership">Leadership (high-level drivers)</option>
						</select>
					</div>
					<div class="flex items-end">
						<button
							type="button"
							class="btn btn-primary w-full"
							onclick={savePersona}
							disabled={savingPersona}
							aria-label="Save persona"
						>
							{savingPersona ? '⏳ Saving...' : '💾 Save Persona'}
						</button>
					</div>
				</div>
			</div>

			<!-- Carbon Budget Settings -->
			<div
				class="card stagger-enter relative"
				class:opacity-60={!['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
				class:pointer-events-none={!['growth', 'pro', 'enterprise'].includes(
					data.subscription?.tier
				)}
			>
				<div class="flex items-center justify-between mb-5">
					<h2 class="text-lg font-semibold flex items-center gap-2">
						<span>🌱</span> Carbon Budget
					</h2>

					{#if !['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
						<span class="badge badge-warning text-xs">Growth Plan Required</span>
					{/if}
				</div>

				{#if !['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
					<div class="absolute inset-0 z-10 flex items-center justify-center bg-transparent">
						<a href={`${base}/billing`} class="btn btn-primary shadow-lg pointer-events-auto">
							Upgrade to Unlock GreenOps
						</a>
					</div>
				{/if}

				{#if loadingCarbon}
					<div class="skeleton h-4 w-48"></div>
				{:else}
					<div class="space-y-4">
						<div class="form-group">
							<label for="carbon_budget">Monthly Carbon Budget (kg CO₂)</label>
							<input
								type="number"
								id="carbon_budget"
								bind:value={carbonSettings.carbon_budget_kg}
								min="0"
								step="10"
								disabled={!['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
								aria-label="Monthly carbon budget in kilograms"
							/>
							<p class="text-xs text-ink-500 mt-1">Set your monthly carbon footprint limit</p>
						</div>

						<div class="form-group">
							<label for="alert_threshold">Alert Threshold (%)</label>
							<input
								type="number"
								id="alert_threshold"
								bind:value={carbonSettings.alert_threshold_percent}
								min="0"
								max="100"
								disabled={!['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
								aria-label="Carbon alert threshold percentage"
							/>
							<p class="text-xs text-ink-500 mt-1">
								Warn when usage reaches this percentage of budget
							</p>
						</div>

						<div class="form-group">
							<label for="default_region">Default AWS Region</label>
							<select
								id="default_region"
								bind:value={carbonSettings.default_region}
								class="select"
								disabled={!['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
								aria-label="Default AWS region for carbon analysis"
							>
								<option value="us-west-2">US West (Oregon) - 21 gCO₂/kWh ⭐</option>
								<option value="eu-north-1">EU (Stockholm) - 28 gCO₂/kWh ⭐</option>
								<option value="ca-central-1">Canada (Central) - 35 gCO₂/kWh ⭐</option>
								<option value="eu-west-1">EU (Ireland) - 316 gCO₂/kWh</option>
								<option value="us-east-1">US East (N. Virginia) - 379 gCO₂/kWh</option>
								<option value="ap-northeast-1">Asia Pacific (Tokyo) - 506 gCO₂/kWh</option>
							</select>
							<p class="text-xs text-ink-500 mt-1">
								Regions marked with ⭐ have lowest carbon intensity
							</p>
						</div>

						<!-- Email Notifications -->
						<div class="form-group">
							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={carbonSettings.email_enabled}
									class="toggle"
									disabled={!['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Enable email notifications for carbon alerts"
								/>
								<span>Enable email notifications for carbon alerts</span>
							</label>
						</div>

						{#if carbonSettings.email_enabled}
							<div class="form-group">
								<label for="email_recipients">Email Recipients</label>
								<input
									type="text"
									id="email_recipients"
									bind:value={carbonSettings.email_recipients}
									placeholder="email1@example.com, email2@example.com"
									disabled={!['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Carbon alert email recipients"
								/>
								<p class="text-xs text-ink-500 mt-1">
									Comma-separated email addresses for carbon budget alerts
								</p>
							</div>
						{/if}

						<button
							type="button"
							class="btn btn-primary"
							onclick={saveCarbonSettings}
							disabled={savingCarbon ||
								!['growth', 'pro', 'enterprise'].includes(data.subscription?.tier)}
							aria-label="Save carbon budget settings"
						>
							{savingCarbon ? '⏳ Saving...' : '💾 Save Carbon Settings'}
						</button>
					</div>
				{/if}
			</div>

			<IdentitySettingsCard
				accessToken={data.session?.access_token}
				tier={data.subscription?.tier}
			/>

			<EnforcementSettingsCard
				accessToken={data.session?.access_token}
				tier={data.subscription?.tier}
			/>

			<EnforcementOpsCard accessToken={data.session?.access_token} tier={data.subscription?.tier} />

			<!-- AI Strategy Settings -->
			<div class="card stagger-enter">
				<h2 class="text-lg font-semibold mb-5 flex items-center gap-2">
					<span>🤖</span> AI Strategy
				</h2>

				{#if loadingLLM}
					<div class="skeleton h-4 w-48"></div>
				{:else}
					<div class="space-y-4">
						<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
							<div class="form-group">
								<label for="provider">Preferred Provider</label>
								<select
									id="provider"
									bind:value={llmSettings.preferred_provider}
									class="select"
									onchange={() =>
										(llmSettings.preferred_model =
											providerModels[
												llmSettings.preferred_provider as keyof typeof providerModels
											][0])}
									aria-label="Preferred AI provider"
								>
									<option value="groq">Groq (Ultra-Fast)</option>
									<option value="openai">OpenAI (Gold Standard)</option>
									<option value="anthropic">Anthropic (Claude)</option>
									<option value="google">Google (Gemini)</option>
								</select>
							</div>

							<div class="form-group">
								<label for="model">AI Model</label>
								<select
									id="model"
									bind:value={llmSettings.preferred_model}
									class="select"
									aria-label="Preferred AI model"
								>
									{#each providerModels[llmSettings.preferred_provider as keyof typeof providerModels] as model (model)}
										<option value={model}>{model}</option>
									{/each}
								</select>
							</div>
						</div>

						<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
							<div class="form-group">
								<label for="llm_budget">Monthly AI Budget (USD)</label>
								<input
									type="number"
									id="llm_budget"
									bind:value={llmSettings.monthly_limit_usd}
									min="0"
									step="1"
									aria-label="Monthly AI budget in USD"
								/>
							</div>

							<div class="form-group">
								<label for="llm_alert_threshold">Alert Threshold (%)</label>
								<input
									type="number"
									id="llm_alert_threshold"
									bind:value={llmSettings.alert_threshold_percent}
									min="0"
									max="100"
									aria-label="AI alert threshold percentage"
								/>
							</div>
						</div>

						<div class="space-y-4 pt-4 border-t border-ink-700">
							<h3 class="text-sm font-semibold text-accent-400 uppercase tracking-wider">
								Bring Your Own Key (Optional)
							</h3>
							<p class="text-xs text-ink-400">
								Provide your own API key to pay the provider directly. The platform will still track
								usage for your awareness.
							</p>

							<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
								<div class="form-group">
									<label for="openai_key" class="flex items-center justify-between">
										<span>OpenAI API Key</span>
										{#if llmSettings.has_openai_key}
											<span
												class="text-xs px-1.5 py-0.5 rounded bg-success-500/10 text-success-400 border border-success-500/50"
												>Configured</span
											>
										{/if}
									</label>
									<input
										type="password"
										id="openai_key"
										bind:value={llmSettings.openai_api_key}
										placeholder={llmSettings.has_openai_key ? '••••••••••••••••' : 'sk-...'}
										aria-label="OpenAI API Key"
									/>
								</div>
								<div class="form-group">
									<label for="claude_key" class="flex items-center justify-between">
										<span>Claude API Key</span>
										{#if llmSettings.has_claude_key}
											<span
												class="text-xs px-1.5 py-0.5 rounded bg-success-500/10 text-success-400 border border-success-500/50"
												>Configured</span
											>
										{/if}
									</label>
									<input
										type="password"
										id="claude_key"
										bind:value={llmSettings.claude_api_key}
										placeholder={llmSettings.has_claude_key ? '••••••••••••••••' : 'sk-ant-...'}
										aria-label="Claude API Key"
									/>
								</div>
								<div class="form-group">
									<label for="google_key" class="flex items-center justify-between">
										<span>Google AI (Gemini) Key</span>
										{#if llmSettings.has_google_key}
											<span
												class="text-xs px-1.5 py-0.5 rounded bg-success-500/10 text-success-400 border border-success-500/50"
												>Configured</span
											>
										{/if}
									</label>
									<input
										type="password"
										id="google_key"
										bind:value={llmSettings.google_api_key}
										placeholder={llmSettings.has_google_key ? '••••••••••••••••' : 'AIza...'}
										aria-label="Google AI (Gemini) API Key"
									/>
								</div>
								<div class="form-group">
									<label for="groq_key" class="flex items-center justify-between">
										<span>Groq API Key</span>
										{#if llmSettings.has_groq_key}
											<span
												class="text-xs px-1.5 py-0.5 rounded bg-success-500/10 text-success-400 border border-success-500/50"
												>Configured</span
											>
										{/if}
									</label>
									<input
										type="password"
										id="groq_key"
										bind:value={llmSettings.groq_api_key}
										placeholder={llmSettings.has_groq_key ? '••••••••••••••••' : 'gsk_...'}
										aria-label="Groq API Key"
									/>
								</div>
							</div>
						</div>

						<div class="form-group">
							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={llmSettings.hard_limit}
									class="toggle"
									aria-label="Enable hard limit for AI budget"
								/>
								<span>Enable Hard Limit (Block AI analysis if budget exceeded)</span>
							</label>
						</div>

						<button
							type="button"
							class="btn btn-primary"
							onclick={saveLLMSettings}
							disabled={savingLLM}
							aria-label="Save AI strategy settings"
						>
							{savingLLM ? '⏳ Saving...' : '💾 Save AI Strategy'}
						</button>
					</div>
				{/if}
			</div>

			<!-- ActiveOps (Remediation) Settings -->
			<div
				class="card stagger-enter relative"
				class:opacity-60={!['pro', 'enterprise'].includes(data.subscription?.tier)}
				class:pointer-events-none={!['pro', 'enterprise'].includes(data.subscription?.tier)}
			>
				<div class="flex items-center justify-between mb-3">
					<h2 class="text-lg font-semibold flex items-center gap-2">
						<span>⚡</span> ActiveOps (Autonomous Remediation)
					</h2>

					{#if !['pro', 'enterprise'].includes(data.subscription?.tier)}
						<span class="badge badge-warning text-xs">Pro Plan Required</span>
					{/if}
				</div>

				{#if !['pro', 'enterprise'].includes(data.subscription?.tier)}
					<div class="absolute inset-0 z-10 flex items-center justify-center bg-transparent">
						<a href={`${base}/billing`} class="btn btn-primary shadow-lg pointer-events-auto">
							Upgrade to Unlock Auto-Pilot
						</a>
					</div>
				{/if}

				<p class="text-xs text-ink-400 mb-5">
					Enable AI to automatically remediate high-confidence zombie resources during weekly
					sweeps.
				</p>

				{#if loadingActiveOps}
					<div class="skeleton h-4 w-48"></div>
				{:else}
					<div class="space-y-6">
						<div class="p-4 rounded-lg bg-warning-900/10 border border-warning-900/30">
							<h4 class="text-sm font-bold text-warning-400 mb-1">⚠️ Safety Disclaimer</h4>
							<p class="text-xs text-warning-500 leading-relaxed">
								Auto-Pilot mode allows Valdrics to perform destructive actions (deletion) on
								identified resources. Always ensure you have regular backups. Actions are only taken
								if the AI confidence exceeds the specified threshold.
							</p>
						</div>

						<label class="flex items-center gap-3 cursor-pointer">
							<input
								type="checkbox"
								bind:checked={activeOpsSettings.auto_pilot_enabled}
								class="toggle toggle-warning"
								disabled={!['pro', 'enterprise'].includes(data.subscription?.tier)}
								aria-label="Enable Auto-Pilot for autonomous deletion"
							/>
							<span
								class="font-medium {activeOpsSettings.auto_pilot_enabled
									? 'text-white'
									: 'text-ink-400'}"
							>
								Enable Auto-Pilot (Weekly Autonomous Deletion)
							</span>
						</label>

						<div class="form-group">
							<label for="confidence_threshold"
								>Min Confidence Threshold: {Math.round(
									activeOpsSettings.min_confidence_threshold * 100
								)}%</label
							>
							<input
								type="range"
								id="confidence_threshold"
								bind:value={activeOpsSettings.min_confidence_threshold}
								min="0.5"
								max="1.0"
								step="0.01"
								class="range"
								disabled={!activeOpsSettings.auto_pilot_enabled ||
									!['pro', 'enterprise'].includes(data.subscription?.tier)}
								aria-label="Minimum AI confidence threshold for autonomous actions"
							/>
							<div class="flex justify-between text-xs text-ink-500 mt-1">
								<span>Riskier (50%)</span>
								<span>Ultra-Safe (100%)</span>
							</div>
						</div>

						<div class="pt-2 border-t border-white/10 space-y-3">
							<h4 class="text-sm font-semibold text-ink-200">Policy Guardrails</h4>
							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={activeOpsSettings.policy_enabled}
									class="toggle"
									disabled={!['pro', 'enterprise'].includes(data.subscription?.tier)}
								/>
								<span>Enable request-level policy guardrails</span>
							</label>

							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={activeOpsSettings.policy_block_production_destructive}
									class="toggle"
									disabled={!activeOpsSettings.policy_enabled ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
								/>
								<span>Block destructive actions on production-like resources</span>
							</label>

							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={activeOpsSettings.policy_require_gpu_override}
									class="toggle"
									disabled={!activeOpsSettings.policy_enabled ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
								/>
								<span>Require explicit override for GPU-impacting changes</span>
							</label>

							<div class="form-group">
								<label for="policy_warn_threshold"
									>Low-Confidence Warn Threshold: {Math.round(
										activeOpsSettings.policy_low_confidence_warn_threshold * 100
									)}%</label
								>
								<input
									type="range"
									id="policy_warn_threshold"
									bind:value={activeOpsSettings.policy_low_confidence_warn_threshold}
									min="0.5"
									max="1.0"
									step="0.01"
									class="range"
									disabled={!activeOpsSettings.policy_enabled ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
								/>
							</div>

							<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
								<label class="flex items-center gap-3 cursor-pointer">
									<input
										type="checkbox"
										bind:checked={activeOpsSettings.policy_violation_notify_slack}
										class="toggle"
										disabled={!activeOpsSettings.policy_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
									<span>Notify policy violations to Slack</span>
								</label>
								<label class="flex items-center gap-3 cursor-pointer">
									<input
										type="checkbox"
										bind:checked={activeOpsSettings.policy_violation_notify_jira}
										class="toggle"
										disabled={!activeOpsSettings.policy_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
									<span>Notify policy violations to Jira</span>
								</label>
							</div>

							<div class="form-group border-t border-white/10 pt-4">
								<label for="policy_escalation_role">Escalation Approval Role</label>
								<select
									id="policy_escalation_role"
									bind:value={activeOpsSettings.policy_escalation_required_role}
									disabled={!activeOpsSettings.policy_enabled ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
								>
									<option value="owner">Owner</option>
									<option value="admin">Admin</option>
								</select>
							</div>
						</div>

						<div class="pt-2 border-t border-white/10 space-y-4">
							<h4 class="text-sm font-semibold text-ink-200 flex items-center gap-2">
								<span>🪪</span> License & SaaS Governance
							</h4>

							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={activeOpsSettings.license_auto_reclaim_enabled}
									class="toggle toggle-success"
									disabled={!['pro', 'enterprise'].includes(data.subscription?.tier)}
								/>
								<span>Enable autonomous seat reclamation for inactive users</span>
							</label>

							<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
								<div class="form-group">
									<label for="inactive_threshold"
										>Inactivity Threshold: {activeOpsSettings.license_inactive_threshold_days} days</label
									>
									<input
										type="range"
										id="inactive_threshold"
										bind:value={activeOpsSettings.license_inactive_threshold_days}
										min="7"
										max="365"
										step="1"
										class="range range-success"
										disabled={!activeOpsSettings.license_auto_reclaim_enabled}
									/>
								</div>
								<div class="form-group">
									<label for="grace_period"
										>Notification Grace Period: {activeOpsSettings.license_reclaim_grace_period_days}
										days</label
									>
									<input
										type="range"
										id="grace_period"
										bind:value={activeOpsSettings.license_reclaim_grace_period_days}
										min="1"
										max="30"
										step="1"
										class="range range-info"
										disabled={!activeOpsSettings.license_auto_reclaim_enabled}
									/>
								</div>
							</div>

							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={activeOpsSettings.license_downgrade_recommendations_enabled}
									class="toggle"
									disabled={!['pro', 'enterprise'].includes(data.subscription?.tier)}
								/>
								<span>Enable cost-saving tier downgrade recommendations</span>
							</label>
						</div>

						<button
							type="button"
							class="btn btn-primary"
							onclick={saveActiveOpsSettings}
							disabled={savingActiveOps || !['pro', 'enterprise'].includes(data.subscription?.tier)}
							aria-label="Save ActiveOps settings"
						>
							{savingActiveOps ? '⏳ Saving...' : '💾 Save ActiveOps Settings'}
						</button>
					</div>
				{/if}
			</div>

			<!-- Safety Controls -->
			<div class="card stagger-enter">
				<div class="flex items-center justify-between mb-4">
					<h2 class="text-lg font-semibold flex items-center gap-2">
						<span>🛡️</span> Remediation Safety Controls
					</h2>
					<div class="flex items-center gap-2">
						<button
							type="button"
							class="btn btn-ghost"
							onclick={loadSafetyStatus}
							disabled={loadingSafety || resettingSafety}
							aria-label="Refresh remediation safety status"
						>
							{loadingSafety ? 'Refreshing...' : 'Refresh'}
						</button>
						<button
							type="button"
							class="btn btn-secondary"
							onclick={resetSafetyCircuitBreaker}
							disabled={loadingSafety || resettingSafety}
							aria-label="Reset remediation circuit breaker"
						>
							{resettingSafety ? 'Resetting...' : 'Reset Circuit Breaker'}
						</button>
					</div>
				</div>
				<p class="text-xs text-ink-400 mb-4">
					Tracks runtime safety state for auto-remediation. Reset requires admin role and records an
					audit event.
				</p>

				{#if safetyError}
					<div
						class="mb-4 rounded-lg border border-danger-500/50 bg-danger-500/10 p-3 text-sm text-danger-400"
					>
						{safetyError}
					</div>
				{/if}
				{#if safetySuccess}
					<div
						class="mb-4 rounded-lg border border-success-500/50 bg-success-500/10 p-3 text-sm text-success-400"
					>
						{safetySuccess}
					</div>
				{/if}

				{#if loadingSafety}
					<div class="skeleton h-20 w-full"></div>
				{:else if safetyStatus}
					<div class="space-y-4">
						<div class="grid grid-cols-1 md:grid-cols-4 gap-3">
							<div class="rounded-lg border border-ink-700 p-3">
								<p class="text-xs uppercase tracking-wide text-ink-500 mb-1">Circuit State</p>
								<span
									class="badge"
									class:badge-success={safetyStatus.circuit_state === 'closed'}
									class:badge-warning={safetyStatus.circuit_state === 'half_open'}
									class:badge-error={['open', 'unknown'].includes(safetyStatus.circuit_state)}
								>
									{formatCircuitState(safetyStatus.circuit_state)}
								</span>
							</div>

							<div class="rounded-lg border border-ink-700 p-3">
								<p class="text-xs uppercase tracking-wide text-ink-500 mb-1">Execution</p>
								<p class={safetyStatus.can_execute ? 'text-success-400' : 'text-danger-400'}>
									{safetyStatus.can_execute ? 'Allowed' : 'Blocked'}
								</p>
							</div>

							<div class="rounded-lg border border-ink-700 p-3">
								<p class="text-xs uppercase tracking-wide text-ink-500 mb-1">Failure Count</p>
								<p class="text-white">{safetyStatus.failure_count}</p>
							</div>

							<div class="rounded-lg border border-ink-700 p-3">
								<p class="text-xs uppercase tracking-wide text-ink-500 mb-1">Last Failure</p>
								<p class="text-white text-xs">{formatSafetyDate(safetyStatus.last_failure_at)}</p>
							</div>
						</div>

						<div class="rounded-lg border border-ink-700 p-3">
							<div class="flex items-center justify-between text-xs text-ink-400 mb-2">
								<span>Daily Savings Guardrail</span>
								<span>
									${safetyStatus.daily_savings_used.toFixed(2)} / ${safetyStatus.daily_savings_limit.toFixed(
										2
									)}
								</span>
							</div>
							<div class="h-2 w-full bg-ink-800 rounded-full overflow-hidden">
								<div
									class="h-full rounded-full transition-all duration-500"
									class:bg-success-500={safetyUsagePercent(safetyStatus) < 70}
									class:bg-warning-500={safetyUsagePercent(safetyStatus) >= 70 &&
										safetyUsagePercent(safetyStatus) < 90}
									class:bg-danger-500={safetyUsagePercent(safetyStatus) >= 90}
									style="width: {safetyUsagePercent(safetyStatus)}%"
								></div>
							</div>
							<p class="mt-1 text-right text-xs text-ink-500">
								{safetyUsagePercent(safetyStatus).toFixed(1)}% used
							</p>
						</div>
					</div>
				{/if}
			</div>

			<!-- Slack Settings -->
			<div class="card stagger-enter">
				<h2 class="text-lg font-semibold mb-5 flex items-center gap-2">
					<span>💬</span> Slack Notifications
				</h2>

				<div class="space-y-4">
					<label class="flex items-center gap-3 cursor-pointer">
						<input
							type="checkbox"
							bind:checked={settings.slack_enabled}
							class="toggle"
							aria-label="Enable Slack notifications"
						/>
						<span>Enable Slack notifications</span>
					</label>

					<div class="form-group">
						<label for="channel">Channel Override (optional)</label>
						<input
							type="text"
							id="channel"
							bind:value={settings.slack_channel_override}
							placeholder="C01234ABCDE"
							disabled={!settings.slack_enabled}
							aria-label="Slack channel ID override"
						/>
						<p class="text-xs text-ink-500 mt-1">Leave empty to use the default channel</p>
					</div>

					<button
						type="button"
						class="btn btn-secondary"
						onclick={testSlack}
						disabled={!settings.slack_enabled || testing}
						aria-label="Send test Slack notification"
					>
						{testing ? '⏳ Sending...' : '🧪 Send Test Notification'}
					</button>

					<div class="pt-4 border-t border-ink-200">
						<h3 class="text-sm font-semibold mb-3">Jira Incident Routing (Pro+)</h3>
						<label class="flex items-center gap-3 cursor-pointer mb-3">
							<input
								type="checkbox"
								bind:checked={settings.jira_enabled}
								class="toggle"
								disabled={!['pro', 'enterprise'].includes(data.subscription?.tier)}
								aria-label="Enable Jira policy notifications"
							/>
							<span>Enable Jira policy notifications</span>
						</label>

						<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
							<div class="form-group">
								<label for="jira_base_url">Jira Base URL</label>
								<input
									type="url"
									id="jira_base_url"
									bind:value={settings.jira_base_url}
									placeholder="https://your-org.atlassian.net"
									disabled={!settings.jira_enabled ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Jira base URL"
								/>
							</div>
							<div class="form-group">
								<label for="jira_email">Jira Account Email</label>
								<input
									type="email"
									id="jira_email"
									bind:value={settings.jira_email}
									placeholder="jira@company.com"
									disabled={!settings.jira_enabled ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Jira account email"
								/>
							</div>
							<div class="form-group">
								<label for="jira_project_key">Jira Project Key</label>
								<input
									type="text"
									id="jira_project_key"
									bind:value={settings.jira_project_key}
									placeholder="FINOPS"
									disabled={!settings.jira_enabled ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Jira project key"
								/>
							</div>
							<div class="form-group">
								<label for="jira_issue_type">Issue Type</label>
								<input
									type="text"
									id="jira_issue_type"
									bind:value={settings.jira_issue_type}
									placeholder="Task"
									disabled={!settings.jira_enabled ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Jira issue type"
								/>
							</div>
						</div>

						<div class="form-group">
							<label for="jira_api_token">Jira API Token</label>
							<input
								type="password"
								id="jira_api_token"
								bind:value={settings.jira_api_token}
								placeholder={settings.has_jira_api_token
									? 'Stored token exists. Enter new token to rotate.'
									: 'Enter Jira API token'}
								disabled={!settings.jira_enabled ||
									!['pro', 'enterprise'].includes(data.subscription?.tier)}
								aria-label="Jira API token"
							/>
						</div>
						<label class="flex items-center gap-3 cursor-pointer mb-3">
							<input
								type="checkbox"
								bind:checked={settings.clear_jira_api_token}
								class="toggle"
								disabled={!settings.jira_enabled ||
									!settings.has_jira_api_token ||
									!['pro', 'enterprise'].includes(data.subscription?.tier)}
								aria-label="Clear stored Jira API token"
							/>
							<span>Clear stored Jira token</span>
						</label>
						<button
							type="button"
							class="btn btn-secondary"
							onclick={testJira}
							disabled={!settings.jira_enabled ||
								testingJira ||
								!['pro', 'enterprise'].includes(data.subscription?.tier)}
							aria-label="Send test Jira issue"
						>
							{testingJira ? '⏳ Sending...' : '🧪 Send Test Jira Issue'}
						</button>

						<div class="pt-4 border-t border-ink-200 mt-4">
							<h3 class="text-sm font-semibold mb-3">Microsoft Teams Incident Routing (Pro+)</h3>
							<label class="flex items-center gap-3 cursor-pointer mb-3">
								<input
									type="checkbox"
									bind:checked={settings.teams_enabled}
									class="toggle"
									disabled={!['pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Enable Teams policy notifications"
								/>
								<span>Enable Teams policy notifications</span>
							</label>
							<div class="form-group">
								<label for="teams_webhook_url">Teams Webhook URL</label>
								<input
									type="password"
									id="teams_webhook_url"
									bind:value={settings.teams_webhook_url}
									placeholder={settings.has_teams_webhook_url
										? 'Stored webhook exists. Enter new URL to rotate.'
										: 'https://<tenant>.webhook.office.com/...'}
									disabled={!settings.teams_enabled ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Teams webhook URL"
								/>
								<p class="text-xs text-ink-500 mt-1">
									Webhook URL is encrypted at rest and used for policy/remediation alerts.
								</p>
							</div>
							<label class="flex items-center gap-3 cursor-pointer mb-3">
								<input
									type="checkbox"
									bind:checked={settings.clear_teams_webhook_url}
									class="toggle"
									disabled={!settings.teams_enabled ||
										!settings.has_teams_webhook_url ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Clear stored Teams webhook URL"
								/>
								<span>Clear stored Teams webhook URL</span>
							</label>
							<button
								type="button"
								class="btn btn-secondary"
								onclick={testTeams}
								disabled={!settings.teams_enabled ||
									testingTeams ||
									!['pro', 'enterprise'].includes(data.subscription?.tier)}
								aria-label="Send test Teams notification"
							>
								{testingTeams ? '⏳ Sending...' : '🧪 Send Test Teams Notification'}
							</button>
						</div>

						<div class="mt-4 rounded-xl border border-ink-700 p-4 bg-ink-900/30 space-y-4">
							<div class="flex items-center justify-between">
								<h4 class="text-sm font-semibold">Workflow Automation (GitHub/GitLab/Webhook)</h4>
								{#if !['pro', 'enterprise'].includes(data.subscription?.tier)}
									<span class="badge badge-warning text-xs">Pro Plan Required</span>
								{/if}
							</div>
							<p class="text-xs text-ink-400">
								Route policy and remediation events into your CI runbooks using tenant-scoped
								credentials.
							</p>

							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={settings.workflow_github_enabled}
									class="toggle"
									disabled={!['pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Enable GitHub workflow dispatch"
								/>
								<span>Enable GitHub Actions workflow dispatch</span>
							</label>
							<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
								<div class="form-group">
									<label for="workflow_github_owner">GitHub Owner</label>
									<input
										type="text"
										id="workflow_github_owner"
										bind:value={settings.workflow_github_owner}
										placeholder="Valdrix-AI"
										disabled={!settings.workflow_github_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
								</div>
								<div class="form-group">
									<label for="workflow_github_repo">GitHub Repo</label>
									<input
										type="text"
										id="workflow_github_repo"
										bind:value={settings.workflow_github_repo}
										placeholder="valdrix"
										disabled={!settings.workflow_github_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
								</div>
								<div class="form-group">
									<label for="workflow_github_workflow_id">Workflow ID/File</label>
									<input
										type="text"
										id="workflow_github_workflow_id"
										bind:value={settings.workflow_github_workflow_id}
										placeholder="remediation.yml"
										disabled={!settings.workflow_github_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
								</div>
								<div class="form-group">
									<label for="workflow_github_ref">Ref</label>
									<input
										type="text"
										id="workflow_github_ref"
										bind:value={settings.workflow_github_ref}
										placeholder="main"
										disabled={!settings.workflow_github_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
								</div>
							</div>
							<div class="form-group">
								<label for="workflow_github_token">GitHub Token</label>
								<input
									type="password"
									id="workflow_github_token"
									bind:value={settings.workflow_github_token}
									placeholder={settings.workflow_has_github_token
										? 'Stored token exists. Enter new token to rotate.'
										: 'Enter GitHub token'}
									disabled={!settings.workflow_github_enabled ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
								/>
							</div>
							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={settings.clear_workflow_github_token}
									class="toggle"
									disabled={!settings.workflow_github_enabled ||
										!settings.workflow_has_github_token ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
								/>
								<span>Clear stored GitHub token</span>
							</label>

							<div class="h-px bg-ink-700"></div>

							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={settings.workflow_gitlab_enabled}
									class="toggle"
									disabled={!['pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Enable GitLab workflow dispatch"
								/>
								<span>Enable GitLab CI trigger dispatch</span>
							</label>
							<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
								<div class="form-group">
									<label for="workflow_gitlab_base_url">GitLab Base URL</label>
									<input
										type="url"
										id="workflow_gitlab_base_url"
										bind:value={settings.workflow_gitlab_base_url}
										placeholder="https://gitlab.com"
										disabled={!settings.workflow_gitlab_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
								</div>
								<div class="form-group">
									<label for="workflow_gitlab_project_id">Project ID/Path</label>
									<input
										type="text"
										id="workflow_gitlab_project_id"
										bind:value={settings.workflow_gitlab_project_id}
										placeholder="12345"
										disabled={!settings.workflow_gitlab_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
								</div>
								<div class="form-group">
									<label for="workflow_gitlab_ref">Ref</label>
									<input
										type="text"
										id="workflow_gitlab_ref"
										bind:value={settings.workflow_gitlab_ref}
										placeholder="main"
										disabled={!settings.workflow_gitlab_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
								</div>
								<div class="form-group">
									<label for="workflow_gitlab_trigger_token">Trigger Token</label>
									<input
										type="password"
										id="workflow_gitlab_trigger_token"
										bind:value={settings.workflow_gitlab_trigger_token}
										placeholder={settings.workflow_has_gitlab_trigger_token
											? 'Stored token exists. Enter new token to rotate.'
											: 'Enter GitLab trigger token'}
										disabled={!settings.workflow_gitlab_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
								</div>
							</div>
							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={settings.clear_workflow_gitlab_trigger_token}
									class="toggle"
									disabled={!settings.workflow_gitlab_enabled ||
										!settings.workflow_has_gitlab_trigger_token ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
								/>
								<span>Clear stored GitLab trigger token</span>
							</label>

							<div class="h-px bg-ink-700"></div>

							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={settings.workflow_webhook_enabled}
									class="toggle"
									disabled={!['pro', 'enterprise'].includes(data.subscription?.tier)}
									aria-label="Enable webhook workflow dispatch"
								/>
								<span>Enable Generic CI Webhook dispatch</span>
							</label>
							<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
								<div class="form-group">
									<label for="workflow_webhook_url">Webhook URL</label>
									<input
										type="url"
										id="workflow_webhook_url"
										bind:value={settings.workflow_webhook_url}
										placeholder="https://ci.example.com/hooks/valdrix"
										disabled={!settings.workflow_webhook_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
								</div>
								<div class="form-group">
									<label for="workflow_webhook_bearer_token">Bearer Token (optional)</label>
									<input
										type="password"
										id="workflow_webhook_bearer_token"
										bind:value={settings.workflow_webhook_bearer_token}
										placeholder={settings.workflow_has_webhook_bearer_token
											? 'Stored token exists. Enter new token to rotate.'
											: 'Enter bearer token (optional)'}
										disabled={!settings.workflow_webhook_enabled ||
											!['pro', 'enterprise'].includes(data.subscription?.tier)}
									/>
								</div>
							</div>
							<label class="flex items-center gap-3 cursor-pointer">
								<input
									type="checkbox"
									bind:checked={settings.clear_workflow_webhook_bearer_token}
									class="toggle"
									disabled={!settings.workflow_webhook_enabled ||
										!settings.workflow_has_webhook_bearer_token ||
										!['pro', 'enterprise'].includes(data.subscription?.tier)}
								/>
								<span>Clear stored webhook bearer token</span>
							</label>

							<button
								type="button"
								class="btn btn-secondary"
								onclick={testWorkflowDispatch}
								disabled={testingWorkflow ||
									!['pro', 'enterprise'].includes(data.subscription?.tier)}
								aria-label="Send test workflow event"
							>
								{testingWorkflow ? '⏳ Sending...' : '🧪 Send Test Workflow Event'}
							</button>
						</div>

						<div class="mt-4 rounded-xl border border-ink-700 p-4 bg-ink-900/30">
							<div class="flex flex-wrap items-center justify-between gap-3 mb-3">
								<h4 class="text-sm font-semibold">Policy Notification Diagnostics</h4>
								<button
									type="button"
									class="btn btn-ghost"
									onclick={runPolicyDiagnostics}
									disabled={diagnosticsLoading}
									aria-label="Run policy notification diagnostics"
								>
									{diagnosticsLoading ? '⏳ Checking...' : '🔍 Run Diagnostics'}
								</button>
							</div>

							{#if policyDiagnostics}
								<p class="text-xs text-ink-400 mb-3">
									Tier: <span class="font-semibold uppercase">{policyDiagnostics.tier}</span>
									• Policy enabled: {policyDiagnostics.policy_enabled ? 'yes' : 'no'}
								</p>

								<div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
									<div class="rounded-lg border border-ink-700 p-3">
										<div class="flex items-center justify-between">
											<span class="font-medium">Slack</span>
											<span
												class={policyDiagnostics.slack.ready
													? 'text-success-400'
													: 'text-warning-400'}
											>
												{policyDiagnostics.slack.ready ? 'Ready' : 'Blocked'}
											</span>
										</div>
										{#if policyDiagnostics.slack.reasons.length > 0}
											<p class="text-xs text-ink-400 mt-2 break-words">
												{policyDiagnostics.slack.reasons.join(', ')}
											</p>
										{/if}
									</div>

									<div class="rounded-lg border border-ink-700 p-3">
										<div class="flex items-center justify-between">
											<span class="font-medium">Jira</span>
											<span
												class={policyDiagnostics.jira.ready
													? 'text-success-400'
													: 'text-warning-400'}
											>
												{policyDiagnostics.jira.ready ? 'Ready' : 'Blocked'}
											</span>
										</div>
										{#if policyDiagnostics.jira.reasons.length > 0}
											<p class="text-xs text-ink-400 mt-2 break-words">
												{policyDiagnostics.jira.reasons.join(', ')}
											</p>
										{/if}
									</div>
								</div>
							{/if}
						</div>
					</div>
				</div>
			</div>

			<!-- Digest Schedule -->
			<div class="card stagger-enter" style="animation-delay: 50ms;">
				<h2 class="text-lg font-semibold mb-5 flex items-center gap-2">
					<span>📅</span> Daily Digest
				</h2>

				<div class="space-y-4">
					<div class="form-group">
						<label for="schedule">Frequency</label>
						<select
							id="schedule"
							bind:value={settings.digest_schedule}
							class="select"
							aria-label="Daily digest frequency"
						>
							<option value="daily">Daily</option>
							<option value="weekly">Weekly (Mondays)</option>
							<option value="disabled">Disabled</option>
						</select>
					</div>

					{#if settings.digest_schedule !== 'disabled'}
						<div class="grid grid-cols-2 gap-4">
							<div class="form-group">
								<label for="hour">Hour (UTC)</label>
								<select
									id="hour"
									bind:value={settings.digest_hour}
									class="select"
									aria-label="Digest delivery hour (UTC)"
								>
									{#each Array(24)
										.fill(0)
										.map((_, i) => i) as h (h)}
										<option value={h}>{h.toString().padStart(2, '0')}:00</option>
									{/each}
								</select>
							</div>
							<div class="form-group">
								<label for="minute">Minute</label>
								<select
									id="minute"
									bind:value={settings.digest_minute}
									class="select"
									aria-label="Digest delivery minute"
								>
									{#each [0, 15, 30, 45] as m (m)}
										<option value={m}>:{m.toString().padStart(2, '0')}</option>
									{/each}
								</select>
							</div>
						</div>
					{/if}
				</div>
			</div>

			<!-- Alert Preferences -->
			<div class="card stagger-enter" style="animation-delay: 100ms;">
				<h2 class="text-lg font-semibold mb-5 flex items-center gap-2">
					<span>🚨</span> Alert Preferences
				</h2>

				<div class="space-y-3">
					<label class="flex items-center gap-3 cursor-pointer">
						<input type="checkbox" bind:checked={settings.alert_on_budget_warning} class="toggle" />
						<span>Alert when approaching budget limit</span>
					</label>

					<label class="flex items-center gap-3 cursor-pointer">
						<input
							type="checkbox"
							bind:checked={settings.alert_on_budget_exceeded}
							class="toggle"
						/>
						<span>Alert when budget is exceeded</span>
					</label>

					<label class="flex items-center gap-3 cursor-pointer">
						<input
							type="checkbox"
							bind:checked={settings.alert_on_zombie_detected}
							class="toggle"
						/>
						<span>Alert when zombie resources detected</span>
					</label>
				</div>
			</div>

			<!-- Save Button -->
			<div class="flex justify-end">
				<button type="button" class="btn btn-primary" onclick={saveSettings} disabled={saving}>
					{saving ? '⏳ Saving...' : '💾 Save Settings'}
				</button>
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
	.border-danger-500\/50 {
		border-color: rgb(244 63 94 / 0.5);
	}
	.border-success-500\/50 {
		border-color: rgb(16 185 129 / 0.5);
	}

	.form-group {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.form-group label {
		font-weight: 500;
		font-size: 0.875rem;
	}

	input[type='text'],
	.select {
		width: 100%;
		padding: 0.75rem;
		border: 1px solid var(--color-ink-700);
		border-radius: 0.5rem;
		background: var(--color-ink-900);
		color: white;
	}

	input:disabled,
	.select:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.toggle {
		width: 3rem;
		height: 1.5rem;
		appearance: none;
		background: var(--color-ink-700);
		border-radius: 999px;
		position: relative;
		cursor: pointer;
		transition: background 0.2s;
	}

	.toggle:checked {
		background: var(--color-accent-500);
	}

	.toggle::after {
		content: '';
		position: absolute;
		top: 2px;
		left: 2px;
		width: 1.25rem;
		height: 1.25rem;
		background: white;
		border-radius: 50%;
		transition: transform 0.2s;
	}

	.toggle:checked::after {
		transform: translateX(1.5rem);
	}

	.toggle-warning:checked {
		background: var(--color-warning-500);
	}

	.range {
		width: 100%;
		height: 0.5rem;
		background: var(--color-ink-700);
		border-radius: 999px;
		appearance: none;
		outline: none;
	}

	.range::-webkit-slider-thumb {
		appearance: none;
		width: 1.25rem;
		height: 1.25rem;
		background: var(--color-accent-400);
		border-radius: 50%;
		cursor: pointer;
		transition: transform 0.1s;
	}

	.range::-webkit-slider-thumb:hover {
		transform: scale(1.1);
	}

	.range:disabled::-webkit-slider-thumb {
		background: var(--color-ink-500);
		cursor: not-allowed;
	}

	.btn {
		padding: 0.75rem 1.5rem;
		border-radius: 0.5rem;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s;
	}

	.btn-primary {
		background: var(--color-accent-500);
		color: white;
		border: none;
	}

	.btn-primary:hover:not(:disabled) {
		opacity: 0.9;
	}

	.btn-secondary {
		background: transparent;
		border: 1px solid var(--color-ink-600);
		color: var(--color-ink-300);
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--color-ink-800);
	}

	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.border-ink-700 {
		border-color: var(--color-ink-700);
	}
</style>
