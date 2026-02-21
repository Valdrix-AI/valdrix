<script lang="ts">
	import { onMount } from 'svelte';
	import { api } from '$lib/api';
	import AuthGate from '$lib/components/AuthGate.svelte';
	import { edgeApiPath } from '$lib/edgeProxy';
	import { TimeoutError } from '$lib/fetchWithTimeout';
	import {
		buildUnitEconomicsUrl,
		defaultDateWindow,
		formatDelta,
		hasInvalidUnitWindow,
		unitDeltaClass
	} from './unitEconomics';

	type PendingRequest = {
		id: string;
		status: string;
		resource_id: string;
		resource_type: string;
		action: string;
		provider?: string;
		region?: string;
		connection_id?: string | null;
		estimated_savings: number;
		scheduled_execution_at?: string | null;
		escalation_required?: boolean;
		escalation_reason?: string | null;
		escalated_at?: string | null;
		created_at: string | null;
	};

	type PolicyPreview = {
		decision: string;
		summary: string;
		tier: string;
		rule_hits: Array<{ rule_id: string; message: string }>;
	};

	type JobStatus = {
		pending: number;
		running: number;
		completed: number;
		failed: number;
		dead_letter: number;
	};

	type JobSLOMetric = {
		job_type: string;
		window_hours: number;
		target_success_rate_percent: number;
		total_jobs: number;
		successful_jobs: number;
		failed_jobs: number;
		success_rate_percent: number;
		meets_slo: boolean;
		latest_completed_at?: string | null;
		avg_duration_seconds?: number | null;
		p95_duration_seconds?: number | null;
	};

	type JobSLOResponse = {
		window_hours: number;
		target_success_rate_percent: number;
		overall_meets_slo: boolean;
		metrics: JobSLOMetric[];
	};

	type JobRecord = {
		id: string;
		job_type: string;
		status: string;
		attempts: number;
		created_at: string;
		error_message?: string;
	};

	type StrategyRecommendation = {
		id: string;
		resource_type: string;
		region: string;
		term: string;
		payment_option: string;
		estimated_monthly_savings: number;
		roi_percentage: number;
		status: string;
	};

	type UnitEconomicsMetric = {
		metric_key: string;
		label: string;
		denominator: number;
		total_cost: number;
		cost_per_unit: number;
		baseline_cost_per_unit: number;
		delta_percent: number;
		is_anomalous: boolean;
	};

	type UnitEconomicsResponse = {
		start_date: string;
		end_date: string;
		total_cost: number;
		baseline_total_cost: number;
		threshold_percent: number;
		anomaly_count: number;
		alert_dispatched: boolean;
		metrics: UnitEconomicsMetric[];
	};

	type UnitEconomicsSettings = {
		id: string;
		default_request_volume: number;
		default_workload_volume: number;
		default_customer_volume: number;
		anomaly_threshold_percent: number;
	};

	type IngestionSLAResponse = {
		window_hours: number;
		target_success_rate_percent: number;
		total_jobs: number;
		successful_jobs: number;
		failed_jobs: number;
		success_rate_percent: number;
		meets_sla: boolean;
		latest_completed_at: string | null;
		avg_duration_seconds: number | null;
		p95_duration_seconds: number | null;
		records_ingested: number;
	};

	type AcceptanceKpiMetric = {
		key: string;
		label: string;
		available: boolean;
		target: string;
		actual: string;
		meets_target: boolean;
		details: Record<string, unknown>;
	};

	type AcceptanceKpisResponse = {
		start_date: string;
		end_date: string;
		tier: string;
		all_targets_met: boolean;
		available_metrics: number;
		metrics: AcceptanceKpiMetric[];
	};

	type AcceptanceKpiEvidenceItem = {
		event_id: string;
		run_id: string | null;
		captured_at: string;
		actor_id: string | null;
		actor_email: string | null;
		success: boolean;
		acceptance_kpis: AcceptanceKpisResponse;
	};

	type AcceptanceKpiEvidenceResponse = {
		total: number;
		items: AcceptanceKpiEvidenceItem[];
	};

	type AcceptanceKpiCaptureResponse = {
		status: string;
		event_id: string;
		run_id: string;
		captured_at: string;
		acceptance_kpis: AcceptanceKpisResponse;
	};

	type IntegrationAcceptanceEvidenceItem = {
		event_id: string;
		run_id: string | null;
		event_type: string;
		channel: string;
		success: boolean;
		status_code: number | null;
		message: string | null;
		actor_email: string | null;
		event_timestamp: string;
		details: Record<string, unknown>;
	};

	type IntegrationAcceptanceEvidenceResponse = {
		total: number;
		items: IntegrationAcceptanceEvidenceItem[];
	};

	type IntegrationAcceptanceCaptureResponse = {
		run_id: string;
		tenant_id: string;
		captured_at: string;
		overall_status: string;
		passed: number;
		failed: number;
		results: Array<{
			channel: string;
			success: boolean;
			status_code: number;
			message: string;
		}>;
	};

	type IntegrationAcceptanceRunChannel = {
		channel: string;
		success: boolean;
		statusCode: number | null;
		message: string | null;
		eventTimestamp: string;
	};

	type IntegrationAcceptanceRun = {
		runId: string;
		capturedAt: string;
		overallStatus: string;
		passed: number;
		failed: number;
		checkedChannels: string[];
		actorEmail: string | null;
		channels: IntegrationAcceptanceRunChannel[];
	};

	type ReconciliationClosePackage = {
		tenant_id: string;
		provider: string | null;
		period: { start_date: string; end_date: string };
		close_status: string;
		lifecycle: {
			total_records: number;
			preliminary_records: number;
			final_records: number;
			total_cost_usd: number;
			preliminary_cost_usd: number;
			final_cost_usd: number;
		};
		reconciliation: {
			status: string;
			discrepancy_percentage: number;
			confidence?: number;
			comparison_basis?: string;
		};
		restatements: {
			count: number;
			net_delta_usd: number;
			absolute_delta_usd: number;
		};
		invoice_reconciliation?: {
			status: string;
			provider: string;
			period: { start_date: string; end_date: string };
			threshold_percent: number;
			invoice?: {
				id: string;
				invoice_number?: string | null;
				currency: string;
				total_amount: number;
				total_amount_usd: number;
				status: string;
				notes?: string | null;
				updated_at?: string | null;
			};
			ledger_final_cost_usd?: number;
			delta_usd?: number;
			absolute_delta_usd?: number;
			delta_percent?: number;
		} | null;
		integrity_hash: string;
		package_version: string;
	};

	type ProviderInvoiceForm = {
		invoice_number: string;
		currency: string;
		total_amount: number;
		status: string;
		notes: string;
	};

	const initialUnitWindow = defaultDateWindow(30);
	const initialCloseWindow = defaultDateWindow(30);
	const OPS_REQUEST_TIMEOUT_MS = 10000;
	const EDGE_API_BASE = edgeApiPath('').replace(/\/$/, '');

	let { data } = $props();
	let loading = $state(false);
	let error = $state('');
	let success = $state('');
	let processingJobs = $state(false);
	let refreshingStrategies = $state(false);
	let refreshingUnitEconomics = $state(false);
	let refreshingIngestionSla = $state(false);
	let refreshingJobSlo = $state(false);
	let refreshingAcceptanceKpis = $state(false);
	let refreshingAcceptanceKpiHistory = $state(false);
	let refreshingAcceptanceRuns = $state(false);
	let capturingAcceptanceRuns = $state(false);
	let capturingAcceptanceKpis = $state(false);
	let runningAcceptanceSuite = $state(false);
	let captureIncludeSlack = $state(true);
	let captureIncludeJira = $state(true);
	let captureIncludeWorkflow = $state(true);
	let captureFailFast = $state(false);
	let lastAcceptanceCapture = $state<IntegrationAcceptanceCaptureResponse | null>(null);
	let refreshingClosePackage = $state(false);
	let savingInvoice = $state(false);
	let deletingInvoice = $state(false);
	let savingUnitSettings = $state(false);
	let downloadingAcceptanceJson = $state(false);
	let downloadingAcceptanceCsv = $state(false);
	let downloadingCloseJson = $state(false);
	let downloadingCloseCsv = $state(false);
	let downloadingRestatementCsv = $state(false);
	let actingId = $state<string | null>(null);

	let pendingRequests = $state<PendingRequest[]>([]);
	let jobStatus = $state<JobStatus | null>(null);
	let jobs = $state<JobRecord[]>([]);
	let recommendations = $state<StrategyRecommendation[]>([]);
	let unitStartDate = $state(initialUnitWindow.start);
	let unitEndDate = $state(initialUnitWindow.end);
	let unitAlertOnAnomaly = $state(true);
	let unitEconomics = $state<UnitEconomicsResponse | null>(null);
	let unitSettings = $state<UnitEconomicsSettings | null>(null);
	let ingestionSlaWindowHours = $state(24);
	let ingestionSla = $state<IngestionSLAResponse | null>(null);
	let jobSloWindowHours = $state(24 * 7);
	let jobSlo = $state<JobSLOResponse | null>(null);
	let acceptanceKpis = $state<AcceptanceKpisResponse | null>(null);
	let acceptanceKpiHistory = $state<AcceptanceKpiEvidenceItem[]>([]);
	let lastAcceptanceKpiCapture = $state<AcceptanceKpiCaptureResponse | null>(null);
	let acceptanceRuns = $state<IntegrationAcceptanceRun[]>([]);
	let closeStartDate = $state(initialCloseWindow.start);
	let closeEndDate = $state(initialCloseWindow.end);
	let closeProvider = $state('all');
	let closePackage = $state<ReconciliationClosePackage | null>(null);
	let invoiceForm = $state<ProviderInvoiceForm>({
		invoice_number: '',
		currency: 'USD',
		total_amount: 0,
		status: 'submitted',
		notes: ''
	});
	let remediationModalOpen = $state(false);
	let selectedRequest = $state<PendingRequest | null>(null);
	let selectedPolicyPreview = $state<PolicyPreview | null>(null);
	let policyPreviewLoading = $state(false);
	let remediationSubmitting = $state(false);
	let remediationModalError = $state('');
	let remediationModalSuccess = $state('');
	let bypassGracePeriod = $state(false);

	function getHeaders() {
		return {
			Authorization: `Bearer ${data.session?.access_token}`
		};
	}

	async function getWithTimeout(url: string, headers: Record<string, string>) {
		return api.get(url, { headers, timeoutMs: OPS_REQUEST_TIMEOUT_MS });
	}

	function formatDate(value: string | null): string {
		if (!value) return '-';
		return new Date(value).toLocaleString();
	}

	function formatUsd(value: number): string {
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: 'USD',
			maximumFractionDigits: 2
		}).format(value || 0);
	}

	function formatNumber(value: number, fractionDigits = 2): string {
		return new Intl.NumberFormat('en-US', {
			maximumFractionDigits: fractionDigits
		}).format(value || 0);
	}

	function formatDuration(seconds: number | null): string {
		if (seconds === null || Number.isNaN(seconds)) return '-';
		if (seconds < 60) return `${Math.round(seconds)}s`;
		const minutes = Math.floor(seconds / 60);
		const remainder = Math.round(seconds % 60);
		if (minutes < 60) return `${minutes}m ${remainder}s`;
		const hours = Math.floor(minutes / 60);
		const mins = minutes % 60;
		return `${hours}h ${mins}m`;
	}

	function ingestionSlaBadgeClass(sla: IngestionSLAResponse): string {
		return sla.meets_sla ? 'badge badge-success' : 'badge badge-warning';
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

	function buildIngestionSlaUrl(): string {
		const params = new URLSearchParams({
			window_hours: String(ingestionSlaWindowHours),
			target_success_rate_percent: '95'
		});
		return edgeApiPath(`/costs/ingestion/sla?${params.toString()}`);
	}

	function buildJobSloUrl(): string {
		const params = new URLSearchParams({
			window_hours: String(jobSloWindowHours),
			target_success_rate_percent: '95'
		});
		return edgeApiPath(`/jobs/slo?${params.toString()}`);
	}

	function buildAcceptanceKpiUrl(responseFormat: 'json' | 'csv' = 'json'): string {
		const params = new URLSearchParams({
			start_date: unitStartDate,
			end_date: unitEndDate,
			ingestion_window_hours: String(ingestionSlaWindowHours),
			ingestion_target_success_rate_percent: '95',
			recency_target_hours: '48',
			chargeback_target_percent: '90',
			max_unit_anomalies: '0',
			response_format: responseFormat
		});
		return edgeApiPath(`/costs/acceptance/kpis?${params.toString()}`);
	}

	function buildAcceptanceKpiCaptureUrl(): string {
		const params = new URLSearchParams({
			start_date: unitStartDate,
			end_date: unitEndDate,
			ingestion_window_hours: String(ingestionSlaWindowHours),
			ingestion_target_success_rate_percent: '95',
			recency_target_hours: '48',
			chargeback_target_percent: '90',
			max_unit_anomalies: '0'
		});
		return edgeApiPath(`/costs/acceptance/kpis/capture?${params.toString()}`);
	}

	function buildAcceptanceKpiHistoryUrl(limit = 50): string {
		const params = new URLSearchParams({ limit: String(limit) });
		return edgeApiPath(`/costs/acceptance/kpis/evidence?${params.toString()}`);
	}

	function acceptanceBadgeClass(metric: AcceptanceKpiMetric): string {
		if (!metric.available) return 'badge badge-default';
		return metric.meets_target ? 'badge badge-success' : 'badge badge-warning';
	}

	function jobSloBadgeClass(slo: JobSLOResponse): string {
		return slo.overall_meets_slo ? 'badge badge-success' : 'badge badge-warning';
	}

	function jobSloMetricBadgeClass(metric: JobSLOMetric): string {
		return metric.meets_slo ? 'badge badge-success' : 'badge badge-warning';
	}

	function closeStatusBadgeClass(status: string | undefined): string {
		const normalized = (status || '').toLowerCase();
		if (normalized === 'ready') return 'badge badge-success';
		if (normalized.includes('blocked')) return 'badge badge-warning';
		return 'badge badge-default';
	}

	function acceptanceRunStatusClass(status: string): string {
		const normalized = status.toLowerCase();
		if (normalized === 'success') return 'badge badge-success';
		if (normalized === 'partial_failure') return 'badge badge-warning';
		if (normalized === 'failed') return 'badge badge-error';
		return 'badge badge-default';
	}

	function buildAcceptanceEvidenceUrl(limit = 100): string {
		const params = new URLSearchParams({ limit: String(limit) });
		return edgeApiPath(`/settings/notifications/acceptance-evidence?${params.toString()}`);
	}

	function hasSelectedAcceptanceChannels(): boolean {
		return captureIncludeSlack || captureIncludeJira || captureIncludeWorkflow;
	}

	function toInt(value: unknown): number | null {
		if (typeof value === 'number' && Number.isFinite(value)) return Math.trunc(value);
		if (typeof value === 'string') {
			const parsed = Number.parseInt(value, 10);
			return Number.isNaN(parsed) ? null : parsed;
		}
		return null;
	}

	function buildAcceptanceRuns(
		items: IntegrationAcceptanceEvidenceItem[]
	): IntegrationAcceptanceRun[] {
		type RunBucket = {
			runId: string;
			suite: IntegrationAcceptanceEvidenceItem | null;
			channels: Record<string, IntegrationAcceptanceEvidenceItem>;
			latestTimestamp: string;
			actorEmail: string | null;
		};
		const buckets: Record<string, RunBucket> = {};

		for (const item of items) {
			const runId = (item.run_id || '').trim() || `single:${item.event_id}`;
			const existing = buckets[runId];
			const eventTs = Date.parse(item.event_timestamp);
			if (!existing) {
				buckets[runId] = {
					runId,
					suite:
						item.channel === 'suite' || item.event_type === 'integration_test.suite' ? item : null,
					channels: item.channel === 'suite' ? {} : { [item.channel]: item },
					latestTimestamp: item.event_timestamp,
					actorEmail: item.actor_email
				};
				continue;
			}

			const currentTs = Date.parse(existing.latestTimestamp);
			if (Number.isFinite(eventTs) && (!Number.isFinite(currentTs) || eventTs > currentTs)) {
				existing.latestTimestamp = item.event_timestamp;
			}
			if (!existing.actorEmail && item.actor_email) {
				existing.actorEmail = item.actor_email;
			}
			if (item.channel === 'suite' || item.event_type === 'integration_test.suite') {
				if (!existing.suite) {
					existing.suite = item;
				} else {
					const previousSuiteTs = Date.parse(existing.suite.event_timestamp);
					if (
						Number.isFinite(eventTs) &&
						(!Number.isFinite(previousSuiteTs) || eventTs > previousSuiteTs)
					) {
						existing.suite = item;
					}
				}
			} else {
				const previousChannel = existing.channels[item.channel];
				if (!previousChannel) {
					existing.channels[item.channel] = item;
				} else {
					const previousChannelTs = Date.parse(previousChannel.event_timestamp);
					if (
						Number.isFinite(eventTs) &&
						(!Number.isFinite(previousChannelTs) || eventTs > previousChannelTs)
					) {
						existing.channels[item.channel] = item;
					}
				}
			}
		}

		return Object.values(buckets)
			.map((bucket) => {
				const channels = Object.values(bucket.channels)
					.map((entry) => ({
						channel: entry.channel,
						success: entry.success,
						statusCode: entry.status_code,
						message: entry.message,
						eventTimestamp: entry.event_timestamp
					}))
					.sort((a, b) => a.channel.localeCompare(b.channel));

				const fallbackPassed = channels.filter((channel) => channel.success).length;
				const fallbackFailed = channels.length - fallbackPassed;
				const suiteDetails = bucket.suite?.details || {};
				const checkedChannelsRaw = suiteDetails.checked_channels;
				const checkedChannels = Array.isArray(checkedChannelsRaw)
					? checkedChannelsRaw.map((value) => String(value))
					: channels.map((channel) => channel.channel);
				const passed = toInt(suiteDetails.passed) ?? fallbackPassed;
				const failed = toInt(suiteDetails.failed) ?? fallbackFailed;
				const rawOverallStatus =
					typeof suiteDetails.overall_status === 'string'
						? suiteDetails.overall_status.toLowerCase()
						: '';
				const overallStatus =
					rawOverallStatus ||
					(failed === 0 ? 'success' : passed > 0 ? 'partial_failure' : 'failed');

				return {
					runId: bucket.runId,
					capturedAt: bucket.suite?.event_timestamp || bucket.latestTimestamp,
					overallStatus,
					passed,
					failed,
					checkedChannels,
					actorEmail: bucket.actorEmail,
					channels
				} satisfies IntegrationAcceptanceRun;
			})
			.sort((a, b) => {
				const left = Date.parse(a.capturedAt);
				const right = Date.parse(b.capturedAt);
				if (!Number.isFinite(left) && !Number.isFinite(right)) return 0;
				if (!Number.isFinite(left)) return 1;
				if (!Number.isFinite(right)) return -1;
				return right - left;
			});
	}

	async function loadOpsData() {
		if (!data.user || !data.session?.access_token) {
			return;
		}
		if (hasInvalidUnitWindow(unitStartDate, unitEndDate)) {
			error = 'Unit economics date range is invalid: start date must be on or before end date.';
			return;
		}

		error = '';
		try {
			const headers = getHeaders();
			const results = await Promise.allSettled([
				getWithTimeout(edgeApiPath('/zombies/pending'), headers),
				getWithTimeout(edgeApiPath('/jobs/status'), headers),
				getWithTimeout(edgeApiPath('/jobs/list?limit=20'), headers),
				getWithTimeout(edgeApiPath('/strategies/recommendations?status=open'), headers),
				getWithTimeout(edgeApiPath('/costs/unit-economics/settings'), headers),
				getWithTimeout(
					buildUnitEconomicsUrl(EDGE_API_BASE, unitStartDate, unitEndDate, unitAlertOnAnomaly),
					headers
				),
				getWithTimeout(buildIngestionSlaUrl(), headers),
				getWithTimeout(buildJobSloUrl(), headers),
				getWithTimeout(buildAcceptanceKpiUrl(), headers),
				getWithTimeout(buildAcceptanceKpiHistoryUrl(25), headers),
				getWithTimeout(buildClosePackageUrl('json', false), headers),
				getWithTimeout(buildAcceptanceEvidenceUrl(), headers)
			]);

			const responseOrNull = (index: number): Response | null =>
				results[index]?.status === 'fulfilled'
					? (results[index] as PromiseFulfilledResult<Response>).value
					: null;

			const pendingRes = responseOrNull(0);
			const statusRes = responseOrNull(1);
			const jobsRes = responseOrNull(2);
			const recsRes = responseOrNull(3);
			const settingsRes = responseOrNull(4);
			const unitRes = responseOrNull(5);
			const ingestionSlaRes = responseOrNull(6);
			const jobSloRes = responseOrNull(7);
			const acceptanceRes = responseOrNull(8);
			const acceptanceHistoryRes = responseOrNull(9);
			const closePackageRes = responseOrNull(10);
			const acceptanceEvidenceRes = responseOrNull(11);

			pendingRequests = pendingRes?.ok ? ((await pendingRes.json()).requests ?? []) : [];
			jobStatus = statusRes?.ok ? await statusRes.json() : null;
			jobs = jobsRes?.ok ? await jobsRes.json() : [];
			recommendations = recsRes?.ok ? await recsRes.json() : [];
			unitSettings = settingsRes?.ok ? await settingsRes.json() : null;
			unitEconomics = unitRes?.ok ? await unitRes.json() : null;
			ingestionSla = ingestionSlaRes?.ok ? await ingestionSlaRes.json() : null;
			jobSlo = jobSloRes?.ok ? await jobSloRes.json() : null;
			acceptanceKpis = acceptanceRes?.ok ? await acceptanceRes.json() : null;
			const acceptanceHistoryPayload = acceptanceHistoryRes?.ok
				? ((await acceptanceHistoryRes.json()) as AcceptanceKpiEvidenceResponse)
				: null;
			acceptanceKpiHistory = acceptanceHistoryPayload?.items || [];
			closePackage = closePackageRes?.ok ? await closePackageRes.json() : null;
			const acceptanceEvidencePayload = acceptanceEvidenceRes?.ok
				? ((await acceptanceEvidenceRes.json()) as IntegrationAcceptanceEvidenceResponse)
				: null;
			acceptanceRuns = buildAcceptanceRuns(acceptanceEvidencePayload?.items || []);

			const timedOutCount = results.filter(
				(result) => result.status === 'rejected' && result.reason instanceof TimeoutError
			).length;
			if (timedOutCount > 0) {
				error = `${timedOutCount} Ops widgets timed out. You can refresh individual sections.`;
			}
			if (selectedRequest) {
				selectedRequest = pendingRequests.find((req) => req.id === selectedRequest?.id) ?? null;
				if (!selectedRequest) {
					remediationModalOpen = false;
				}
			}
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to load operations data.';
		}
	}

	async function refreshJobSlo() {
		if (!data.user || !data.session?.access_token) return;
		refreshingJobSlo = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.get(buildJobSloUrl(), { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to load job SLO metrics.');
			}
			jobSlo = await res.json();
			success = 'Job SLO metrics refreshed.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to refresh job SLO metrics.';
		} finally {
			refreshingJobSlo = false;
		}
	}

	async function refreshAcceptanceRuns() {
		if (!data.user || !data.session?.access_token) return;
		refreshingAcceptanceRuns = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.get(buildAcceptanceEvidenceUrl(), { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(
					payload.detail || payload.message || 'Failed to load integration acceptance runs.'
				);
			}
			const payload = (await res.json()) as IntegrationAcceptanceEvidenceResponse;
			acceptanceRuns = buildAcceptanceRuns(payload.items || []);
			success = 'Integration acceptance evidence refreshed.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to refresh integration acceptance evidence.';
		} finally {
			refreshingAcceptanceRuns = false;
		}
	}

	async function captureAcceptanceRuns() {
		if (!data.user || !data.session?.access_token) return;
		if (!hasSelectedAcceptanceChannels()) {
			error = 'Select at least one integration channel (Slack, Jira, or Workflow).';
			success = '';
			return;
		}
		capturingAcceptanceRuns = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.post(
				edgeApiPath('/settings/notifications/acceptance-evidence/capture'),
				{
					include_slack: captureIncludeSlack,
					include_jira: captureIncludeJira,
					include_workflow: captureIncludeWorkflow,
					fail_fast: captureFailFast
				},
				{ headers }
			);
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(
					payload.detail || payload.message || 'Failed to capture integration acceptance run.'
				);
			}
			const payload = (await res.json()) as IntegrationAcceptanceCaptureResponse;
			lastAcceptanceCapture = payload;
			await refreshAcceptanceRuns();
			success = `Integration acceptance run captured (${payload.run_id.slice(0, 8)}...) - ${payload.passed} passed / ${payload.failed} failed.`;
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to capture integration acceptance run.';
		} finally {
			capturingAcceptanceRuns = false;
		}
	}

	async function captureAcceptanceKpisOrThrow(): Promise<AcceptanceKpiCaptureResponse> {
		const headers = getHeaders();
		const res = await api.post(buildAcceptanceKpiCaptureUrl(), undefined, { headers });
		if (!res.ok) {
			const payload = await res.json().catch(() => ({}));
			throw new Error(
				payload.detail || payload.message || 'Failed to capture acceptance KPI evidence.'
			);
		}
		return (await res.json()) as AcceptanceKpiCaptureResponse;
	}

	async function captureIntegrationAcceptanceOrThrow(): Promise<IntegrationAcceptanceCaptureResponse> {
		const headers = getHeaders();
		const res = await api.post(
			edgeApiPath('/settings/notifications/acceptance-evidence/capture'),
			{
				include_slack: captureIncludeSlack,
				include_jira: captureIncludeJira,
				include_workflow: captureIncludeWorkflow,
				fail_fast: captureFailFast
			},
			{ headers }
		);
		if (!res.ok) {
			const payload = await res.json().catch(() => ({}));
			throw new Error(
				payload.detail || payload.message || 'Failed to capture integration acceptance evidence.'
			);
		}
		return (await res.json()) as IntegrationAcceptanceCaptureResponse;
	}

	async function runAcceptanceSuite() {
		if (!data.user || !data.session?.access_token) return;
		if (hasInvalidUnitWindow(unitStartDate, unitEndDate)) {
			error = 'Acceptance KPI date range is invalid: start date must be on or before end date.';
			return;
		}
		if (!hasSelectedAcceptanceChannels()) {
			error = 'Select at least one integration channel (Slack, Jira, or Workflow).';
			success = '';
			return;
		}

		runningAcceptanceSuite = true;
		error = '';
		success = '';
		try {
			capturingAcceptanceKpis = true;
			const kpiPayload = await captureAcceptanceKpisOrThrow();
			lastAcceptanceKpiCapture = kpiPayload;
			acceptanceKpis = kpiPayload.acceptance_kpis;
			await refreshAcceptanceKpiHistory();
			capturingAcceptanceKpis = false;

			capturingAcceptanceRuns = true;
			const integrationPayload = await captureIntegrationAcceptanceOrThrow();
			lastAcceptanceCapture = integrationPayload;
			await refreshAcceptanceRuns();
			capturingAcceptanceRuns = false;

			success = `Acceptance suite captured: KPIs (${kpiPayload.event_id.slice(0, 8)}...) + integrations (${integrationPayload.run_id.slice(0, 8)}...)`;
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to run acceptance suite.';
		} finally {
			capturingAcceptanceKpis = false;
			capturingAcceptanceRuns = false;
			runningAcceptanceSuite = false;
		}
	}

	async function refreshUnitEconomics() {
		if (!data.user || !data.session?.access_token) return;
		if (hasInvalidUnitWindow(unitStartDate, unitEndDate)) {
			error = 'Unit economics date range is invalid: start date must be on or before end date.';
			return;
		}

		refreshingUnitEconomics = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const [settingsRes, unitRes] = await Promise.all([
				api.get(edgeApiPath('/costs/unit-economics/settings'), { headers }),
				api.get(
					buildUnitEconomicsUrl(EDGE_API_BASE, unitStartDate, unitEndDate, unitAlertOnAnomaly),
					{
						headers
					}
				)
			]);

			if (!unitRes.ok) {
				const payload = await unitRes.json().catch(() => ({}));
				throw new Error(
					payload.detail || payload.message || 'Failed to load unit economics metrics.'
				);
			}
			unitEconomics = await unitRes.json();

			if (settingsRes.ok) {
				unitSettings = await settingsRes.json();
			}
			success = 'Unit economics refreshed.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to refresh unit economics.';
		} finally {
			refreshingUnitEconomics = false;
		}
	}

	async function refreshIngestionSla() {
		if (!data.user || !data.session?.access_token) return;
		refreshingIngestionSla = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.get(buildIngestionSlaUrl(), { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to load ingestion SLA.');
			}
			ingestionSla = await res.json();
			success = 'Ingestion SLA refreshed.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to refresh ingestion SLA.';
		} finally {
			refreshingIngestionSla = false;
		}
	}

	async function refreshAcceptanceKpis() {
		if (!data.user || !data.session?.access_token) return;
		if (hasInvalidUnitWindow(unitStartDate, unitEndDate)) {
			error = 'Unit economics date range is invalid: start date must be on or before end date.';
			return;
		}
		refreshingAcceptanceKpis = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.get(buildAcceptanceKpiUrl(), { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to load acceptance KPIs.');
			}
			acceptanceKpis = await res.json();
			success = 'Acceptance KPI evidence refreshed.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to refresh acceptance KPIs.';
		} finally {
			refreshingAcceptanceKpis = false;
		}
	}

	async function refreshAcceptanceKpiHistory() {
		if (!data.user || !data.session?.access_token) return;
		refreshingAcceptanceKpiHistory = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.get(buildAcceptanceKpiHistoryUrl(50), { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(
					payload.detail || payload.message || 'Failed to load acceptance KPI history.'
				);
			}
			const payload = (await res.json()) as AcceptanceKpiEvidenceResponse;
			acceptanceKpiHistory = payload.items || [];
			success = 'Acceptance KPI evidence history refreshed.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to refresh acceptance KPI history.';
		} finally {
			refreshingAcceptanceKpiHistory = false;
		}
	}

	async function captureAcceptanceKpis() {
		if (!data.user || !data.session?.access_token) return;
		if (hasInvalidUnitWindow(unitStartDate, unitEndDate)) {
			error = 'Acceptance KPI date range is invalid: start date must be on or before end date.';
			return;
		}
		capturingAcceptanceKpis = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.post(buildAcceptanceKpiCaptureUrl(), undefined, { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(
					payload.detail || payload.message || 'Failed to capture acceptance KPI evidence.'
				);
			}
			const payload = (await res.json()) as AcceptanceKpiCaptureResponse;
			lastAcceptanceKpiCapture = payload;
			acceptanceKpis = payload.acceptance_kpis;
			success = 'Acceptance KPI evidence captured.';
			void refreshAcceptanceKpiHistory();
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to capture acceptance KPI evidence.';
		} finally {
			capturingAcceptanceKpis = false;
		}
	}

	function buildClosePackageUrl(
		responseFormat: 'json' | 'csv' = 'json',
		enforceFinalized = false
	): string {
		const params = [
			`start_date=${encodeURIComponent(closeStartDate)}`,
			`end_date=${encodeURIComponent(closeEndDate)}`,
			`response_format=${encodeURIComponent(responseFormat)}`,
			`enforce_finalized=${encodeURIComponent(String(enforceFinalized))}`
		];
		if (closeProvider !== 'all') {
			params.push(`provider=${encodeURIComponent(closeProvider)}`);
		}
		return edgeApiPath(`/costs/reconciliation/close-package?${params.join('&')}`);
	}

	function buildRestatementUrl(responseFormat: 'json' | 'csv' = 'json'): string {
		const params = [
			`start_date=${encodeURIComponent(closeStartDate)}`,
			`end_date=${encodeURIComponent(closeEndDate)}`,
			`response_format=${encodeURIComponent(responseFormat)}`
		];
		if (closeProvider !== 'all') {
			params.push(`provider=${encodeURIComponent(closeProvider)}`);
		}
		return edgeApiPath(`/costs/reconciliation/restatements?${params.join('&')}`);
	}

	function parseFilenameFromDisposition(disposition: string | null, fallback: string): string {
		if (!disposition) return fallback;
		const match = disposition.match(/filename="?([^"]+)"?/i);
		if (!match || !match[1]) return fallback;
		return match[1];
	}

	function downloadTextFile(filename: string, content: string, mime: string): void {
		if (typeof window === 'undefined' || typeof URL.createObjectURL !== 'function') {
			return;
		}
		const blob = new Blob([content], { type: mime });
		const url = URL.createObjectURL(blob);
		const link = document.createElement('a');
		link.href = url;
		link.download = filename;
		document.body.appendChild(link);
		link.click();
		link.remove();
		URL.revokeObjectURL(url);
	}

	function normalizeCurrencyCode(value: string): string {
		const normalized = (value || '').trim().toUpperCase();
		return normalized || 'USD';
	}

	function syncInvoiceFormFromClosePackage(pkg: ReconciliationClosePackage | null): void {
		if (!pkg?.invoice_reconciliation) return;
		const inv = pkg.invoice_reconciliation.invoice;
		if (inv) {
			invoiceForm.invoice_number = inv.invoice_number ? String(inv.invoice_number) : '';
			invoiceForm.currency = normalizeCurrencyCode(inv.currency);
			// Keep the editable amount in the original invoice currency.
			invoiceForm.total_amount = Number(inv.total_amount ?? 0);
			invoiceForm.status = inv.status ? String(inv.status) : 'submitted';
			invoiceForm.notes = inv.notes ? String(inv.notes) : '';
			return;
		}

		invoiceForm.invoice_number = '';
		invoiceForm.currency = 'USD';
		const ledgerTotal = Number(pkg.invoice_reconciliation.ledger_final_cost_usd ?? 0);
		invoiceForm.total_amount = Number.isFinite(ledgerTotal) ? ledgerTotal : 0;
		invoiceForm.status = 'submitted';
		invoiceForm.notes = '';
	}

	async function previewClosePackage({ silent = false }: { silent?: boolean } = {}) {
		if (!data.user || !data.session?.access_token) return;
		if (hasInvalidUnitWindow(closeStartDate, closeEndDate)) {
			error = 'Close package date range is invalid: start date must be on or before end date.';
			return;
		}
		refreshingClosePackage = true;
		if (!silent) {
			error = '';
			success = '';
		}
		try {
			const headers = getHeaders();
			const res = await api.get(buildClosePackageUrl('json', false), { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(
					payload.detail || payload.message || 'Failed to load close package preview.'
				);
			}
			closePackage = await res.json();
			syncInvoiceFormFromClosePackage(closePackage);
			if (!silent) {
				success = 'Close package preview refreshed.';
			}
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to refresh close package preview.';
		} finally {
			refreshingClosePackage = false;
		}
	}

	async function saveProviderInvoice(event?: SubmitEvent) {
		event?.preventDefault();
		if (!data.user || !data.session?.access_token) return;
		if (closeProvider === 'all') {
			error = 'Select a provider (AWS/Azure/GCP/SaaS/License/Platform/Hybrid) to store an invoice.';
			return;
		}
		if (hasInvalidUnitWindow(closeStartDate, closeEndDate)) {
			error = 'Invoice period is invalid: start date must be on or before end date.';
			return;
		}

		savingInvoice = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const currency = normalizeCurrencyCode(invoiceForm.currency);
			const total_amount = Number(invoiceForm.total_amount);
			const payload = {
				provider: closeProvider,
				start_date: closeStartDate,
				end_date: closeEndDate,
				currency,
				total_amount,
				invoice_number: invoiceForm.invoice_number.trim() || undefined,
				status: invoiceForm.status.trim() || undefined,
				notes: invoiceForm.notes.trim() || undefined
			};
			const res = await api.post(edgeApiPath('/costs/reconciliation/invoices'), payload, {
				headers
			});
			if (!res.ok) {
				const body = await res.json().catch(() => ({}));
				throw new Error(body.detail || body.message || 'Failed to save provider invoice.');
			}
			await res.json().catch(() => null);
			await previewClosePackage({ silent: true });
			success = 'Invoice saved.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to save provider invoice.';
		} finally {
			savingInvoice = false;
		}
	}

	async function deleteProviderInvoice() {
		if (!data.user || !data.session?.access_token) return;
		const invoiceId = closePackage?.invoice_reconciliation?.invoice?.id;
		if (!invoiceId) return;

		deletingInvoice = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.delete(
				edgeApiPath(`/costs/reconciliation/invoices/${encodeURIComponent(invoiceId)}`),
				{ headers }
			);
			if (!res.ok) {
				const body = await res.json().catch(() => ({}));
				throw new Error(body.detail || body.message || 'Failed to delete provider invoice.');
			}
			await res.json().catch(() => null);
			await previewClosePackage({ silent: true });
			success = 'Invoice deleted.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to delete provider invoice.';
		} finally {
			deletingInvoice = false;
		}
	}

	async function downloadAcceptanceKpiJson() {
		if (downloadingAcceptanceJson) return;
		downloadingAcceptanceJson = true;
		error = '';
		success = '';
		try {
			if (!acceptanceKpis) {
				await refreshAcceptanceKpis();
			}
			if (!acceptanceKpis) {
				throw new Error('No acceptance KPI data available to export.');
			}
			const filename = `acceptance-kpis-${acceptanceKpis.start_date}-${acceptanceKpis.end_date}.json`;
			downloadTextFile(filename, JSON.stringify(acceptanceKpis, null, 2), 'application/json');
			success = 'Acceptance KPI JSON downloaded.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to export acceptance KPI JSON.';
		} finally {
			downloadingAcceptanceJson = false;
		}
	}

	async function downloadAcceptanceKpiCsv() {
		if (!data.user || !data.session?.access_token || downloadingAcceptanceCsv) return;
		downloadingAcceptanceCsv = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.get(buildAcceptanceKpiUrl('csv'), { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(
					payload.detail || payload.message || 'Failed to export acceptance KPI CSV.'
				);
			}
			const content = await res.text();
			const filename = parseFilenameFromDisposition(
				res.headers.get('content-disposition'),
				`acceptance-kpis-${unitStartDate}-${unitEndDate}.csv`
			);
			downloadTextFile(filename, content, 'text/csv');
			success = 'Acceptance KPI CSV downloaded.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to export acceptance KPI CSV.';
		} finally {
			downloadingAcceptanceCsv = false;
		}
	}

	async function downloadClosePackageJson() {
		if (!data.user || !data.session?.access_token || downloadingCloseJson) return;
		downloadingCloseJson = true;
		error = '';
		success = '';
		try {
			if (hasInvalidUnitWindow(closeStartDate, closeEndDate)) {
				throw new Error(
					'Close package date range is invalid: start date must be on or before end date.'
				);
			}
			const headers = getHeaders();
			const res = await api.get(buildClosePackageUrl('json', false), { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to fetch close package JSON.');
			}
			closePackage = await res.json();
			syncInvoiceFormFromClosePackage(closePackage);
			const filename = `close-package-${closeStartDate}-${closeEndDate}-${closeProvider}.json`;
			downloadTextFile(filename, JSON.stringify(closePackage, null, 2), 'application/json');
			success = 'Close package JSON downloaded.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to export close package JSON.';
		} finally {
			downloadingCloseJson = false;
		}
	}

	async function downloadClosePackageCsv() {
		if (!data.user || !data.session?.access_token || downloadingCloseCsv) return;
		downloadingCloseCsv = true;
		error = '';
		success = '';
		try {
			if (hasInvalidUnitWindow(closeStartDate, closeEndDate)) {
				throw new Error(
					'Close package date range is invalid: start date must be on or before end date.'
				);
			}
			const headers = getHeaders();
			const res = await api.get(buildClosePackageUrl('csv', false), { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to export close package CSV.');
			}
			const content = await res.text();
			const filename = parseFilenameFromDisposition(
				res.headers.get('content-disposition'),
				`close-package-${closeStartDate}-${closeEndDate}-${closeProvider}.csv`
			);
			downloadTextFile(filename, content, 'text/csv');
			success = 'Close package CSV downloaded.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to export close package CSV.';
		} finally {
			downloadingCloseCsv = false;
		}
	}

	async function downloadRestatementCsv() {
		if (!data.user || !data.session?.access_token || downloadingRestatementCsv) return;
		downloadingRestatementCsv = true;
		error = '';
		success = '';
		try {
			if (hasInvalidUnitWindow(closeStartDate, closeEndDate)) {
				throw new Error(
					'Close package date range is invalid: start date must be on or before end date.'
				);
			}
			const headers = getHeaders();
			const res = await api.get(buildRestatementUrl('csv'), { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to export restatements CSV.');
			}
			const content = await res.text();
			const filename = parseFilenameFromDisposition(
				res.headers.get('content-disposition'),
				`restatements-${closeStartDate}-${closeEndDate}-${closeProvider}.csv`
			);
			downloadTextFile(filename, content, 'text/csv');
			success = 'Restatements CSV downloaded.';
		} catch (e) {
			const err = e as Error;
			error = err.message || 'Failed to export restatements CSV.';
		} finally {
			downloadingRestatementCsv = false;
		}
	}

	async function saveUnitEconomicsSettings(event?: SubmitEvent) {
		event?.preventDefault();
		if (!unitSettings || !data.session?.access_token) return;

		savingUnitSettings = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const payload = {
				default_request_volume: Number(unitSettings.default_request_volume),
				default_workload_volume: Number(unitSettings.default_workload_volume),
				default_customer_volume: Number(unitSettings.default_customer_volume),
				anomaly_threshold_percent: Number(unitSettings.anomaly_threshold_percent)
			};
			const res = await api.put(edgeApiPath('/costs/unit-economics/settings'), payload, {
				headers
			});
			if (!res.ok) {
				const body = await res.json().catch(() => ({}));
				throw new Error(
					body.detail ||
						body.message ||
						'Failed to save unit economics defaults. Admin role is required.'
				);
			}
			unitSettings = await res.json();
			success = 'Unit economics defaults saved.';
			await refreshUnitEconomics();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			savingUnitSettings = false;
		}
	}

	function closeRemediationModal() {
		if (remediationSubmitting) return;
		remediationModalOpen = false;
		selectedRequest = null;
		selectedPolicyPreview = null;
		policyPreviewLoading = false;
		remediationModalError = '';
		remediationModalSuccess = '';
		bypassGracePeriod = false;
	}

	async function previewSelectedPolicy() {
		if (!selectedRequest) return;
		policyPreviewLoading = true;
		remediationModalError = '';
		remediationModalSuccess = '';
		try {
			const headers = getHeaders();
			const res = await api.get(edgeApiPath(`/zombies/policy-preview/${selectedRequest.id}`), {
				headers
			});
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to preview policy decision.');
			}
			selectedPolicyPreview = await res.json();
		} catch (e) {
			const err = e as Error;
			selectedPolicyPreview = null;
			remediationModalError = err.message;
		} finally {
			policyPreviewLoading = false;
		}
	}

	async function openRemediationModal(req: PendingRequest) {
		if (policyPreviewLoading || remediationSubmitting) return;
		selectedRequest = req;
		selectedPolicyPreview = null;
		remediationModalError = '';
		remediationModalSuccess = '';
		bypassGracePeriod = false;
		remediationModalOpen = true;
		await previewSelectedPolicy();
	}

	async function approveSelectedRequest() {
		if (!selectedRequest || remediationSubmitting) return;
		const requestId = selectedRequest.id;
		actingId = requestId;
		remediationSubmitting = true;
		remediationModalError = '';
		remediationModalSuccess = '';
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.post(
				edgeApiPath(`/zombies/approve/${requestId}`),
				{ notes: 'Approved from Ops Center' },
				{ headers }
			);
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to approve request.');
			}
			remediationModalSuccess = `Request ${requestId.slice(0, 8)} approved.`;
			success = remediationModalSuccess;
			await loadOpsData();
		} catch (e) {
			const err = e as Error;
			remediationModalError = err.message;
			error = err.message;
		} finally {
			actingId = null;
			remediationSubmitting = false;
		}
	}

	async function executeSelectedRequest() {
		if (!selectedRequest || remediationSubmitting) return;
		if (selectedRequest.status === 'pending' || selectedRequest.status === 'pending_approval') {
			remediationModalError = 'This request must be approved before it can execute.';
			return;
		}
		const requestId = selectedRequest.id;
		actingId = requestId;
		remediationSubmitting = true;
		remediationModalError = '';
		remediationModalSuccess = '';
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const url = bypassGracePeriod
				? edgeApiPath(`/zombies/execute/${requestId}?bypass_grace_period=true`)
				: edgeApiPath(`/zombies/execute/${requestId}`);
			const res = await api.post(url, undefined, { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to execute request.');
			}
			const payload = (await res.json().catch(() => ({}))) as { status?: string };
			const statusValue = (payload.status || '').toLowerCase();
			if (statusValue === 'scheduled') {
				remediationModalSuccess = `Request ${requestId.slice(0, 8)} scheduled after grace period.`;
			} else if (statusValue === 'completed') {
				remediationModalSuccess = `Request ${requestId.slice(0, 8)} completed.`;
			} else if (statusValue) {
				remediationModalSuccess = `Request ${requestId.slice(0, 8)} status: ${statusValue.replaceAll('_', ' ')}.`;
			} else {
				remediationModalSuccess = `Request ${requestId.slice(0, 8)} execution started.`;
			}
			success = remediationModalSuccess;
			await loadOpsData();
		} catch (e) {
			const err = e as Error;
			remediationModalError = err.message;
			error = err.message;
		} finally {
			actingId = null;
			remediationSubmitting = false;
		}
	}

	async function processPendingJobs() {
		processingJobs = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.post(edgeApiPath('/jobs/process?limit=10'), undefined, { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to process jobs.');
			}
			const payload = await res.json();
			success = `Processed ${payload.processed} jobs (${payload.succeeded} succeeded, ${payload.failed} failed).`;
			await loadOpsData();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			processingJobs = false;
		}
	}

	async function refreshRecommendations() {
		refreshingStrategies = true;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.post(edgeApiPath('/strategies/refresh'), undefined, { headers });
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to refresh recommendations.');
			}
			const payload = await res.json();
			success = payload.message || 'Strategy refresh completed.';
			await loadOpsData();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			refreshingStrategies = false;
		}
	}

	async function applyRecommendation(id: string) {
		actingId = id;
		error = '';
		success = '';
		try {
			const headers = getHeaders();
			const res = await api.post(edgeApiPath(`/strategies/apply/${id}`), undefined, {
				headers
			});
			if (!res.ok) {
				const payload = await res.json().catch(() => ({}));
				throw new Error(payload.detail || payload.message || 'Failed to apply recommendation.');
			}
			success = `Recommendation ${id.slice(0, 8)} marked as applied.`;
			await loadOpsData();
		} catch (e) {
			const err = e as Error;
			error = err.message;
		} finally {
			actingId = null;
		}
	}

	onMount(() => {
		void loadOpsData();
	});
</script>

<svelte:head>
	<title>Ops Center | Valdrix</title>
</svelte:head>

<div class="space-y-8">
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-bold mb-1">Ops Center</h1>
			<p class="text-ink-400 text-sm">
				Operate remediation approvals, background jobs, and strategy recommendations.
			</p>
		</div>
	</div>

	<AuthGate authenticated={!!data.user} action="access operations">
		{#if loading}
			<div class="card">
				<div class="skeleton h-6 w-64 mb-4"></div>
				<div class="skeleton h-4 w-full mb-2"></div>
				<div class="skeleton h-4 w-4/5"></div>
			</div>
		{:else}
			{#if error}
				<div class="card border-danger-500/50 bg-danger-500/10">
					<p class="text-danger-400">{error}</p>
				</div>
			{/if}
			{#if success}
				<div class="card border-success-500/50 bg-success-500/10">
					<p class="text-success-400">{success}</p>
				</div>
			{/if}

			<div class="grid gap-5 md:grid-cols-5">
				<div class="card card-stat">
					<p class="text-xs text-ink-400 uppercase tracking-wide">Pending Remediation</p>
					<p class="text-3xl font-bold text-warning-400">{pendingRequests.length}</p>
				</div>
				<div class="card card-stat">
					<p class="text-xs text-ink-400 uppercase tracking-wide">Jobs Pending</p>
					<p class="text-3xl font-bold text-accent-400">{jobStatus?.pending ?? 0}</p>
				</div>
				<div class="card card-stat">
					<p class="text-xs text-ink-400 uppercase tracking-wide">Jobs Running</p>
					<p class="text-3xl font-bold text-warning-400">{jobStatus?.running ?? 0}</p>
				</div>
				<div class="card card-stat">
					<p class="text-xs text-ink-400 uppercase tracking-wide">Jobs Failed</p>
					<p class="text-3xl font-bold text-danger-400">{jobStatus?.failed ?? 0}</p>
				</div>
				<div class="card card-stat">
					<p class="text-xs text-ink-400 uppercase tracking-wide">Open Strategies</p>
					<p class="text-3xl font-bold text-success-400">{recommendations.length}</p>
				</div>
			</div>

			<div class="card space-y-5">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div>
						<h2 class="text-lg font-semibold">Unit Economics Monitor</h2>
						<p class="text-xs text-ink-400">
							Track cost-per-request/workload/customer versus a previous window baseline.
						</p>
					</div>
					<div class="flex items-end gap-2">
						<label class="text-xs text-ink-400">
							<span class="block mb-1">Start</span>
							<input class="input text-xs" type="date" bind:value={unitStartDate} />
						</label>
						<label class="text-xs text-ink-400">
							<span class="block mb-1">End</span>
							<input class="input text-xs" type="date" bind:value={unitEndDate} />
						</label>
						<label class="flex items-center gap-2 text-xs text-ink-400 mb-1">
							<input type="checkbox" bind:checked={unitAlertOnAnomaly} />
							Alert on anomaly
						</label>
						<button
							class="btn btn-secondary text-xs"
							disabled={refreshingUnitEconomics}
							onclick={refreshUnitEconomics}
						>
							{refreshingUnitEconomics ? 'Refreshing...' : 'Refresh Unit Metrics'}
						</button>
					</div>
				</div>

				{#if unitEconomics}
					<div class="grid gap-3 md:grid-cols-4">
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Current Window Cost</p>
							<p class="text-2xl font-bold text-ink-100">{formatUsd(unitEconomics.total_cost)}</p>
						</div>
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Baseline Cost</p>
							<p class="text-2xl font-bold text-ink-100">
								{formatUsd(unitEconomics.baseline_total_cost)}
							</p>
						</div>
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Threshold</p>
							<p class="text-2xl font-bold text-accent-400">
								{unitEconomics.threshold_percent.toFixed(2)}%
							</p>
						</div>
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Anomalies</p>
							<p
								class={`text-2xl font-bold ${unitEconomics.anomaly_count > 0 ? 'text-danger-400' : 'text-success-400'}`}
							>
								{unitEconomics.anomaly_count}
							</p>
						</div>
					</div>

					<div class="overflow-x-auto">
						<table class="table">
							<thead>
								<tr>
									<th>Metric</th>
									<th>Denominator</th>
									<th>Current Cost/Unit</th>
									<th>Baseline Cost/Unit</th>
									<th>Delta</th>
									<th>Status</th>
								</tr>
							</thead>
							<tbody>
								{#if unitEconomics.metrics.length === 0}
									<tr>
										<td colspan="6" class="text-ink-400 text-center py-4">
											No unit metrics available for this window.
										</td>
									</tr>
								{:else}
									{#each unitEconomics.metrics as metric (metric.metric_key)}
										<tr>
											<td class="text-sm">{metric.label}</td>
											<td>{formatNumber(metric.denominator, 2)}</td>
											<td>{formatUsd(metric.cost_per_unit)}</td>
											<td>{formatUsd(metric.baseline_cost_per_unit)}</td>
											<td class={unitDeltaClass(metric)}>{formatDelta(metric.delta_percent)}</td>
											<td class={metric.is_anomalous ? 'text-danger-400' : 'text-success-400'}>
												{metric.is_anomalous ? 'Anomalous' : 'Normal'}
											</td>
										</tr>
									{/each}
								{/if}
							</tbody>
						</table>
					</div>
				{:else}
					<p class="text-sm text-ink-400">
						Unit economics data is unavailable for the selected window. Try refreshing.
					</p>
				{/if}

				{#if unitSettings}
					<form class="space-y-3" onsubmit={saveUnitEconomicsSettings}>
						<h3 class="text-sm font-semibold text-ink-200">Default Unit Volumes</h3>
						<p class="text-xs text-ink-500">
							Admins can set baseline denominators used when query overrides are not provided.
						</p>
						<div class="grid gap-3 md:grid-cols-4">
							<label class="text-xs text-ink-400">
								<span class="block mb-1">Request Volume</span>
								<input
									class="input text-xs"
									type="number"
									min="0.0001"
									step="0.0001"
									bind:value={unitSettings.default_request_volume}
								/>
							</label>
							<label class="text-xs text-ink-400">
								<span class="block mb-1">Workload Volume</span>
								<input
									class="input text-xs"
									type="number"
									min="0.0001"
									step="0.0001"
									bind:value={unitSettings.default_workload_volume}
								/>
							</label>
							<label class="text-xs text-ink-400">
								<span class="block mb-1">Customer Volume</span>
								<input
									class="input text-xs"
									type="number"
									min="0.0001"
									step="0.0001"
									bind:value={unitSettings.default_customer_volume}
								/>
							</label>
							<label class="text-xs text-ink-400">
								<span class="block mb-1">Anomaly Threshold %</span>
								<input
									class="input text-xs"
									type="number"
									min="0.01"
									step="0.01"
									bind:value={unitSettings.anomaly_threshold_percent}
								/>
							</label>
						</div>
						<div class="flex justify-end">
							<button class="btn btn-primary text-xs" type="submit" disabled={savingUnitSettings}>
								{savingUnitSettings ? 'Saving...' : 'Save Defaults'}
							</button>
						</div>
					</form>
				{/if}
			</div>

			<div class="card space-y-4">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div>
						<h2 class="text-lg font-semibold">Cost Ingestion SLA</h2>
						<p class="text-xs text-ink-400">
							Track ingestion reliability and processing latency against a 95% success target.
						</p>
					</div>
					<div class="flex items-end gap-2">
						<label class="text-xs text-ink-400">
							<span class="block mb-1">Window</span>
							<select
								class="input text-xs"
								bind:value={ingestionSlaWindowHours}
								aria-label="SLA Window"
							>
								<option value={24}>Last 24h</option>
								<option value={72}>Last 72h</option>
								<option value={168}>Last 7d</option>
							</select>
						</label>
						<button
							class="btn btn-secondary text-xs"
							disabled={refreshingIngestionSla}
							onclick={refreshIngestionSla}
						>
							{refreshingIngestionSla ? 'Refreshing...' : 'Refresh SLA'}
						</button>
					</div>
				</div>

				{#if ingestionSla}
					<div class="flex items-center gap-2">
						<span class={ingestionSlaBadgeClass(ingestionSla)}>
							{ingestionSla.meets_sla ? 'SLA Healthy' : 'SLA At Risk'}
						</span>
						<span class="text-xs text-ink-500">
							{ingestionSla.success_rate_percent.toFixed(2)}% success ({ingestionSla.successful_jobs}/
							{ingestionSla.total_jobs} jobs)
						</span>
					</div>
					<div class="grid gap-3 md:grid-cols-5">
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Jobs (Window)</p>
							<p class="text-2xl font-bold text-ink-100">{ingestionSla.total_jobs}</p>
						</div>
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Failed Jobs</p>
							<p class="text-2xl font-bold text-danger-400">{ingestionSla.failed_jobs}</p>
						</div>
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Records Ingested</p>
							<p class="text-2xl font-bold text-accent-400">
								{formatNumber(ingestionSla.records_ingested, 0)}
							</p>
						</div>
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Avg Duration</p>
							<p class="text-2xl font-bold text-ink-100">
								{formatDuration(ingestionSla.avg_duration_seconds)}
							</p>
						</div>
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">P95 Duration</p>
							<p class="text-2xl font-bold text-warning-400">
								{formatDuration(ingestionSla.p95_duration_seconds)}
							</p>
						</div>
					</div>
					<p class="text-xs text-ink-500">
						Latest completed ingestion: {formatDate(ingestionSla.latest_completed_at)}
					</p>
				{:else}
					<p class="text-sm text-ink-400">
						No ingestion SLA data is available for this window yet.
					</p>
				{/if}
			</div>

			<div class="card space-y-4">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div>
						<h2 class="text-lg font-semibold">Job Reliability SLO</h2>
						<p class="text-xs text-ink-400">
							Admin-only reliability view for background jobs (success rate + duration tails).
						</p>
					</div>
					<div class="flex items-end gap-2">
						<label class="text-xs text-ink-400">
							<span class="block mb-1">Window</span>
							<select
								class="input text-xs"
								bind:value={jobSloWindowHours}
								aria-label="Job SLO Window"
							>
								<option value={24}>Last 24h</option>
								<option value={72}>Last 72h</option>
								<option value={168}>Last 7d</option>
							</select>
						</label>
						<button
							class="btn btn-secondary text-xs"
							disabled={refreshingJobSlo}
							onclick={refreshJobSlo}
						>
							{refreshingJobSlo ? 'Refreshing...' : 'Refresh SLO'}
						</button>
					</div>
				</div>

				{#if jobSlo}
					<div class="flex items-center gap-2">
						<span class={jobSloBadgeClass(jobSlo)}>
							{jobSlo.overall_meets_slo ? 'SLO Healthy' : 'SLO At Risk'}
						</span>
						<span class="text-xs text-ink-500">
							{jobSlo.window_hours}h window | target {jobSlo.target_success_rate_percent.toFixed(
								2
							)}%
						</span>
					</div>

					<div class="overflow-x-auto">
						<table class="table">
							<thead>
								<tr>
									<th>Job Type</th>
									<th>Success</th>
									<th>Failed</th>
									<th>Rate</th>
									<th>P95 Duration</th>
									<th>Status</th>
								</tr>
							</thead>
							<tbody>
								{#if jobSlo.metrics.length === 0}
									<tr>
										<td colspan="6" class="text-ink-400 text-center py-4">
											No jobs found in this window yet.
										</td>
									</tr>
								{:else}
									{#each jobSlo.metrics as metric (metric.job_type)}
										<tr>
											<td class="text-sm">{metric.job_type}</td>
											<td class="text-sm text-ink-200">
												{metric.successful_jobs}/{metric.total_jobs}
											</td>
											<td class="text-sm text-danger-400">{metric.failed_jobs}</td>
											<td class="text-sm">{metric.success_rate_percent.toFixed(2)}%</td>
											<td class="text-sm">{formatDuration(metric.p95_duration_seconds ?? null)}</td>
											<td>
												<span class={jobSloMetricBadgeClass(metric)}>
													{metric.meets_slo ? 'On Target' : 'Off Target'}
												</span>
											</td>
										</tr>
									{/each}
								{/if}
							</tbody>
						</table>
					</div>
				{:else}
					<p class="text-sm text-ink-400">
						Job SLO metrics are unavailable (admin-only) or no data exists yet.
					</p>
				{/if}
			</div>

			<div class="card space-y-4">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div>
						<h2 class="text-lg font-semibold">Acceptance KPI Evidence</h2>
						<p class="text-xs text-ink-400">
							Production sign-off signals for ingestion reliability, chargeback coverage, and unit
							economics stability, plus ledger data-quality (normalization + canonical mapping
							coverage).
						</p>
					</div>
					<div class="flex items-center gap-2">
						<button
							class="btn btn-primary text-xs"
							disabled={capturingAcceptanceKpis}
							onclick={captureAcceptanceKpis}
						>
							{capturingAcceptanceKpis ? 'Capturing...' : 'Capture KPI Evidence'}
						</button>
						<button
							class="btn btn-secondary text-xs"
							disabled={downloadingAcceptanceJson}
							onclick={downloadAcceptanceKpiJson}
						>
							{downloadingAcceptanceJson ? 'Exporting...' : 'Download JSON'}
						</button>
						<button
							class="btn btn-secondary text-xs"
							disabled={downloadingAcceptanceCsv}
							onclick={downloadAcceptanceKpiCsv}
						>
							{downloadingAcceptanceCsv ? 'Exporting...' : 'Download CSV'}
						</button>
						<button
							class="btn btn-secondary text-xs"
							disabled={refreshingAcceptanceKpis}
							onclick={refreshAcceptanceKpis}
						>
							{refreshingAcceptanceKpis ? 'Refreshing...' : 'Refresh KPI Evidence'}
						</button>
						<button
							class="btn btn-secondary text-xs"
							disabled={refreshingAcceptanceKpiHistory}
							onclick={refreshAcceptanceKpiHistory}
						>
							{refreshingAcceptanceKpiHistory ? 'Refreshing...' : 'Refresh History'}
						</button>
					</div>
				</div>
				{#if acceptanceKpis}
					<div class="flex items-center gap-2">
						<span
							class={acceptanceKpis.all_targets_met ? 'badge badge-success' : 'badge badge-warning'}
						>
							{acceptanceKpis.all_targets_met ? 'All Targets Met' : 'Gaps Open'}
						</span>
						<span class="text-xs text-ink-500">
							{acceptanceKpis.start_date} -> {acceptanceKpis.end_date} | Tier {acceptanceKpis.tier.toUpperCase()}
							|
							{acceptanceKpis.available_metrics} active metrics
						</span>
					</div>
					<div class="overflow-x-auto">
						<table class="table">
							<thead>
								<tr>
									<th>Metric</th>
									<th>Target</th>
									<th>Actual</th>
									<th>Status</th>
								</tr>
							</thead>
							<tbody>
								{#each acceptanceKpis.metrics as metric (metric.key)}
									<tr>
										<td class="text-sm">{metric.label}</td>
										<td class="text-xs text-ink-400">{metric.target}</td>
										<td class="text-xs">{metric.actual}</td>
										<td>
											<span class={acceptanceBadgeClass(metric)}>
												{#if !metric.available}
													Unavailable
												{:else if metric.meets_target}
													On Target
												{:else}
													Off Target
												{/if}
											</span>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<div class="space-y-2">
						<div class="flex flex-wrap items-center justify-between gap-2">
							<p class="text-xs text-ink-400">
								Captured snapshots (audit-grade). Latest shown first.
							</p>
							{#if lastAcceptanceKpiCapture}
								<p class="text-xs text-ink-500">
									Last captured: {formatDate(lastAcceptanceKpiCapture.captured_at)}
								</p>
							{/if}
						</div>
						{#if acceptanceKpiHistory.length > 0}
							<div class="space-y-2">
								{#each acceptanceKpiHistory.slice(0, 5) as item (item.event_id)}
									<div class="flex flex-wrap items-center justify-between gap-2 text-xs">
										<div class="flex items-center gap-2">
											<span class="text-ink-300">{formatDate(item.captured_at)}</span>
											<span
												class={item.acceptance_kpis.all_targets_met
													? 'badge badge-success'
													: 'badge badge-warning'}
											>
												{item.acceptance_kpis.all_targets_met ? 'All Targets Met' : 'Gaps Open'}
											</span>
										</div>
										<span class="text-ink-500">
											Run {item.run_id ? item.run_id.slice(0, 8) : 'unknown'}
										</span>
									</div>
								{/each}
							</div>
						{:else}
							<p class="text-xs text-ink-400">No captured KPI snapshots yet.</p>
						{/if}
					</div>
				{:else}
					<p class="text-sm text-ink-400">Acceptance KPIs are currently unavailable.</p>
				{/if}
			</div>

			<div class="card space-y-4">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div>
						<h2 class="text-lg font-semibold">Integration Acceptance Runs</h2>
						<p class="text-xs text-ink-400">
							Latest tenant-scoped Slack/Jira/workflow connectivity evidence captured in audit logs.
						</p>
					</div>
					<div class="flex items-center gap-2">
						<button
							class="btn btn-primary text-xs"
							disabled={runningAcceptanceSuite ||
								capturingAcceptanceRuns ||
								capturingAcceptanceKpis ||
								refreshingAcceptanceRuns ||
								refreshingAcceptanceKpiHistory ||
								!hasSelectedAcceptanceChannels()}
							onclick={runAcceptanceSuite}
						>
							{runningAcceptanceSuite ? 'Running...' : 'Run Full Suite'}
						</button>
						<button
							class="btn btn-secondary text-xs"
							disabled={capturingAcceptanceRuns ||
								refreshingAcceptanceRuns ||
								!hasSelectedAcceptanceChannels()}
							onclick={captureAcceptanceRuns}
						>
							{capturingAcceptanceRuns ? 'Running...' : 'Run Checks'}
						</button>
						<button
							class="btn btn-secondary text-xs"
							disabled={refreshingAcceptanceRuns || capturingAcceptanceRuns}
							onclick={refreshAcceptanceRuns}
						>
							{refreshingAcceptanceRuns ? 'Refreshing...' : 'Refresh Runs'}
						</button>
					</div>
				</div>
				<div class="grid gap-3 md:grid-cols-4">
					<label class="flex items-center gap-2 text-xs text-ink-300 cursor-pointer">
						<input
							type="checkbox"
							class="toggle"
							aria-label="Include Slack checks"
							bind:checked={captureIncludeSlack}
							disabled={capturingAcceptanceRuns}
						/>
						<span>Include Slack</span>
					</label>
					<label class="flex items-center gap-2 text-xs text-ink-300 cursor-pointer">
						<input
							type="checkbox"
							class="toggle"
							aria-label="Include Jira checks"
							bind:checked={captureIncludeJira}
							disabled={capturingAcceptanceRuns}
						/>
						<span>Include Jira</span>
					</label>
					<label class="flex items-center gap-2 text-xs text-ink-300 cursor-pointer">
						<input
							type="checkbox"
							class="toggle"
							aria-label="Include Workflow checks"
							bind:checked={captureIncludeWorkflow}
							disabled={capturingAcceptanceRuns}
						/>
						<span>Include Workflow</span>
					</label>
					<label class="flex items-center gap-2 text-xs text-ink-300 cursor-pointer">
						<input
							type="checkbox"
							class="toggle"
							aria-label="Fail fast checks"
							bind:checked={captureFailFast}
							disabled={capturingAcceptanceRuns}
						/>
						<span>Fail fast</span>
					</label>
				</div>
				{#if lastAcceptanceCapture}
					<div class="rounded-lg border border-ink-700/60 bg-ink-900/30 px-3 py-2 text-xs">
						<div class="flex flex-wrap items-center gap-2">
							<span class={acceptanceRunStatusClass(lastAcceptanceCapture.overall_status)}>
								{lastAcceptanceCapture.overall_status.replaceAll('_', ' ').toUpperCase()}
							</span>
							<span class="text-ink-400">
								Last run {lastAcceptanceCapture.run_id.slice(0, 8)}...: {lastAcceptanceCapture.passed}
								passed / {lastAcceptanceCapture.failed} failed
							</span>
						</div>
					</div>
				{/if}
				{#if acceptanceRuns.length > 0}
					<div class="overflow-x-auto">
						<table class="table">
							<thead>
								<tr>
									<th>Run</th>
									<th>Status</th>
									<th>Channels</th>
									<th>Actor</th>
									<th>Captured</th>
								</tr>
							</thead>
							<tbody>
								{#each acceptanceRuns.slice(0, 10) as run (run.runId)}
									<tr>
										<td class="font-mono text-xs">
											{run.runId.slice(0, 8)}...
										</td>
										<td>
											<div class="flex items-center gap-2">
												<span class={acceptanceRunStatusClass(run.overallStatus)}>
													{run.overallStatus.replaceAll('_', ' ').toUpperCase()}
												</span>
												<span class="text-xs text-ink-500">
													{run.passed} passed / {run.failed} failed
												</span>
											</div>
										</td>
										<td>
											<div class="flex flex-wrap gap-1">
												{#each run.channels as channel (channel.channel)}
													<span
														class={channel.success ? 'badge badge-success' : 'badge badge-error'}
														title={channel.message || ''}
													>
														{channel.channel}: {channel.success ? 'OK' : 'FAIL'}
													</span>
												{/each}
											</div>
											{#if run.channels.length === 0}
												<span class="text-xs text-ink-500">
													{run.checkedChannels.join(', ') || 'No channels recorded'}
												</span>
											{/if}
										</td>
										<td class="text-xs text-ink-500">{run.actorEmail || '-'}</td>
										<td class="text-xs text-ink-500">{formatDate(run.capturedAt)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{:else}
					<p class="text-sm text-ink-400">
						No integration acceptance runs captured yet. Use Settings -> Notifications to run tests.
					</p>
				{/if}
			</div>

			<div class="card space-y-4">
				<div class="flex flex-wrap items-center justify-between gap-3">
					<div>
						<h2 class="text-lg font-semibold">Reconciliation Close Workflow</h2>
						<p class="text-xs text-ink-400">
							Preview month-end close readiness and export close/restatement evidence artifacts.
						</p>
					</div>
					<div class="flex items-end gap-2">
						<label class="text-xs text-ink-400">
							<span class="block mb-1">Start</span>
							<input class="input text-xs" type="date" bind:value={closeStartDate} />
						</label>
						<label class="text-xs text-ink-400">
							<span class="block mb-1">End</span>
							<input class="input text-xs" type="date" bind:value={closeEndDate} />
						</label>
						<label class="text-xs text-ink-400">
							<span class="block mb-1">Provider</span>
							<select class="input text-xs" bind:value={closeProvider}>
								<option value="all">All</option>
								<option value="aws">AWS</option>
								<option value="azure">Azure</option>
								<option value="gcp">GCP</option>
								<option value="saas">SaaS</option>
								<option value="license">License</option>
								<option value="platform">Platform</option>
								<option value="hybrid">Hybrid</option>
							</select>
						</label>
					</div>
				</div>

				<div class="flex flex-wrap gap-2">
					<button
						class="btn btn-secondary text-xs"
						disabled={refreshingClosePackage}
						onclick={() => previewClosePackage()}
					>
						{refreshingClosePackage ? 'Refreshing...' : 'Preview Close Status'}
					</button>
					<button
						class="btn btn-secondary text-xs"
						disabled={downloadingCloseJson}
						onclick={downloadClosePackageJson}
					>
						{downloadingCloseJson ? 'Exporting...' : 'Download Close JSON'}
					</button>
					<button
						class="btn btn-secondary text-xs"
						disabled={downloadingCloseCsv}
						onclick={downloadClosePackageCsv}
					>
						{downloadingCloseCsv ? 'Exporting...' : 'Download Close CSV'}
					</button>
					<button
						class="btn btn-secondary text-xs"
						disabled={downloadingRestatementCsv}
						onclick={downloadRestatementCsv}
					>
						{downloadingRestatementCsv ? 'Exporting...' : 'Download Restatements CSV'}
					</button>
				</div>

				{#if closePackage}
					<div class="flex items-center gap-2">
						<span class={closeStatusBadgeClass(closePackage.close_status)}>
							{closePackage.close_status.replaceAll('_', ' ').toUpperCase()}
						</span>
						<span class="text-xs text-ink-500">
							{closePackage.period.start_date} -> {closePackage.period.end_date} | {closePackage.package_version}
						</span>
					</div>
					{#if closePackage.invoice_reconciliation}
						<div
							class="rounded-lg border border-ink-700/60 bg-ink-900/20 px-3 py-2 text-xs space-y-1"
						>
							<div class="flex flex-wrap items-center gap-2">
								<span class="badge badge-default">Invoice Reconciliation</span>
								<span
									class={`badge ${closePackage.invoice_reconciliation.status === 'match' ? 'badge-success' : closePackage.invoice_reconciliation.status === 'missing_invoice' ? 'badge-warning' : 'badge-error'}`}
								>
									{closePackage.invoice_reconciliation.status.replaceAll('_', ' ').toUpperCase()}
								</span>
								<span class="text-ink-500">
									Threshold {closePackage.invoice_reconciliation.threshold_percent}%
								</span>
							</div>
							{#if closePackage.invoice_reconciliation.invoice}
								<div class="flex flex-wrap gap-3 text-ink-400">
									<span>
										Invoice total (USD): <span class="text-ink-200"
											>{formatUsd(
												closePackage.invoice_reconciliation.invoice.total_amount_usd
											)}</span
										>
									</span>
									<span>
										Ledger final (USD): <span class="text-ink-200"
											>{formatUsd(
												closePackage.invoice_reconciliation.ledger_final_cost_usd || 0
											)}</span
										>
									</span>
									<span>
										Delta: <span class="text-ink-200"
											>{formatUsd(closePackage.invoice_reconciliation.delta_usd || 0)}</span
										>
									</span>
									<span>
										Delta %: <span class="text-ink-200"
											>{(closePackage.invoice_reconciliation.delta_percent || 0).toFixed(2)}%</span
										>
									</span>
								</div>
							{:else}
								<p class="text-ink-500">
									No invoice stored for this provider/period yet. Add one below to enable
									invoice-linked reconciliation.
								</p>
							{/if}

							<form class="mt-3 grid gap-2 md:grid-cols-6" onsubmit={saveProviderInvoice}>
								<label class="text-xs text-ink-400 md:col-span-2">
									<span class="block mb-1">Invoice #</span>
									<input
										class="input text-xs"
										placeholder="Optional"
										bind:value={invoiceForm.invoice_number}
									/>
								</label>
								<label class="text-xs text-ink-400">
									<span class="block mb-1">Currency</span>
									<input
										class="input text-xs"
										placeholder="USD"
										bind:value={invoiceForm.currency}
									/>
								</label>
								<label class="text-xs text-ink-400">
									<span class="block mb-1">Total</span>
									<input
										class="input text-xs"
										type="number"
										step="0.01"
										min="0"
										bind:value={invoiceForm.total_amount}
									/>
								</label>
								<label class="text-xs text-ink-400">
									<span class="block mb-1">Status</span>
									<select class="input text-xs" bind:value={invoiceForm.status}>
										<option value="submitted">Submitted</option>
										<option value="paid">Paid</option>
										<option value="reconciled">Reconciled</option>
										<option value="disputed">Disputed</option>
										<option value="void">Void</option>
									</select>
								</label>
								<label class="text-xs text-ink-400 md:col-span-6">
									<span class="block mb-1">Notes</span>
									<input
										class="input text-xs"
										placeholder="Optional"
										bind:value={invoiceForm.notes}
									/>
								</label>
								<div class="md:col-span-6 flex flex-wrap items-center gap-2">
									<button class="btn btn-secondary text-xs" type="submit" disabled={savingInvoice}>
										{savingInvoice
											? 'Saving...'
											: closePackage.invoice_reconciliation.invoice
												? 'Update Invoice'
												: 'Save Invoice'}
									</button>
									{#if closePackage.invoice_reconciliation.invoice}
										<button
											class="btn btn-ghost text-xs"
											type="button"
											disabled={deletingInvoice}
											onclick={deleteProviderInvoice}
										>
											{deletingInvoice ? 'Deleting...' : 'Delete'}
										</button>
									{/if}
									<span class="text-xs text-ink-500">
										Note: non-USD invoices require DB exchange rates (Settings -> Billing).
									</span>
								</div>
							</form>
						</div>
					{/if}
					<div class="grid gap-3 md:grid-cols-5">
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Total Records</p>
							<p class="text-2xl font-bold text-ink-100">{closePackage.lifecycle.total_records}</p>
						</div>
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Preliminary</p>
							<p
								class={`text-2xl font-bold ${closePackage.lifecycle.preliminary_records > 0 ? 'text-warning-400' : 'text-success-400'}`}
							>
								{closePackage.lifecycle.preliminary_records}
							</p>
						</div>
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Final</p>
							<p class="text-2xl font-bold text-success-400">
								{closePackage.lifecycle.final_records}
							</p>
						</div>
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Discrepancy %</p>
							<p class="text-2xl font-bold text-warning-400">
								{closePackage.reconciliation.discrepancy_percentage.toFixed(2)}%
							</p>
						</div>
						<div class="card card-stat">
							<p class="text-xs text-ink-400 uppercase tracking-wide">Restatements</p>
							<p class="text-2xl font-bold text-accent-400">{closePackage.restatements.count}</p>
						</div>
					</div>
					<p class="text-xs text-ink-500 font-mono break-all">
						Integrity hash: {closePackage.integrity_hash}
					</p>
				{:else}
					<p class="text-sm text-ink-400">
						No close package preview loaded for the selected period/provider yet.
					</p>
				{/if}
			</div>

			<div class="card">
				<div class="flex items-center justify-between mb-4">
					<h2 class="text-lg font-semibold">Remediation Queue</h2>
				</div>
				{#if pendingRequests.length === 0}
					<p class="text-ink-400 text-sm">No pending remediation requests.</p>
				{:else}
					<div class="overflow-x-auto">
						<table class="table">
							<thead>
								<tr>
									<th>Request</th>
									<th>Resource</th>
									<th>Action</th>
									<th>Savings</th>
									<th>Created</th>
									<th>Controls</th>
								</tr>
							</thead>
							<tbody>
								{#each pendingRequests as req (req.id)}
									<tr>
										<td class="font-mono text-xs">{req.id.slice(0, 8)}...</td>
										<td>
											<div class="text-sm">{req.resource_type}</div>
											<div class="text-xs text-ink-500 font-mono">{req.resource_id}</div>
											<div class="text-xs text-ink-500 capitalize">
												{req.status.replaceAll('_', ' ')}
											</div>
											{#if req.escalation_required}
												<div class="badge badge-warning mt-1 text-[10px]">
													Escalated: {req.escalation_reason || 'Owner approval required'}
												</div>
											{/if}
										</td>
										<td class="capitalize">{req.action.replaceAll('_', ' ')}</td>
										<td>{formatUsd(req.estimated_savings)}</td>
										<td class="text-xs text-ink-500">{formatDate(req.created_at)}</td>
										<td class="flex gap-2">
											<button
												class="btn btn-primary text-xs"
												disabled={actingId === req.id}
												onclick={() => openRemediationModal(req)}
											>
												Review
											</button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>

			<div class="card">
				<div class="flex items-center justify-between mb-4">
					<h2 class="text-lg font-semibold">Background Jobs</h2>
					<div class="flex gap-2">
						<button
							class="btn btn-secondary text-xs"
							disabled={processingJobs}
							onclick={loadOpsData}
						>
							Refresh
						</button>
						<button
							class="btn btn-primary text-xs"
							disabled={processingJobs}
							onclick={processPendingJobs}
						>
							{processingJobs ? 'Processing...' : 'Process Pending'}
						</button>
					</div>
				</div>
				<div class="overflow-x-auto">
					<table class="table">
						<thead>
							<tr>
								<th>Type</th>
								<th>Status</th>
								<th>Attempts</th>
								<th>Created</th>
								<th>Error</th>
							</tr>
						</thead>
						<tbody>
							{#if jobs.length === 0}
								<tr>
									<td colspan="5" class="text-ink-400 text-center py-4">No jobs found.</td>
								</tr>
							{:else}
								{#each jobs as job (job.id)}
									<tr>
										<td class="font-mono text-xs">{job.job_type}</td>
										<td class="capitalize">{job.status}</td>
										<td>{job.attempts}</td>
										<td class="text-xs text-ink-500">{formatDate(job.created_at)}</td>
										<td class="text-xs text-danger-400">{job.error_message || '-'}</td>
									</tr>
								{/each}
							{/if}
						</tbody>
					</table>
				</div>
			</div>

			<div class="card">
				<div class="flex items-center justify-between mb-4">
					<h2 class="text-lg font-semibold">RI/SP Strategy Recommendations</h2>
					<div class="flex gap-2">
						<button class="btn btn-secondary text-xs" onclick={loadOpsData}>Refresh</button>
						<button
							class="btn btn-primary text-xs"
							disabled={refreshingStrategies}
							onclick={refreshRecommendations}
						>
							{refreshingStrategies ? 'Refreshing...' : 'Regenerate'}
						</button>
					</div>
				</div>
				<div class="overflow-x-auto">
					<table class="table">
						<thead>
							<tr>
								<th>Resource</th>
								<th>Region</th>
								<th>Term</th>
								<th>Payment</th>
								<th>Savings</th>
								<th>ROI</th>
								<th>Action</th>
							</tr>
						</thead>
						<tbody>
							{#if recommendations.length === 0}
								<tr>
									<td colspan="7" class="text-ink-400 text-center py-4">
										No open strategy recommendations.
									</td>
								</tr>
							{:else}
								{#each recommendations as rec (rec.id)}
									<tr>
										<td class="text-sm">{rec.resource_type}</td>
										<td class="text-sm">{rec.region}</td>
										<td class="text-sm">{rec.term}</td>
										<td class="text-sm">{rec.payment_option}</td>
										<td class="text-success-400 font-semibold">
											{formatUsd(rec.estimated_monthly_savings)}
										</td>
										<td>{rec.roi_percentage.toFixed(1)}%</td>
										<td>
											<button
												class="btn btn-secondary text-xs"
												disabled={actingId === rec.id}
												onclick={() => applyRecommendation(rec.id)}
											>
												Apply
											</button>
										</td>
									</tr>
								{/each}
							{/if}
						</tbody>
					</table>
				</div>
			</div>
		{/if}
	</AuthGate>
</div>

{#if remediationModalOpen && selectedRequest}
	<div class="fixed inset-0 z-[150] flex items-center justify-center p-4">
		<button
			type="button"
			class="absolute inset-0 bg-ink-950/70 backdrop-blur-sm border-0"
			aria-label="Close remediation modal"
			onclick={closeRemediationModal}
		></button>
		<div
			class="relative w-full max-w-2xl card border border-ink-700"
			role="dialog"
			aria-modal="true"
			aria-label="Remediation review"
		>
			<div class="flex items-center justify-between mb-4">
				<div>
					<h3 class="text-lg font-semibold">Remediation Request Review</h3>
					<p class="text-xs text-ink-400 mt-1 font-mono">{selectedRequest.id}</p>
				</div>
				<button class="btn btn-secondary text-xs" onclick={closeRemediationModal}>Close</button>
			</div>

			<div class="space-y-3 text-sm">
				<div class="text-ink-300">
					<span class="text-ink-500">Resource:</span>
					{selectedRequest.resource_type} ({selectedRequest.resource_id})
				</div>
				{#if selectedRequest.provider}
					<div class="text-ink-300">
						<span class="text-ink-500">Provider:</span>
						{selectedRequest.provider.toUpperCase()}
					</div>
				{/if}
				{#if selectedRequest.region}
					<div class="text-ink-300">
						<span class="text-ink-500">Region:</span>
						{selectedRequest.region}
					</div>
				{/if}
				<div class="text-ink-300">
					<span class="text-ink-500">Action:</span>
					{selectedRequest.action.replaceAll('_', ' ')}
				</div>
				<div class="text-ink-300">
					<span class="text-ink-500">Estimated savings:</span>
					{formatUsd(selectedRequest.estimated_savings)}
				</div>
				<div class="text-ink-300 capitalize">
					<span class="text-ink-500">Status:</span>
					{selectedRequest.status.replaceAll('_', ' ')}
				</div>
				{#if selectedRequest.status === 'scheduled'}
					<div class="text-ink-300">
						<span class="text-ink-500">Scheduled for:</span>
						{formatDate(selectedRequest.scheduled_execution_at || null)}
					</div>
				{/if}
				{#if selectedRequest.escalation_required}
					<div class="badge badge-warning">
						Escalated: {selectedRequest.escalation_reason || 'Owner approval required'}
					</div>
				{/if}

				{#if policyPreviewLoading}
					<div class="card border border-ink-700">
						<div class="skeleton h-4 w-44 mb-2"></div>
						<div class="skeleton h-4 w-full"></div>
					</div>
				{:else if selectedPolicyPreview}
					<div class="flex items-center gap-2">
						<span class={policyDecisionClass(selectedPolicyPreview.decision)}>
							{selectedPolicyPreview.decision.toUpperCase()}
						</span>
						<span class="text-xs text-ink-500 uppercase">{selectedPolicyPreview.tier}</span>
					</div>
					<p class="text-ink-300">{selectedPolicyPreview.summary}</p>
					{#if selectedPolicyPreview.rule_hits.length > 0}
						<div class="rounded-lg border border-ink-700 p-3">
							<p class="text-xs uppercase tracking-wide text-ink-500 mb-2">Rule Hits</p>
							<ul class="space-y-1 text-xs text-ink-300">
								{#each selectedPolicyPreview.rule_hits as hit (hit.rule_id)}
									<li>
										<span class="font-semibold">{hit.rule_id}</span>
										{#if hit.message}
											: {hit.message}
										{/if}
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				{/if}

				{#if remediationModalError}
					<div class="card border-danger-500/50 bg-danger-500/10">
						<p class="text-danger-400 text-xs">{remediationModalError}</p>
					</div>
				{/if}

				{#if remediationModalSuccess}
					<div class="card border-success-500/50 bg-success-500/10">
						<p class="text-success-400 text-xs">{remediationModalSuccess}</p>
					</div>
				{/if}
			</div>

			<div class="mt-5 flex items-center justify-end gap-2">
				{#if selectedRequest.status === 'approved' || selectedRequest.status === 'scheduled'}
					<label class="flex items-center gap-2 text-xs text-ink-400 mr-auto">
						<input type="checkbox" bind:checked={bypassGracePeriod} />
						Bypass grace period
					</label>
				{/if}
				<button
					class="btn btn-secondary text-xs"
					onclick={previewSelectedPolicy}
					disabled={policyPreviewLoading || remediationSubmitting}
				>
					{policyPreviewLoading ? 'Refreshing...' : 'Re-run Preview'}
				</button>
				<button
					class="btn btn-secondary text-xs"
					onclick={approveSelectedRequest}
					disabled={remediationSubmitting ||
						policyPreviewLoading ||
						!(
							selectedRequest.status === 'pending' || selectedRequest.status === 'pending_approval'
						)}
				>
					{remediationSubmitting && actingId === selectedRequest.id ? 'Approving...' : 'Approve'}
				</button>
				<button
					class="btn btn-primary text-xs"
					onclick={executeSelectedRequest}
					disabled={remediationSubmitting ||
						policyPreviewLoading ||
						selectedRequest.status === 'pending' ||
						selectedRequest.status === 'pending_approval'}
				>
					{#if remediationSubmitting && actingId === selectedRequest.id}
						Executing...
					{:else if selectedRequest.status === 'pending'}
						Approve First
					{:else if selectedRequest.status === 'pending_approval'}
						Awaiting Approval
					{:else}
						Execute
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}
