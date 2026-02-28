<script lang="ts">
	import { browser } from '$app/environment';
	import { assets, base } from '$app/paths';
	import { page } from '$app/stores';
	import { onDestroy, onMount } from 'svelte';
	import {
		REALTIME_SIGNAL_SNAPSHOTS,
		lanePositionPercent,
		laneSeverityClass,
		nextSnapshotIndex,
		type SignalLaneId
	} from '$lib/landing/realtimeSignalMap';
	import { emitLandingTelemetry } from '$lib/landing/landingTelemetry';
	import {
		resolveLandingExperiments,
		resolveOrCreateLandingVisitorId,
		shouldIncludeExperimentQueryParams,
		type BuyerPersona,
		type LandingExperimentAssignments
	} from '$lib/landing/landingExperiment';
	import {
		captureLandingAttribution,
		incrementLandingFunnelStage,
		type FunnelStage,
		type LandingAttribution
	} from '$lib/landing/landingFunnel';
	import {
		DEFAULT_LANDING_ROI_INPUTS,
		calculateLandingRoi,
		normalizeLandingRoiInputs
	} from '$lib/landing/roiCalculator';

	const DEFAULT_EXPERIMENT_ASSIGNMENTS: LandingExperimentAssignments = Object.freeze({
		buyerPersonaDefault: 'cto',
		heroVariant: 'control_every_dollar',
		ctaVariant: 'start_free',
		sectionOrderVariant: 'problem_first',
		seed: 'default'
	});

	const HERO_ROLE_CONTEXT: Record<
		BuyerPersona,
		{
			controlTitle: string;
			metricsTitle: string;
			subtitle: string;
			quantPromise: string;
			primaryIntent: string;
		}
	> = Object.freeze({
		cto: {
			controlTitle: 'Stop cloud and software waste before it slows your roadmap.',
			metricsTitle: 'From cost dashboards to fast, owner-led engineering action.',
			subtitle: 'Give engineering a faster path from spend signal to safe execution with clear ownership.',
			quantPromise: 'Target 10-18% controllable spend recovery opportunity in the first 90 days.',
			primaryIntent: 'engineering_control'
		},
		finops: {
			controlTitle: 'Control every dollar with accountable ownership and faster decisions.',
			metricsTitle: 'From visibility reporting to faster financial action.',
			subtitle:
				'Detect spend movement earlier, route accountable owners immediately, and close actions before month-end pressure.',
			quantPromise: 'Target 30-50% fewer late-cycle escalations by formalizing ownership and action paths.',
			primaryIntent: 'finops_governance'
		},
		security: {
			controlTitle: 'Reduce spend and change risk without becoming a delivery bottleneck.',
			metricsTitle: 'From anomalies to safe, reviewable remediation.',
			subtitle:
				'Keep execution guarded by approvals and pre-change checks while engineering keeps shipping.',
			quantPromise: 'Target measurable reduction in risky manual changes by enforcing pre-change checks.',
			primaryIntent: 'security_governance'
		},
		cfo: {
			controlTitle: 'Control cloud margin risk before it reaches the boardroom.',
			metricsTitle: 'From spend metrics to board-ready economic control.',
			subtitle:
				'Tie spend movement to accountable owners so margin conversations shift from surprise to strategy.',
			quantPromise:
				'Target stronger forecast confidence with one decision loop across engineering and finance.',
			primaryIntent: 'executive_briefing'
		}
	});

	const HERO_PROOF_POINTS = Object.freeze([
		{
			title: 'One Economic Truth',
			detail: 'Cloud, SaaS, and license decisions share one operating view.'
		},
		{
			title: 'Execution With Guardrails',
			detail: 'Owners, approvals, and safety checks are built into every action path.'
		},
		{
			title: 'Board-Ready Narrative',
			detail: 'You can explain spend movement, actions, and outcomes in minutes.'
		}
	]);

	const HERO_OUTCOME_CHIPS = Object.freeze([
		{
			label: 'Signal-to-owner handoff',
			value: '< 1 business day target'
		},
		{
			label: 'Controllable waste opportunity',
			value: '10-18% target range'
		},
		{
			label: 'Operating model',
			value: 'Visibility + ownership + action'
		}
	]);

	const SIGNAL_VALUE_CARDS = Object.freeze([
		{
			label: 'Clarity',
			value: 'See what changed and why',
			hint: 'Cloud spend, anomaly, and workload signals in one operational view.'
		},
		{
			label: 'Ownership',
			value: 'Know who decides next',
			hint: 'Clear responsibility across platform, finance, and leadership.'
		},
		{
			label: 'Confidence',
			value: 'Explain decisions quickly',
			hint: 'Teams stay aligned during finance and leadership reviews.'
		}
	]);

	const MICRO_DEMO_STEPS = Object.freeze([
		{
			id: 'detect',
			title: 'Detect',
			detail: 'Realtime cloud anomaly is detected and scoped to impacted workloads.'
		},
		{
			id: 'govern',
			title: 'Assess',
			detail: 'Risk checks and entitlement context evaluate blast radius before execution.'
		},
		{
			id: 'approve',
			title: 'Approve',
			detail: 'Accountable owner approves with explicit decision context and clear impact.'
		},
		{
			id: 'prove',
			title: 'Confirm',
			detail: 'Outcomes are captured so finance and engineering can measure impact quickly.'
		}
	]);

	const CLOUD_HOOK_STATES = Object.freeze([
		{
			id: 'without',
			title: 'Without Valdrics',
			subtitle: 'Reactive cloud cost operations',
			ahaMoment: 'Anomalies surface late, ownership is unclear, and teams react under pressure.',
				points: [
					'Spend spikes are discovered after the billing cycle.',
					'Remediation ownership is ambiguous across teams.',
					'Cost actions execute ad hoc, and outcomes are hard to track.'
				],
			metrics: [
				{ label: 'Signal Lag', value: 'After invoice close' },
				{ label: 'Decision Owner', value: 'Unclear' },
				{ label: 'Execution Safety', value: 'Inconsistent' }
			]
		},
			{
				id: 'with',
				title: 'With Valdrics',
				subtitle: 'Controlled cloud economics',
				ahaMoment:
					'Anomaly detected, owner assigned, risk checked, and action approved in one flow.',
				points: [
					'Realtime anomalies route to a named accountable owner.',
					'Safety checks run before every change.',
					'Decision history is easy to share with finance and leadership.'
				],
				metrics: [
					{ label: 'Signal Lag', value: 'Realtime' },
					{ label: 'Decision Owner', value: 'Explicit' },
					{ label: 'Execution Safety', value: 'Guardrailed' }
				]
			}
		]);

	const EXECUTIVE_CONFIDENCE_POINTS = Object.freeze([
		{
			kicker: 'Decision Quality',
			title: 'Teams decide faster with less friction',
			detail: 'Economic controls are clear, reviewable, and consistently applied across teams.'
		},
		{
			kicker: 'Execution',
			title: 'Actions stay safe and accountable',
			detail: 'Change flows remain safe with clear ownership and explicit approvals.'
		},
		{
			kicker: 'Leadership',
			title: 'Reviews stay focused on outcomes',
			detail: 'Leadership gets a clear narrative from signal to action without noise.'
		}
	]);

	const TRUST_ECOSYSTEM_BADGES = Object.freeze([
		'AWS',
		'Azure',
		'GCP',
		'Microsoft 365',
		'Salesforce',
		'Datadog',
		'Kubernetes'
	]);

	const TRUST_BENCHMARK_OUTCOMES = Object.freeze([
		{
			title: 'Faster economic decisions',
			detail:
				'High-growth teams target a tighter detect-to-decision cycle by unifying ownership and execution context.',
			benchmark: 'Target benchmark: 15-25% faster decision cycles'
		},
		{
			title: 'Fewer finance escalations',
			detail:
				'When ownership and approvals are explicit, month-end surprise escalations can be reduced materially.',
			benchmark: 'Target benchmark: 30-50% fewer late escalations'
		},
		{
			title: 'Clear accountability',
			detail:
				'Teams can move from ambiguous remediation ownership to explicit, role-based accountability across functions.',
			benchmark: 'Target benchmark: owner assigned on every material anomaly'
		}
	]);

	const BUYER_ROLE_VIEWS = Object.freeze([
		{
			id: 'cto' as const,
			label: 'Engineering',
			headline: 'Keep roadmap velocity while controlling cloud and software spend',
			detail:
				'Engineering ships faster when spend risk is managed inside delivery workflows, not escalated after the close.',
			signals: ['Roadmap stability', 'Controlled velocity', 'Fewer escalation loops'],
			thirtyDayOutcomes: [
				'Top spend regressions mapped to accountable owners.',
				'High-risk actions routed through explicit owner sign-off.',
				'Weekly engineering reviews include cost + risk with clear next actions.'
			]
		},
		{
			id: 'finops' as const,
			label: 'FinOps',
			headline: 'Move from reporting to faster financial action',
			detail:
				'Use one operating loop to attribute spend movement, assign ownership, and route remediation clearly.',
			signals: ['Forecast confidence', 'Ownership clarity', 'Faster remediation cycle'],
			thirtyDayOutcomes: [
				'Material anomalies triaged with ownership and deadlines.',
				'Escalation volume reduced through earlier owner-led decisions.',
				'Finance and platform teams review one shared operating narrative.'
			]
		},
		{
			id: 'security' as const,
			label: 'Security',
			headline: 'Reduce risk without becoming a delivery bottleneck',
			detail:
				'Run risk checks before execution with explicit ownership and a clear change history.',
			signals: ['Control adherence', 'Risk visibility', 'Decision traceability'],
			thirtyDayOutcomes: [
				'Risk checks applied before cost-impacting actions.',
				'Approval lineage made explicit for sensitive changes.',
				'Security and platform teams share one review trail.'
			]
		},
		{
			id: 'cfo' as const,
			label: 'CFO',
			headline: 'Protect gross margin with predictable spend decisions',
			detail:
				'Tie cloud actions to financial impact and ownership so executive decisions rely on controlled, trusted signals.',
			signals: ['Margin protection', 'Investment confidence', 'Board-level explainability'],
			thirtyDayOutcomes: [
				'Top margin risks linked to named owners and action dates.',
				'Forecast conversations shift from variance explanation to decision planning.',
				'Board updates include a concise signal-to-action narrative.'
			]
		}
	]);

	const CUSTOMER_PROOF_STORIES = Object.freeze([
		{
			title: 'B2B SaaS Platform',
			before: 'Monthly spend spikes discovered late with no clear owner.',
			after: 'Ownership and approvals moved into the daily operating loop.',
			impact: 'Design-partner pattern: 10-15% controllable spend opportunity surfaced early.'
		},
		{
			title: 'Digital Commerce Group',
			before: 'Finance and engineering escalations happened near close every month.',
			after: 'Spend issues triaged weekly with accountable owners and clear action paths.',
			impact: 'Design-partner pattern: fewer late-cycle escalations and faster decision cycles.'
		},
		{
			title: 'Multi-Region Platform Team',
			before: 'Cloud and SaaS actions were tracked in disconnected workflows.',
			after: 'Cloud+, SaaS, and license decisions executed through one shared operating loop.',
			impact: 'Design-partner pattern: unified operating narrative for leadership reviews.'
		}
	]);

	const CUSTOMER_QUOTES = Object.freeze([
		{
			quote:
				'We stopped debating whose queue a cost issue belongs to. Ownership is now explicit in the workflow.',
			attribution: 'Head of FinOps, Growth-stage SaaS'
		},
		{
			quote:
				'The value is not another dashboard. It is moving from signal to controlled action without drama.',
			attribution: 'VP Engineering, Multi-cloud Platform'
		},
		{
			quote:
				'Leadership reviews got shorter because the economic story is consistent from platform to finance.',
			attribution: 'CFO, Digital Services Organization'
		}
	]);

	const COMPLIANCE_FOUNDATION_BADGES = Object.freeze([
		'Single sign-on (SAML)',
		'SCIM user provisioning',
		'Role-based approvals',
		'Decision history logs',
		'Export-ready records',
		'Tenant isolation'
	]);

	const PLAN_COMPARE_CARDS = Object.freeze([
		{
			id: 'starter',
			name: 'Starter',
			price: 'From $49/mo',
			kicker: 'For focused cloud teams',
			detail: 'Move from static dashboards to owner-routed spend control in one workspace.',
			features: ['Single-cloud start', 'Budgets + anomaly routing', 'Owner action workflows']
		},
		{
			id: 'growth',
			name: 'Growth',
			price: 'From $149/mo',
			kicker: 'For cross-functional FinOps',
			detail: 'Unify cloud, SaaS, and operational ownership with guided execution loops.',
			features: ['Multi-cloud + Cloud+ signals', 'Approval workflows', 'AI-assisted prioritization']
		},
		{
			id: 'pro',
			name: 'Pro',
			price: 'From $299/mo',
			kicker: 'For enterprise teams',
			detail:
				'Scale shared execution across engineering, finance, and leadership with API-first operations.',
			features: ['Automated remediation tracks', 'Expanded API access', 'Priority support']
		}
	]);

	const FREE_TIER_HIGHLIGHTS = Object.freeze([
		'Permanent free tier with usage limits',
		'Cloud and software signal map access',
		'Owner routing and baseline action workflows',
		'BYOK available with tier limits'
	]);

	const CROSS_SURFACE_COVERAGE = Object.freeze([
		{
			title: 'Cloud Infrastructure',
			detail:
				'AWS, Azure, and GCP spend signals are attributed to accountable teams before they become month-end surprises.'
		},
		{
			title: 'GreenOps and Carbon',
			detail:
				'Carbon intensity, budget thresholds, and cleaner-runtime opportunities are tracked alongside cost decisions.'
		},
		{
			title: 'SaaS Spend',
			detail:
				'Vendor usage and expansion pressure are surfaced with ownership context so renewals become controlled decisions.'
		},
		{
			title: 'ITAM and License',
			detail:
				'Entitlement and license posture are reviewed in the same workflow as cloud spend.'
		},
		{
			title: 'Platform Tooling',
			detail:
				'Observability and platform service costs are tied to operating owners and financial outcomes.'
		}
	]);

	const BACKEND_CAPABILITY_PILLARS = Object.freeze([
		{
			title: 'Cost Intelligence and Forecasting',
			detail:
				'Track spend, attribution, anomalies, and forecast movement before variance turns into escalation.'
		},
		{
			title: 'GreenOps Execution',
			detail:
				'Manage carbon budgets, regional intensity, and greener workload scheduling in the same workflow as cost.'
		},
		{
			title: 'Cloud Hygiene and Remediation',
			detail:
				'Detect idle resources, route owner actions, and execute approved remediation with built-in safety checks.'
		},
		{
			title: 'SaaS and ITAM License Control',
			detail:
				'Bring SaaS usage and license posture into one view so reclamation and renewal decisions stay measurable.'
		},
		{
			title: 'Financial Guardrails',
			detail:
				'Apply budgets, credits, reservations, and approval flows so high-impact spend actions stay controlled.'
		},
		{
			title: 'Savings Proof for Leadership',
			detail:
				'Show realized savings events, leaderboard movement, and executive-ready operating outcomes.'
		},
		{
			title: 'Operational Integrations',
			detail:
				'Connect Slack, Teams, Jira, and workflow alerts so decisions move into the channels teams already use.'
		},
		{
			title: 'Security and Identity',
			detail:
				'Support SSO, SCIM provisioning, role-scoped approvals, and audit-ready decision history.'
		}
	]);

	const USD_WHOLE_FORMATTER = new Intl.NumberFormat('en-US', {
		style: 'currency',
		currency: 'USD',
		maximumFractionDigits: 0
	});

	const landingGridX = [...Array(13).keys()];
	const landingGridY = [...Array(9).keys()];
	const SNAPSHOT_ROTATION_MS = 4400;
	const DEMO_ROTATION_MS = 3200;
	const LANDING_SCROLL_MILESTONES = Object.freeze([25, 50, 75, 95]);
	const DEFAULT_SIGNAL_SNAPSHOT = REALTIME_SIGNAL_SNAPSHOTS[0];

	if (!DEFAULT_SIGNAL_SNAPSHOT) {
		throw new Error('Realtime signal map requires at least one snapshot.');
	}

	let signalMapElement: HTMLDivElement | null = null;
	let signalMapInView = $state(true);
	let documentVisible = $state(true);
	let snapshotIndex = $state(0);
	let hookStateIndex = $state(0);
	let buyerRoleIndex = $state(0);
	let demoStepIndex = $state(0);
	let activeLaneId = $state<SignalLaneId | null>(null);
	let visitorId = $state('');
	let pageReferrer = $state('');
	let experiments = $state<LandingExperimentAssignments>(
		resolveLandingExperiments($page.url, DEFAULT_EXPERIMENT_ASSIGNMENTS.seed)
	);
	let attribution = $state<LandingAttribution>({ utm: {} });
	let engagedCaptured = $state(false);
	let rotationInterval: ReturnType<typeof setInterval> | null = null;
	let demoRotationInterval: ReturnType<typeof setInterval> | null = null;
	let roiMonthlySpendUsd = $state(DEFAULT_LANDING_ROI_INPUTS.monthlySpendUsd);
	let roiExpectedReductionPct = $state(DEFAULT_LANDING_ROI_INPUTS.expectedReductionPct);
	let roiRolloutDays = $state(DEFAULT_LANDING_ROI_INPUTS.rolloutDays);
	let roiTeamMembers = $state(DEFAULT_LANDING_ROI_INPUTS.teamMembers);
	let roiBlendedHourlyUsd = $state(DEFAULT_LANDING_ROI_INPUTS.blendedHourlyUsd);
	let roiPlatformAnnualCostUsd = $state(DEFAULT_LANDING_ROI_INPUTS.platformAnnualCostUsd);
	let scenarioWasteWithoutPct = $state(18);
	let scenarioWasteWithPct = $state(7);
	let scenarioWindowMonths = $state(12);
	let scenarioAdjustCaptured = $state(false);

	let activeSnapshot = $derived(
		REALTIME_SIGNAL_SNAPSHOTS[snapshotIndex] ?? DEFAULT_SIGNAL_SNAPSHOT
	);
	let activeHookState = $derived(CLOUD_HOOK_STATES[hookStateIndex] ?? CLOUD_HOOK_STATES[0]);
	let activeBuyerRole = $derived(BUYER_ROLE_VIEWS[buyerRoleIndex] ?? BUYER_ROLE_VIEWS[0]);
	let activeDemoStep = $derived(MICRO_DEMO_STEPS[demoStepIndex] ?? MICRO_DEMO_STEPS[0]);
	let activeSignalLane = $derived(
		activeSnapshot.lanes.find((lane) => lane.id === activeLaneId) ?? activeSnapshot.lanes[0]
	);
	let heroContext = $derived(
		HERO_ROLE_CONTEXT[(activeBuyerRole.id as BuyerPersona) ?? 'finops'] ?? HERO_ROLE_CONTEXT.finops
	);
	let heroTitle = $derived(
		experiments.heroVariant === 'from_metrics_to_control'
			? heroContext.metricsTitle
			: heroContext.controlTitle
	);
	let heroSubtitle = $derived(
		`${heroContext.subtitle} Valdrics helps teams catch overspend early, route the right owner, and act safely before waste compounds.`
	);
	let heroQuantPromise = $derived(heroContext.quantPromise);
	let primaryCtaLabel = $derived(
		experiments.ctaVariant === 'book_briefing' ? 'Book Executive Briefing' : 'Start Free'
	);
	let secondaryCtaLabel = $derived('See Plans');
	let secondaryCtaHref = $derived('#plans');
	let primaryCtaIntent = $derived(
		experiments.ctaVariant === 'book_briefing' ? 'executive_briefing' : heroContext.primaryIntent
	);
	let includeExperimentQueryParams = $derived(
		shouldIncludeExperimentQueryParams($page.url, false)
	);
	let shouldRotateSnapshots = $derived(
		signalMapInView && documentVisible && REALTIME_SIGNAL_SNAPSHOTS.length > 1
	);
	let shouldRotateDemoSteps = $derived(documentVisible && MICRO_DEMO_STEPS.length > 1);
	let roiInputs = $derived(
		normalizeLandingRoiInputs({
			monthlySpendUsd: roiMonthlySpendUsd,
			expectedReductionPct: roiExpectedReductionPct,
			rolloutDays: roiRolloutDays,
			teamMembers: roiTeamMembers,
			blendedHourlyUsd: roiBlendedHourlyUsd,
			platformAnnualCostUsd: roiPlatformAnnualCostUsd
		})
	);
	let roiResult = $derived(calculateLandingRoi(roiInputs));
	let normalizedScenarioWasteWithoutPct = $derived(
		Math.min(35, Math.max(4, Math.round(Number(scenarioWasteWithoutPct) || 0)))
	);
	let normalizedScenarioWasteWithPct = $derived(
		Math.min(
			normalizedScenarioWasteWithoutPct - 1,
			Math.max(1, Math.round(Number(scenarioWasteWithPct) || 0))
		)
	);
	let normalizedScenarioWindowMonths = $derived(
		Math.min(24, Math.max(3, Math.round(Number(scenarioWindowMonths) || 0)))
	);
	let scenarioWasteWithoutUsd = $derived(
		Math.round((roiInputs.monthlySpendUsd * normalizedScenarioWasteWithoutPct) / 100)
	);
	let scenarioWasteWithUsd = $derived(
		Math.round((roiInputs.monthlySpendUsd * normalizedScenarioWasteWithPct) / 100)
	);
	let scenarioWasteRecoveryMonthlyUsd = $derived(
		Math.max(0, scenarioWasteWithoutUsd - scenarioWasteWithUsd)
	);
	let scenarioWasteRecoveryWindowUsd = $derived(
		scenarioWasteRecoveryMonthlyUsd * normalizedScenarioWindowMonths
	);
	let scenarioMaxBarUsd = $derived(Math.max(scenarioWasteWithoutUsd, scenarioWasteWithUsd, 1));
	let scenarioWithoutBarPct = $derived((scenarioWasteWithoutUsd / scenarioMaxBarUsd) * 100);
	let scenarioWithBarPct = $derived((scenarioWasteWithUsd / scenarioMaxBarUsd) * 100);

	$effect(() => {
		const defaultBuyerIndex = BUYER_ROLE_VIEWS.findIndex(
			(role) => role.id === experiments.buyerPersonaDefault
		);
		if (defaultBuyerIndex >= 0) {
			buyerRoleIndex = defaultBuyerIndex;
		}
	});

	$effect(() => {
		if (!activeSignalLane && activeSnapshot.lanes[0]) {
			activeLaneId = activeSnapshot.lanes[0].id;
			return;
		}
		if (activeSignalLane) {
			return;
		}
		activeLaneId = activeSnapshot.lanes[0]?.id ?? null;
	});

	function stopSnapshotRotation() {
		if (!rotationInterval) return;
		clearInterval(rotationInterval);
		rotationInterval = null;
	}

	function stopDemoRotation() {
		if (!demoRotationInterval) return;
		clearInterval(demoRotationInterval);
		demoRotationInterval = null;
	}

	$effect(() => {
		stopSnapshotRotation();
		if (!shouldRotateSnapshots) return;

		rotationInterval = setInterval(() => {
			snapshotIndex = nextSnapshotIndex(snapshotIndex, REALTIME_SIGNAL_SNAPSHOTS.length);
		}, SNAPSHOT_ROTATION_MS);

		return () => stopSnapshotRotation();
	});

	$effect(() => {
		stopDemoRotation();
		if (!shouldRotateDemoSteps) return;

		demoRotationInterval = setInterval(() => {
			demoStepIndex = nextSnapshotIndex(demoStepIndex, MICRO_DEMO_STEPS.length);
		}, DEMO_ROTATION_MS);

		return () => stopDemoRotation();
	});

	onDestroy(() => {
		stopSnapshotRotation();
		stopDemoRotation();
	});

	onMount(() => {
		const storage = browser ? window.localStorage : undefined;
		documentVisible = document.visibilityState === 'visible';
		visitorId = resolveOrCreateLandingVisitorId(storage);
		experiments = resolveLandingExperiments($page.url, visitorId);
		attribution = captureLandingAttribution($page.url, storage);
		pageReferrer = normalizeReferrer(document.referrer);

		incrementLandingFunnelStage('view', storage);
		emitLandingTelemetry('landing_view', 'landing', 'public', buildTelemetryContext('view'));
		emitLandingTelemetry(
			'experiment_exposure',
			'landing',
			`${experiments.heroVariant}|${experiments.ctaVariant}|${experiments.sectionOrderVariant}`,
			buildTelemetryContext('view')
		);

		const handleVisibility = () => {
			documentVisible = document.visibilityState === 'visible';
		};
		document.addEventListener('visibilitychange', handleVisibility);

		let signalMapObserver: IntersectionObserver | null = null;
		if (signalMapElement && typeof IntersectionObserver !== 'undefined') {
			signalMapObserver = new IntersectionObserver(
				(entries) => {
					const entry = entries[0];
					signalMapInView = Boolean(entry?.isIntersecting && entry.intersectionRatio > 0.12);
				},
				{ threshold: [0, 0.12, 0.5] }
			);
			signalMapObserver.observe(signalMapElement);
		}

		const seenSections = new Set<string>();
		let sectionObserver: IntersectionObserver | null = null;
		const landingSections = Array.from(
			document.querySelectorAll<HTMLElement>('[data-landing-section]')
		);
		if (landingSections.length > 0 && typeof IntersectionObserver !== 'undefined') {
			sectionObserver = new IntersectionObserver(
				(entries) => {
					for (const entry of entries) {
						if (!entry.isIntersecting || entry.intersectionRatio < 0.35) {
							continue;
						}
						const sectionId = (entry.target as HTMLElement).dataset.landingSection?.trim();
						if (!sectionId || seenSections.has(sectionId)) {
							continue;
						}

						seenSections.add(sectionId);
						markEngaged();
						emitLandingTelemetry(
							'section_view',
							'landing_section',
							sectionId,
							buildTelemetryContext('engaged')
						);
					}
				},
				{ threshold: [0.15, 0.35, 0.6] }
			);

			for (const section of landingSections) {
				sectionObserver.observe(section);
			}
		}

		const seenMilestones = new Set<number>();
		const handleScroll = () => {
			const root = document.documentElement;
			const maxScrollable = Math.max(1, root.scrollHeight - window.innerHeight);
			const scrollProgress = Math.min(100, Math.max(0, (window.scrollY / maxScrollable) * 100));

			for (const milestone of LANDING_SCROLL_MILESTONES) {
				if (scrollProgress < milestone || seenMilestones.has(milestone)) {
					continue;
				}
				seenMilestones.add(milestone);
				if (milestone >= 50) {
					markEngaged();
				}
				emitLandingTelemetry(
					'scroll_depth',
					'landing',
					`${milestone}`,
					buildTelemetryContext('engaged')
				);
			}
		};

		window.addEventListener('scroll', handleScroll, { passive: true });
		handleScroll();

		return () => {
			document.removeEventListener('visibilitychange', handleVisibility);
			window.removeEventListener('scroll', handleScroll);
			signalMapObserver?.disconnect();
			sectionObserver?.disconnect();
		};
	});

	function normalizeReferrer(referrer: string): string {
		return referrer.trim().slice(0, 200);
	}

	function getStorage(): Storage | undefined {
		if (!browser) return undefined;
		return window.localStorage;
	}

	function buildTelemetryContext(stage?: FunnelStage) {
		return {
			visitorId,
			persona: activeBuyerRole.id,
			funnelStage: stage,
			pagePath: $page.url.pathname,
			referrer: pageReferrer || undefined,
			experiment: {
				hero: experiments.heroVariant,
				cta: experiments.ctaVariant,
				order: experiments.sectionOrderVariant
			},
			utm: attribution.utm
		};
	}

	function markEngaged(): void {
		if (engagedCaptured) return;
		engagedCaptured = true;
		incrementLandingFunnelStage('engaged', getStorage());
		emitLandingTelemetry('landing_engaged', 'landing', 'interactive', buildTelemetryContext('engaged'));
	}

	function buildSignupHref(intent: string, extraParams: Record<string, string> = {}): string {
		const params = new URLSearchParams({
			intent,
			persona: activeBuyerRole.id
		});
		for (const [key, value] of Object.entries(extraParams)) {
			if (value) {
				params.set(key, value);
			}
		}
		if (includeExperimentQueryParams) {
			params.set('exp_hero', experiments.heroVariant);
			params.set('exp_cta', experiments.ctaVariant);
			params.set('exp_order', experiments.sectionOrderVariant);
		}
		params.set('entry', 'landing');
		appendUtmParams(params);
		return `${base}/auth/login?${params.toString()}`;
	}

	function buildPrimaryCtaHref(): string {
		return buildSignupHref(primaryCtaIntent);
	}

	function appendUtmParams(params: URLSearchParams): void {
		if (attribution.utm.source) params.set('utm_source', attribution.utm.source);
		if (attribution.utm.medium) params.set('utm_medium', attribution.utm.medium);
		if (attribution.utm.campaign) params.set('utm_campaign', attribution.utm.campaign);
		if (attribution.utm.term) params.set('utm_term', attribution.utm.term);
		if (attribution.utm.content) params.set('utm_content', attribution.utm.content);
	}

	function buildRoiCtaHref(): string {
		return buildSignupHref('roi_assessment', { source: 'roi' });
	}

	function buildPlanCtaHref(planId: string): string {
		return buildSignupHref('start_plan', { plan: planId, source: 'plans' });
	}

	function buildFreeTierCtaHref(): string {
		return buildSignupHref('free_tier', { plan: 'free', source: 'free_tier' });
	}

	function selectSnapshot(index: number) {
		if (index < 0 || index >= REALTIME_SIGNAL_SNAPSHOTS.length) return;
		snapshotIndex = index;
		markEngaged();
		emitLandingTelemetry(
			'snapshot_select',
			'signal_map',
			REALTIME_SIGNAL_SNAPSHOTS[index]?.id,
			buildTelemetryContext('engaged')
		);
	}

	function selectHookState(index: number) {
		if (index < 0 || index >= CLOUD_HOOK_STATES.length) return;
		hookStateIndex = index;
		markEngaged();
		emitLandingTelemetry(
			'hook_toggle',
			'cloud_hook',
			CLOUD_HOOK_STATES[index]?.id,
			buildTelemetryContext('engaged')
		);
	}

	function selectBuyerRole(index: number) {
		if (index < 0 || index >= BUYER_ROLE_VIEWS.length) return;
		buyerRoleIndex = index;
		markEngaged();
		emitLandingTelemetry(
			'buyer_role_select',
			'buyers',
			BUYER_ROLE_VIEWS[index]?.id,
			buildTelemetryContext('engaged')
		);
	}

	function selectDemoStep(index: number) {
		if (index < 0 || index >= MICRO_DEMO_STEPS.length) return;
		demoStepIndex = index;
		markEngaged();
		emitLandingTelemetry(
			'micro_demo_step',
			'hero_demo',
			MICRO_DEMO_STEPS[index]?.id,
			buildTelemetryContext('engaged')
		);
	}

	function selectSignalLane(laneId: SignalLaneId): void {
		activeLaneId = laneId;
		markEngaged();
		emitLandingTelemetry('lane_focus', 'signal_map', laneId, buildTelemetryContext('engaged'));
	}

	function trackCta(action: string, section: string, value: string): void {
		incrementLandingFunnelStage('cta', getStorage());
		emitLandingTelemetry(action, section, value, buildTelemetryContext('cta'));

		const isSignupIntent =
			value === 'start_free' ||
			value === 'book_briefing' ||
			value.includes('start_plan') ||
			value.includes('start_roi_assessment');
		if (isSignupIntent) {
			incrementLandingFunnelStage('signup_intent', getStorage());
			emitLandingTelemetry('signup_intent', section, value, buildTelemetryContext('signup_intent'));
		}
	}

	function trackScenarioAdjust(control: string): void {
		markEngaged();
		if (scenarioAdjustCaptured) {
			return;
		}
		scenarioAdjustCaptured = true;
		emitLandingTelemetry('scenario_adjust', 'simulator', control, buildTelemetryContext('engaged'));
	}

	function formatUsd(amount: number): string {
		return USD_WHOLE_FORMATTER.format(amount);
	}
</script>

	<div class="landing" itemscope itemtype="https://schema.org/SoftwareApplication">
	<meta itemprop="name" content="Valdrics" />
	<meta itemprop="operatingSystem" content="Web" />
	<meta itemprop="applicationCategory" content="BusinessApplication" />
		<meta
			itemprop="description"
			content="Valdrics helps teams reduce cloud and software spend by turning live spend signals into owner-assigned actions, approvals, and measurable savings."
		/>
	<meta itemprop="url" content={new URL($page.url.pathname, $page.url.origin).toString()} />
	<meta itemprop="image" content={new URL(`${assets}/og-image.png`, $page.url.origin).toString()} />

	<section id="hero" class="landing-hero" data-landing-section="hero">
		<div class="container mx-auto px-6 pt-10 pb-16">
			<div class="landing-hero-grid">
				<div class="landing-copy">
						<div class="landing-kicker fade-in-up" style="animation-delay: 0ms;">
							<span class="badge badge-accent">Cloud + Software Spend Control</span>
							<span class="landing-sep" aria-hidden="true">•</span>
							<span class="landing-kicker-text">See waste early. Act faster. Protect margin.</span>
						</div>

					<div class="landing-problem-hook fade-in-up" style="animation-delay: 70ms;">
						<p class="landing-problem-k">The problem is not visibility. The problem is delayed action.</p>
						<p class="landing-problem-v">
							When ownership is unclear and approvals happen late, controllable waste compounds every week.
						</p>
					</div>

					<h1 class="landing-title fade-in-up" style="animation-delay: 110ms;">
						{heroTitle}
					</h1>

					<p class="landing-subtitle fade-in-up" style="animation-delay: 220ms;">
						{heroSubtitle}
					</p>
					<div class="landing-quant-promise fade-in-up" style="animation-delay: 250ms;">
						<p class="landing-quant-k">What outcomes-focused teams target</p>
						<p class="landing-quant-v">{heroQuantPromise}</p>
					</div>
					<div class="landing-outcome-chips fade-in-up" style="animation-delay: 285ms;">
						{#each HERO_OUTCOME_CHIPS as chip (chip.label)}
							<div class="landing-outcome-chip">
								<p class="landing-outcome-chip-k">{chip.label}</p>
								<p class="landing-outcome-chip-v">{chip.value}</p>
							</div>
						{/each}
					</div>

					<div class="landing-cta fade-in-up" style="animation-delay: 320ms;">
						<a
							href={buildPrimaryCtaHref()}
							class="btn btn-primary text-base px-8 py-3 pulse-glow"
							onclick={() => trackCta('cta_click', 'hero', experiments.ctaVariant)}
						>
							{primaryCtaLabel}
						</a>
						<a
							href={secondaryCtaHref}
							class="btn btn-secondary text-base px-8 py-3"
							onclick={() => trackCta('cta_click', 'hero', 'see_plans')}
						>
							{secondaryCtaLabel}
						</a>
					</div>
					<p class="landing-cta-free-note fade-in-up" style="animation-delay: 338ms;">
						Start free. Upgrade only when ready.
					</p>
						<div class="landing-free-strip fade-in-up" style="animation-delay: 345ms;">
							<span class="landing-free-pill">Permanent Free Tier</span>
							<span>Start at $0, prove value in your own data, then scale when your team is ready.</span>
						</div>
						<p class="landing-cta-note fade-in-up" style="animation-delay: 360ms;">
							One sign-up path. One workspace. Control cloud and software spend from day one.
						</p>
					<a
						href="#simulator"
						class="landing-cta-link fade-in-up"
						style="animation-delay: 390ms;"
						onclick={() => trackCta('cta_click', 'hero', 'open_simulator')}
					>
						Run the spend scenario simulator
					</a>

					<div class="landing-proof fade-in-up" style="animation-delay: 420ms;">
						{#each HERO_PROOF_POINTS as point (point.title)}
							<div class="landing-proof-item">
								<p class="landing-proof-k">{point.title}</p>
								<p class="landing-proof-v">
									{point.detail}
								</p>
							</div>
						{/each}
					</div>
				</div>

				<div class="landing-preview fade-in-up" style="animation-delay: 170ms;">
					<div class="glass-panel landing-preview-card" id="signal-map">
						<div class="landing-preview-header">
							<div class="landing-preview-title">
								<span class="landing-live-dot" aria-hidden="true"></span>
								Realtime Signal Map
							</div>
							<span class="landing-preview-pill">{activeSnapshot.label}</span>
						</div>

						<p class="signal-state-headline">{activeSnapshot.headline}</p>
						<p class="signal-state-sub">{activeSnapshot.decisionSummary}</p>

						<div class="signal-map" class:is-paused={!signalMapInView} bind:this={signalMapElement}>
							<svg
								class="signal-svg"
								viewBox="0 0 640 420"
								role="img"
								aria-labelledby="signal-map-summary"
							>
								<defs>
									<linearGradient id="sigLine" x1="0" y1="0" x2="1" y2="1">
										<stop offset="0" stop-color="var(--color-accent-400)" stop-opacity="0.95" />
										<stop offset="1" stop-color="var(--color-success-400)" stop-opacity="0.72" />
									</linearGradient>
									<radialGradient id="sigGlow" cx="50%" cy="50%" r="60%">
										<stop offset="0" stop-color="var(--color-accent-400)" stop-opacity="0.32" />
										<stop offset="1" stop-color="var(--color-accent-400)" stop-opacity="0" />
									</radialGradient>
								</defs>

								<rect x="0" y="0" width="640" height="420" fill="rgba(0,0,0,0)" />
								<g class="sig-grid">
									{#each landingGridX as xIndex (xIndex)}
										<line x1={xIndex * 54} y1="0" x2={xIndex * 54} y2="420" />
									{/each}
									{#each landingGridY as yIndex (yIndex)}
										<line x1="0" y1={yIndex * 52} x2="640" y2={yIndex * 52} />
									{/each}
								</g>

								<circle cx="320" cy="210" r="160" fill="url(#sigGlow)" />

								{#each activeSnapshot.lanes as lane (lane.id)}
									<line
										class={`sig-link ${laneSeverityClass(lane.severity)}`}
										x1="320"
										y1="210"
										x2={lane.x}
										y2={lane.y}
										stroke="url(#sigLine)"
										stroke-width="2"
										stroke-linecap="round"
										stroke-dasharray="6 10"
									/>
								{/each}

								<circle class="sig-node sig-node--center" cx="320" cy="210" r="12" />
								{#each activeSnapshot.lanes as lane (lane.id)}
									<circle
										class={`sig-node ${laneSeverityClass(lane.severity)} ${activeSignalLane?.id === lane.id ? 'is-focused' : ''}`}
										cx={lane.x}
										cy={lane.y}
										r="8"
									/>
								{/each}
							</svg>

							<div class="signal-label signal-label--center" aria-hidden="true">
								<p class="signal-label-k">Valdrics</p>
								<p class="signal-label-v">Economic Control Plane</p>
							</div>
							{#each activeSnapshot.lanes as lane (lane.id)}
								{@const lanePoint = lanePositionPercent(lane)}
								<button
									type="button"
									class="signal-hotspot"
									class:is-active={activeSignalLane?.id === lane.id}
									style={`left:${lanePoint.leftPct}%; top:${lanePoint.topPct}%;`}
									onclick={() => selectSignalLane(lane.id)}
									aria-label={`Open ${lane.title} lane detail`}
								></button>
							{/each}

								<div id="signal-map-summary" class="sr-only">
									Signal map summary for {activeSnapshot.label}: {activeSnapshot.headline}
									{activeSnapshot.decisionSummary} This view highlights clarity, control, and confidence
									signals for owner-led execution.
								</div>
						</div>

						<div class="signal-lane-controls" role="tablist" aria-label="Realtime signal lane details">
							{#each activeSnapshot.lanes as lane (lane.id)}
								<button
									type="button"
									role="tab"
									id={`signal-lane-tab-${lane.id}`}
									class="signal-lane-btn"
									class:is-active={activeSignalLane?.id === lane.id}
									aria-selected={activeSignalLane?.id === lane.id}
									aria-controls={`signal-lane-panel-${lane.id}`}
									onclick={() => selectSignalLane(lane.id)}
								>
									<span class="signal-lane-btn-title">{lane.title}</span>
									<span class="signal-lane-btn-status">{lane.status}</span>
								</button>
							{/each}
						</div>

						{#if activeSignalLane}
							<div
								class="signal-lane-detail-panel"
								role="tabpanel"
								id={`signal-lane-panel-${activeSignalLane.id}`}
								aria-labelledby={`signal-lane-tab-${activeSignalLane.id}`}
							>
								<p class="signal-lane-detail-k">
									{activeSignalLane.title} · {activeSignalLane.status}
								</p>
								<p class="signal-lane-detail-v">{activeSignalLane.detail}</p>
								<p class="signal-lane-detail-m">Current metric: {activeSignalLane.metric}</p>
							</div>
						{/if}

						<div class="landing-metrics" aria-live="polite">
							{#each SIGNAL_VALUE_CARDS as card (card.label)}
								<div class="landing-metric glass-card">
									<p class="landing-metric-k">{card.label}</p>
									<p class="landing-metric-v">{card.value}</p>
									<p class="landing-metric-h">{card.hint}</p>
								</div>
							{/each}
						</div>

						<div class="landing-demo-strip" aria-label="Guided product moment">
							<p class="landing-demo-k">20-second Cloud Control Demo</p>
							<div class="landing-demo-steps" role="group" aria-label="Control loop demo steps">
								{#each MICRO_DEMO_STEPS as step, index (step.id)}
									<button
										type="button"
										class="landing-demo-step"
										class:is-active={demoStepIndex === index}
										onclick={() => selectDemoStep(index)}
										aria-pressed={demoStepIndex === index}
									>
										{step.title}
									</button>
								{/each}
							</div>
							<p class="landing-demo-detail">{activeDemoStep.detail}</p>
						</div>

						<div class="signal-snapshot-controls" role="group" aria-label="Switch signal snapshots">
							{#each REALTIME_SIGNAL_SNAPSHOTS as snapshot, index (snapshot.id)}
								<button
									type="button"
									class="signal-snapshot-btn"
									class:is-active={snapshotIndex === index}
									onclick={() => selectSnapshot(index)}
									aria-pressed={snapshotIndex === index}
								>
									{snapshot.label}
								</button>
							{/each}
						</div>
					</div>
				</div>
			</div>
		</div>
	</section>

	{#snippet cloudHookSection()}
		<section
			id="cloud-hook"
			class="container mx-auto px-6 pb-20 landing-section-lazy"
			data-landing-section="cloud_hook"
		>
			<div class="landing-hook glass-panel">
				<p class="landing-proof-k">The Cloud Cost Trap</p>
				<h2 class="landing-h2">Visibility alone does not control cloud spend.</h2>
					<p class="landing-section-sub">
						Most teams see cloud waste after the invoice closes. Valdrics creates the aha moment by
						linking each cloud signal to risk checks, ownership, and approved execution in one loop.
					</p>

				<div class="landing-hook-highlight">
					<p class="landing-hook-highlight-k">Aha Moment</p>
					<p class="landing-hook-highlight-v">
						{activeHookState.ahaMoment}
					</p>
				</div>

				<div class="landing-hook-switch" role="group" aria-label="Compare cloud operations">
					{#each CLOUD_HOOK_STATES as state, index (state.id)}
						<button
							type="button"
							class="landing-hook-switch-btn"
							class:is-active={hookStateIndex === index}
							onclick={() => selectHookState(index)}
							aria-pressed={hookStateIndex === index}
						>
							{state.title}
						</button>
					{/each}
				</div>

				<div class="landing-hook-scene" class:is-with={activeHookState.id === 'with'}>
					<p class="landing-hook-sub">{activeHookState.subtitle}</p>
					<ul class="landing-hook-list">
						{#each activeHookState.points as point (point)}
							<li>{point}</li>
						{/each}
					</ul>
					<div class="landing-hook-metrics">
						{#each activeHookState.metrics as metric (metric.label)}
							<div class="landing-hook-metric">
								<p class="landing-hook-metric-k">{metric.label}</p>
								<p class="landing-hook-metric-v">{metric.value}</p>
							</div>
						{/each}
					</div>
				</div>
			</div>
		</section>
	{/snippet}

	{#snippet workflowSection()}
		<section
			id="workflow"
			class="container mx-auto px-6 pb-20 landing-section-lazy"
			data-landing-section="workflow"
		>
				<div class="landing-section-head">
					<h2 class="landing-h2">From signal to savings in one operating flow</h2>
				<p class="landing-section-sub">
					Detect spend risk early, route the right owner, and execute approved actions without slowing
					delivery.
				</p>
			</div>

			<div class="landing-steps">
				<div class="glass-panel landing-step">
					<p class="landing-step-n">01</p>
					<h3 class="landing-h3">Unify your spend signals</h3>
					<p class="landing-p">
						Bring AWS, Azure, GCP, SaaS, and license data into one live operating view.
					</p>
				</div>
					<div class="glass-panel landing-step">
						<p class="landing-step-n">02</p>
						<h3 class="landing-h3">Decide with guardrails</h3>
						<p class="landing-p">
							Apply ownership and risk rules before changes so teams move fast without risky shortcuts.
						</p>
					</div>
				<div class="glass-panel landing-step">
					<p class="landing-step-n">03</p>
					<h3 class="landing-h3">Execute safely, prove impact</h3>
					<p class="landing-p">
						Run approved remediation and keep a clean record for finance and leadership reviews.
					</p>
				</div>
			</div>
		</section>
	{/snippet}

	{#if experiments.sectionOrderVariant === 'workflow_first'}
		{@render workflowSection()}
	{:else}
		{@render cloudHookSection()}
	{/if}

	<section
		id="simulator"
		class="container mx-auto px-6 pb-20 landing-section-lazy"
		data-landing-section="simulator"
	>
			<div class="landing-section-head">
				<h2 class="landing-h2">Realtime spend scenario simulator</h2>
				<p class="landing-section-sub">
					Compare reactive spend behavior versus owner-led execution and see the economic delta instantly.
				</p>
			</div>

		<div class="landing-sim-grid">
			<div class="glass-panel landing-sim-controls">
				<div class="landing-roi-control">
					<label for="sim-waste-without" class="landing-roi-label">Reactive waste rate (%)</label>
					<div class="landing-roi-meta">
						<span>{normalizedScenarioWasteWithoutPct}%</span>
					</div>
					<input
						id="sim-waste-without"
						type="range"
						min="4"
						max="35"
						step="1"
						bind:value={scenarioWasteWithoutPct}
						oninput={() => trackScenarioAdjust('reactive_waste_rate')}
					/>
				</div>
					<div class="landing-roi-control">
						<label for="sim-waste-with" class="landing-roi-label">Managed waste rate (%)</label>
					<div class="landing-roi-meta">
						<span>{normalizedScenarioWasteWithPct}%</span>
					</div>
					<input
						id="sim-waste-with"
						type="range"
						min="1"
						max={Math.max(1, normalizedScenarioWasteWithoutPct - 1)}
						step="1"
						bind:value={scenarioWasteWithPct}
						oninput={() => trackScenarioAdjust('governed_waste_rate')}
					/>
				</div>
				<div class="landing-roi-control">
					<label for="sim-window" class="landing-roi-label">Decision window (months)</label>
					<div class="landing-roi-meta">
						<span>{normalizedScenarioWindowMonths} months</span>
					</div>
					<input
						id="sim-window"
						type="range"
						min="3"
						max="24"
						step="1"
						bind:value={scenarioWindowMonths}
						oninput={() => trackScenarioAdjust('decision_window')}
					/>
				</div>
			</div>

			<div class="glass-panel landing-sim-results">
				<p class="landing-proof-k">Scenario Delta</p>
				<div class="landing-sim-chart" role="img" aria-label="Reactive versus governed waste comparison">
					<div class="landing-sim-bar-row">
						<div class="landing-sim-bar-label">Reactive spend</div>
						<div class="landing-sim-bar-track">
							<span class="landing-sim-bar is-reactive" style={`width:${scenarioWithoutBarPct}%;`}></span>
						</div>
						<div class="landing-sim-bar-value">{formatUsd(scenarioWasteWithoutUsd)}</div>
					</div>
					<div class="landing-sim-bar-row">
						<div class="landing-sim-bar-label">Governed spend</div>
						<div class="landing-sim-bar-track">
							<span class="landing-sim-bar is-governed" style={`width:${scenarioWithBarPct}%;`}></span>
						</div>
						<div class="landing-sim-bar-value">{formatUsd(scenarioWasteWithUsd)}</div>
					</div>
				</div>

				<div class="landing-sim-metrics">
					<div class="landing-sim-metric">
						<p>Recoverable waste / month</p>
						<strong>{formatUsd(scenarioWasteRecoveryMonthlyUsd)}</strong>
					</div>
					<div class="landing-sim-metric">
						<p>Recoverable waste / {normalizedScenarioWindowMonths} months</p>
						<strong>{formatUsd(scenarioWasteRecoveryWindowUsd)}</strong>
					</div>
					<div class="landing-sim-metric">
						<p>Spend context used</p>
						<strong>{formatUsd(roiInputs.monthlySpendUsd)} / month</strong>
					</div>
				</div>
				<p class="landing-roi-note">
					This simulator is directional and designed to accelerate finance + engineering decision alignment.
				</p>
			</div>
		</div>
	</section>

	<section id="roi" class="container mx-auto px-6 pb-20 landing-section-lazy" data-landing-section="roi">
		<div class="landing-section-head">
			<h2 class="landing-h2">See your 12-month control ROI before you commit</h2>
			<p class="landing-section-sub">
				Adjust spend and rollout assumptions to estimate savings velocity, payback timing, and net
				economic impact.
			</p>
		</div>

		<div class="landing-roi-grid">
			<div class="glass-panel landing-roi-controls">
				<div class="landing-roi-control">
					<label for="roi-monthly-spend" class="landing-roi-label">
						Cloud + software monthly spend
					</label>
					<div class="landing-roi-meta">
						<span>{formatUsd(roiInputs.monthlySpendUsd)}</span>
					</div>
					<input
						id="roi-monthly-spend"
						type="range"
						min="5000"
						max="500000"
						step="5000"
						bind:value={roiMonthlySpendUsd}
						oninput={markEngaged}
					/>
				</div>

				<div class="landing-roi-control">
					<label for="roi-reduction" class="landing-roi-label">Expected reduction (%)</label>
					<div class="landing-roi-meta">
						<span>{roiInputs.expectedReductionPct}%</span>
					</div>
					<input
						id="roi-reduction"
						type="range"
						min="1"
						max="30"
						step="1"
						bind:value={roiExpectedReductionPct}
						oninput={markEngaged}
					/>
				</div>

				<div class="landing-roi-control">
					<label for="roi-rollout" class="landing-roi-label">Rollout duration (days)</label>
					<div class="landing-roi-meta">
						<span>{roiInputs.rolloutDays} days</span>
					</div>
					<input
						id="roi-rollout"
						type="range"
						min="7"
						max="120"
						step="1"
						bind:value={roiRolloutDays}
						oninput={markEngaged}
					/>
				</div>

				<div class="landing-roi-control landing-roi-grid-2">
					<div>
						<label for="roi-team" class="landing-roi-label">Team members</label>
						<input
							id="roi-team"
							type="number"
							min="1"
							max="12"
							step="1"
							class="input mt-2"
							bind:value={roiTeamMembers}
							oninput={markEngaged}
						/>
					</div>
					<div>
						<label for="roi-hourly" class="landing-roi-label">Blended hourly rate</label>
						<input
							id="roi-hourly"
							type="number"
							min="50"
							max="400"
							step="5"
							class="input mt-2"
							bind:value={roiBlendedHourlyUsd}
							oninput={markEngaged}
						/>
					</div>
				</div>
			</div>

			<div class="glass-panel landing-roi-results">
				<p class="landing-proof-k">Projected 12-Month Impact</p>
				<div class="landing-roi-metrics">
					<div class="landing-roi-metric">
						<p>Monthly savings potential</p>
						<strong>{formatUsd(roiResult.monthlySavingsUsd)}</strong>
					</div>
					<div class="landing-roi-metric">
						<p>Annual gross savings</p>
						<strong>{formatUsd(roiResult.annualGrossSavingsUsd)}</strong>
					</div>
					<div class="landing-roi-metric">
						<p>Implementation + platform cost</p>
						<strong>{formatUsd(roiResult.implementationCostUsd)}</strong>
					</div>
					<div class="landing-roi-metric">
						<p>Annual net economic value</p>
						<strong class={roiResult.annualNetSavingsUsd >= 0 ? 'is-positive' : 'is-negative'}>
							{formatUsd(roiResult.annualNetSavingsUsd)}
						</strong>
					</div>
					<div class="landing-roi-metric">
						<p>Estimated payback window</p>
						<strong>{roiResult.paybackDays ? `${roiResult.paybackDays} days` : 'N/A'}</strong>
					</div>
					<div class="landing-roi-metric">
						<p>Gross ROI multiple</p>
						<strong>{roiResult.roiMultiple.toFixed(2)}x</strong>
					</div>
				</div>
				<div class="landing-roi-cta">
					<a
						href={buildRoiCtaHref()}
						class="btn btn-primary"
						onclick={() => trackCta('cta_click', 'roi', 'start_roi_assessment')}
					>
						Run This In Your Environment
					</a>
					<p class="landing-roi-note">
						Model output is directional and intended for planning alignment across engineering,
						finance, and leadership.
					</p>
				</div>
			</div>
		</div>
	</section>

		<section
		id="benefits"
		class="container mx-auto px-6 pb-20 landing-section-lazy"
		data-landing-section="benefits"
	>
			<div class="landing-section-head">
				<h2 class="landing-h2">Why teams switch from dashboards to control</h2>
				<p class="landing-section-sub">
					Valdrics combines visibility, ownership, and execution so teams can reduce waste with less
					escalation pressure.
				</p>
			</div>

		<div class="landing-benefits-grid">
			<article class="glass-panel landing-benefit-card">
				<p class="landing-proof-k">Economic Visibility</p>
				<h3 class="landing-h3">See spend shifts before they become monthly surprises</h3>
				<p class="landing-p">
					Get one clear view of cloud and software spend movement so teams can respond early and
					avoid end-of-month firefighting.
				</p>
			</article>

			<article class="glass-panel landing-benefit-card">
				<p class="landing-proof-k">Execution Controls</p>
				<h3 class="landing-h3">Prevent risky actions before they reach production</h3>
				<p class="landing-p">
					Move from ad-hoc approvals to consistent guardrails so teams can act faster without
					compromising safety.
				</p>
			</article>

				<article class="glass-panel landing-benefit-card">
					<p class="landing-proof-k">Financial Control</p>
					<h3 class="landing-h3">Set budget rules once and enforce them everywhere</h3>
					<p class="landing-p">
						Keep financial decisions aligned across platform, finance, and leadership with clear
						ownership and consistent decision paths.
					</p>
			</article>

			<article class="glass-panel landing-benefit-card">
				<p class="landing-proof-k">AI-Assisted Optimization</p>
				<h3 class="landing-h3">Get faster recommendations your team can trust</h3>
				<p class="landing-p">
					Use AI to prioritize high-impact opportunities while keeping final decisions with your
					team.
				</p>
			</article>

				<article class="glass-panel landing-benefit-card">
					<p class="landing-proof-k">Executive Explainability</p>
					<h3 class="landing-h3">Answer leadership questions in minutes</h3>
					<p class="landing-p">
						Share clear decision history and measurable outcomes when leadership or finance needs answers.
					</p>
				</article>
			</div>
		</section>

	<section
		id="plans"
		class="container mx-auto px-6 pb-20 landing-section-lazy"
		data-landing-section="plans"
	>
			<div class="landing-section-head">
				<h2 class="landing-h2">Choose a plan and launch in one sprint</h2>
				<p class="landing-section-sub">
					Shorten the path from sign-up to first savings decision with a plan built for your stage.
				</p>
			</div>

		<div class="landing-free-tier-card glass-panel">
			<div class="landing-free-tier-head">
					<div>
						<p class="landing-proof-k">Start Free</p>
						<h3 class="landing-h3">Permanent free tier for your first savings workflow</h3>
					<p class="landing-p">
						You can start at $0 with bounded usage, prove economic impact, and upgrade only when you need
						expanded scale and automation.
					</p>
				</div>
				<div class="landing-free-tier-price">
					<p class="landing-free-tier-price-k">Entry Price</p>
					<p class="landing-free-tier-price-v">$0</p>
				</div>
			</div>
			<ul class="landing-plan-features">
				{#each FREE_TIER_HIGHLIGHTS as feature (feature)}
					<li>{feature}</li>
				{/each}
			</ul>
			<div class="landing-free-tier-cta">
				<a
					href={buildFreeTierCtaHref()}
					class="btn btn-primary"
					onclick={() => trackCta('cta_click', 'plans', 'start_plan_free')}
				>
					Start on Free Tier
				</a>
				<span class="landing-free-tier-note">Upgrade later to Starter, Growth, or Pro.</span>
			</div>
		</div>

		<div class="landing-plans-grid">
			{#each PLAN_COMPARE_CARDS as plan (plan.id)}
				<article class="glass-panel landing-plan-card">
					<p class="landing-proof-k">{plan.kicker}</p>
					<h3 class="landing-h3">{plan.name}</h3>
					<p class="landing-plan-price">{plan.price}</p>
					<p class="landing-p">{plan.detail}</p>
					<ul class="landing-plan-features">
						{#each plan.features as feature (feature)}
							<li>{feature}</li>
						{/each}
					</ul>
					<a
						href={buildPlanCtaHref(plan.id)}
						class="btn btn-primary"
						onclick={() => trackCta('cta_click', 'plans', `start_plan_${plan.id}`)}
					>
						Start with {plan.name}
					</a>
				</article>
			{/each}
		</div>
		<div class="landing-onboard-flow glass-panel">
			<p class="landing-proof-k">Fast onboarding flow</p>
				<ol class="landing-onboard-steps">
					<li>Connect cloud and software sources.</li>
					<li>Assign owners and approval responsibilities.</li>
					<li>Run your first owner-led remediation cycle.</li>
				</ol>
			<a
				href={`${base}/pricing`}
				class="landing-cta-link"
				onclick={() => trackCta('cta_click', 'plans', 'view_full_pricing')}
			>
				View full pricing and feature details
			</a>
		</div>
	</section>

	<section
		id="personas"
		class="container mx-auto px-6 pb-20 landing-section-lazy"
		data-landing-section="personas"
	>
		<div class="landing-section-head">
			<h2 class="landing-h2">What each team gets in the first 30 days</h2>
			<p class="landing-section-sub">
				Engineering, FinOps, security, and leadership use one system, but each role sees tailored outcomes.
			</p>
		</div>

		<div class="landing-buyer-switch" role="tablist" aria-label="Buyer role views">
			{#each BUYER_ROLE_VIEWS as role, index (role.id)}
				<button
					type="button"
					role="tab"
					id={`buyer-tab-${role.id}`}
					class="landing-buyer-btn"
					class:is-active={buyerRoleIndex === index}
					aria-selected={buyerRoleIndex === index}
					aria-controls={`buyer-panel-${role.id}`}
					tabindex={buyerRoleIndex === index ? 0 : -1}
					onclick={() => selectBuyerRole(index)}
				>
					{role.label}
				</button>
			{/each}
		</div>

		<div
			class="glass-panel landing-buyer-panel"
			role="tabpanel"
			id={`buyer-panel-${activeBuyerRole.id}`}
			aria-labelledby={`buyer-tab-${activeBuyerRole.id}`}
		>
			<p class="landing-proof-k">{activeBuyerRole.label} Priority</p>
			<h3 class="landing-h3">{activeBuyerRole.headline}</h3>
			<p class="landing-p">{activeBuyerRole.detail}</p>
			<div class="landing-buyer-signals">
				{#each activeBuyerRole.signals as signal (signal)}
					<span class="landing-buyer-signal">{signal}</span>
				{/each}
			</div>
			<div class="landing-buyer-outcomes">
				<p class="landing-proof-k">In 30 days</p>
				<ul>
					{#each activeBuyerRole.thirtyDayOutcomes as outcome (outcome)}
						<li>{outcome}</li>
					{/each}
				</ul>
			</div>
		</div>
			<div class="landing-persona-proof">
				Outcome: one system that improves weekly operating decisions across technical and financial teams.
			</div>
		</section>

	{#if experiments.sectionOrderVariant === 'workflow_first'}
		{@render cloudHookSection()}
	{:else}
		{@render workflowSection()}
	{/if}

		<section
			id="coverage"
			class="container mx-auto px-6 pb-20 landing-section-lazy"
			data-landing-section="coverage"
	>
			<div class="landing-section-head">
				<h2 class="landing-h2">One platform for cloud, SaaS, and license spend</h2>
				<p class="landing-section-sub">
					Valdrics starts with cloud economics and extends spend control into SaaS, ITAM/license, and
					platform operations.
				</p>
			</div>

		<div class="landing-coverage-grid">
			{#each CROSS_SURFACE_COVERAGE as area (area.title)}
				<article class="glass-panel landing-coverage-card">
					<p class="landing-proof-k">{area.title}</p>
					<p class="landing-p">{area.detail}</p>
				</article>
			{/each}
			</div>
		</section>

		<section
			id="capabilities"
			class="container mx-auto px-6 pb-20 landing-section-lazy"
			data-landing-section="capabilities"
		>
			<div class="landing-section-head">
				<h2 class="landing-h2">What Valdrics already runs across your operations</h2>
				<p class="landing-section-sub">
					Valdrics is not just a dashboard. It combines cost control, GreenOps, SaaS/license
					management, remediation, and executive proof in one platform.
				</p>
			</div>

			<div class="landing-coverage-grid">
				{#each BACKEND_CAPABILITY_PILLARS as capability (capability.title)}
					<article class="glass-panel landing-coverage-card">
						<p class="landing-proof-k">{capability.title}</p>
						<p class="landing-p">{capability.detail}</p>
					</article>
				{/each}
			</div>
			<div class="landing-validation-cta glass-panel">
				<p class="landing-proof-k">Technical Validation</p>
				<p class="landing-p">
					See the public capability-to-API validation summary used for buyer diligence and security reviews.
				</p>
				<a
					href={`${base}/docs/technical-validation`}
					class="landing-cta-link"
					onclick={() => trackCta('cta_click', 'capabilities', 'open_technical_validation')}
				>
					Open Technical Validation
				</a>
			</div>
		</section>

	<section
		id="trust"
		class="container mx-auto px-6 pb-20 landing-section-lazy"
		data-landing-section="proof"
	>
			<div class="landing-section-head">
				<h2 class="landing-h2">Proof from teams reducing spend waste</h2>
				<p class="landing-section-sub">
					Buyers need outcomes, not marketing claims. Valdrics is designed to show clear before-and-after
					operating results.
				</p>
			</div>

		<div class="landing-evidence-grid">
			{#each EXECUTIVE_CONFIDENCE_POINTS as point (point.title)}
				<article class="glass-panel landing-evidence-card">
					<p class="landing-proof-k">{point.kicker}</p>
					<h3 class="landing-h3">{point.title}</h3>
					<p class="landing-p">{point.detail}</p>
				</article>
			{/each}
		</div>

		<div class="landing-trust-ecosystem">
			<p class="landing-proof-k">Platform Coverage</p>
			<div class="landing-trust-badges">
				{#each TRUST_ECOSYSTEM_BADGES as badge (badge)}
					<span class="landing-trust-badge">{badge}</span>
				{/each}
			</div>
		</div>

		<div class="landing-story-grid">
			{#each CUSTOMER_PROOF_STORIES as story (story.title)}
				<article class="glass-panel landing-story-card">
					<p class="landing-proof-k">{story.title}</p>
					<p class="landing-story-label">Before</p>
					<p class="landing-p">{story.before}</p>
					<p class="landing-story-label">After</p>
					<p class="landing-p">{story.after}</p>
					<p class="landing-trust-benchmark-k">{story.impact}</p>
				</article>
			{/each}
		</div>

		<div class="landing-trust-benchmarks">
			{#each TRUST_BENCHMARK_OUTCOMES as outcome (outcome.title)}
				<article class="glass-panel landing-trust-benchmark">
					<p class="landing-proof-k">Outcome Pattern</p>
					<h3 class="landing-h3">{outcome.title}</h3>
					<p class="landing-p">{outcome.detail}</p>
					<p class="landing-trust-benchmark-k">{outcome.benchmark}</p>
				</article>
			{/each}
		</div>

		<div class="landing-testimonial-grid">
			{#each CUSTOMER_QUOTES as quote (quote.quote)}
				<blockquote class="glass-panel landing-testimonial-card">
					<p class="landing-testimonial-quote">"{quote.quote}"</p>
					<cite class="landing-testimonial-cite">{quote.attribution}</cite>
				</blockquote>
			{/each}
		</div>

			<div class="landing-compliance-block">
				<p class="landing-proof-k">Security and compliance essentials</p>
				<div class="landing-trust-badges">
					{#each COMPLIANCE_FOUNDATION_BADGES as badge (badge)}
						<span class="landing-trust-badge">{badge}</span>
				{/each}
			</div>
			</div>
			<p class="landing-trust-note">
				Customer examples are anonymized and benchmark ranges are directional. Validate against your own
				baseline.
			</p>
		</section>

	<div class="landing-mobile-sticky-cta" aria-label="Mobile quick actions">
		<a
			href={buildPrimaryCtaHref()}
			class="btn btn-primary"
			onclick={() => trackCta('cta_click', 'mobile_sticky', experiments.ctaVariant)}
		>
			{primaryCtaLabel}
		</a>
		<a
			href="#plans"
			class="btn btn-secondary"
			onclick={() => trackCta('cta_click', 'mobile_sticky', 'see_plans')}
		>
			Plans
		</a>
	</div>
</div>

<style>
	.landing {
		position: relative;
		isolation: isolate;
		max-width: 100%;
		overflow-x: clip;
	}

	.landing-section-lazy {
		content-visibility: auto;
		contain-intrinsic-size: 640px;
	}

	.landing-hero {
		position: relative;
		overflow: hidden;
	}

	.landing-hero::before {
		content: '';
		position: absolute;
		inset: -260px -120px auto -120px;
		height: 640px;
		background:
			radial-gradient(520px 320px at 18% 18%, rgb(6 182 212 / 0.22), transparent 62%),
			radial-gradient(520px 360px at 58% 22%, rgb(34 211 238 / 0.18), transparent 65%),
			radial-gradient(520px 420px at 82% 38%, rgb(16 185 129 / 0.14), transparent 68%),
			radial-gradient(420px 360px at 70% 74%, rgb(245 158 11 / 0.1), transparent 70%);
		filter: blur(46px);
		opacity: 1;
		pointer-events: none;
		z-index: 0;
	}

	.landing-hero::after {
		content: '';
		position: absolute;
		inset: 0;
		background-image: radial-gradient(rgb(255 255 255 / 0.1) 1px, transparent 1px);
		background-size: 24px 24px;
		opacity: 0.1;
		pointer-events: none;
		z-index: 0;
	}

	.landing-hero :global(.container) {
		position: relative;
		z-index: 1;
	}

	.landing-hero-grid {
		display: grid;
		gap: 2.5rem;
		align-items: start;
	}

	@media (min-width: 1024px) {
		.landing-hero-grid {
			grid-template-columns: 1.1fr 0.9fr;
			gap: 3rem;
		}
	}

	.landing-copy {
		text-align: center;
	}

	@media (min-width: 1024px) {
		.landing-copy {
			text-align: left;
			padding-top: 0.75rem;
		}
	}

	.landing-kicker {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.55rem;
		flex-wrap: wrap;
	}

	@media (min-width: 1024px) {
		.landing-kicker {
			justify-content: flex-start;
		}
	}

	.landing-kicker-text {
		color: var(--color-ink-400);
		font-size: 0.95rem;
		font-weight: 500;
		letter-spacing: 0.01em;
	}

	.landing-sep {
		color: var(--color-ink-600);
	}

	.landing-problem-hook {
		margin-top: 0.9rem;
		border: 1px solid rgb(244 63 94 / 0.28);
		border-radius: var(--radius-lg);
		padding: 0.7rem 0.85rem;
		background: linear-gradient(130deg, rgb(244 63 94 / 0.12), rgb(15 23 42 / 0.24));
	}

	.landing-problem-k {
		margin: 0;
		font-size: 0.86rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 800;
		color: var(--color-ink-200);
	}

	.landing-problem-v {
		margin: 0.35rem 0 0 0;
		font-size: 1rem;
		line-height: 1.45;
		color: var(--color-ink-100);
	}

	.landing-title {
		font-family: ui-serif, 'Iowan Old Style', 'Palatino Linotype', Palatino, serif;
		font-weight: 800;
		letter-spacing: -0.04em;
		line-height: 1.02;
		font-size: clamp(2.6rem, 5vw, 4.4rem);
		margin-top: 0.9rem;
		margin-bottom: 1rem;
	}

	.landing-subtitle {
		color: var(--color-ink-300);
		font-size: 1.125rem;
		line-height: 1.65;
		max-width: 42rem;
		margin: 0 auto;
	}

	@media (min-width: 1024px) {
		.landing-subtitle {
			margin-left: 0;
		}
	}

	.landing-cta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		justify-content: center;
		margin-top: 1.4rem;
	}

	@media (max-width: 640px) {
		.landing-cta {
			flex-direction: column;
			align-items: stretch;
			gap: 0.65rem;
		}

		.landing-cta a {
			display: inline-flex;
			align-items: center;
			justify-content: center;
			width: 100%;
			min-height: 2.85rem;
			font-size: 1rem;
			line-height: 1.2;
			padding: 0.72rem 1rem;
		}
	}

	@media (min-width: 1024px) {
		.landing-cta {
			justify-content: flex-start;
		}
	}

	.landing-cta-note {
		margin: 0.6rem 0 0 0;
		color: var(--color-ink-400);
		font-size: 0.92rem;
		line-height: 1.45;
	}

	.landing-cta-free-note {
		margin: 0.38rem 0 0 0;
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--color-success-300);
	}

	.landing-free-strip {
		margin-top: 0.65rem;
		display: inline-flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.45rem;
		font-size: 0.89rem;
		color: var(--color-ink-200);
	}

	.landing-free-pill {
		display: inline-flex;
		align-items: center;
		padding: 0.2rem 0.5rem;
		border-radius: 9999px;
		border: 1px solid rgb(16 185 129 / 0.4);
		background: rgb(16 185 129 / 0.15);
		color: var(--color-success-300);
		font-size: 0.76rem;
		letter-spacing: 0.07em;
		text-transform: uppercase;
		font-weight: 800;
	}

	.landing-cta-link {
		display: inline-flex;
		margin-top: 0.2rem;
		font-size: 0.95rem;
		font-weight: 700;
		color: var(--color-accent-300);
		text-decoration: underline;
		text-decoration-thickness: 1px;
		text-underline-offset: 2px;
	}

	.landing-cta-link:hover {
		color: var(--color-accent-200);
	}

	.landing-cta-link:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
		border-radius: 4px;
	}

	@media (max-width: 640px) {
		.landing-cta-note,
		.landing-cta-link {
			text-align: center;
			justify-content: center;
		}

		.landing-cta-free-note {
			text-align: center;
		}

		.landing-free-strip {
			justify-content: center;
			text-align: center;
		}
	}

	.landing-quant-promise {
		margin-top: 1rem;
		border: 1px solid rgb(6 182 212 / 0.24);
		border-radius: var(--radius-lg);
		padding: 0.75rem 0.9rem;
		background: linear-gradient(140deg, rgb(6 182 212 / 0.16), rgb(15 23 42 / 0.34));
	}

	.landing-quant-k {
		margin: 0;
		font-size: 0.78rem;
		font-weight: 800;
		letter-spacing: 0.09em;
		text-transform: uppercase;
		color: var(--color-ink-300);
	}

	.landing-quant-v {
		margin: 0.32rem 0 0 0;
		font-size: 1rem;
		line-height: 1.45;
		color: var(--color-accent-300);
		font-weight: 700;
	}

	.landing-outcome-chips {
		margin-top: 0.85rem;
		display: grid;
		gap: 0.55rem;
		grid-template-columns: 1fr;
	}

	@media (min-width: 768px) {
		.landing-outcome-chips {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-outcome-chip {
		border: 1px solid rgb(255 255 255 / 0.08);
		border-radius: var(--radius-lg);
		padding: 0.65rem 0.7rem;
		background: rgb(10 15 22 / 0.45);
	}

	.landing-outcome-chip-k {
		margin: 0;
		font-size: 0.73rem;
		font-weight: 800;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--color-ink-500);
	}

	.landing-outcome-chip-v {
		margin: 0.27rem 0 0 0;
		font-size: 0.93rem;
		line-height: 1.35;
		color: var(--color-ink-100);
		font-weight: 700;
	}

	.landing-proof {
		margin-top: 1.75rem;
		display: grid;
		gap: 0.85rem;
		grid-template-columns: 1fr;
	}

	@media (min-width: 768px) {
		.landing-proof {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-proof-item {
		border: 1px solid rgb(255 255 255 / 0.06);
		border-radius: var(--radius-lg);
		padding: 0.95rem 1rem;
		background: rgb(15 19 24 / 0.35);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
	}

	.landing-proof-k {
		margin: 0 0 0.25rem 0;
		font-size: var(--text-xs);
		letter-spacing: 0.09em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-200);
	}

	.landing-proof-v {
		margin: 0;
		font-size: 1rem;
		color: var(--color-ink-400);
	}

	.landing-preview {
		max-width: 42rem;
		margin: 0 auto;
		min-width: 0;
	}

	@media (min-width: 1024px) {
		.landing-preview {
			max-width: none;
			margin: 0;
		}
	}

	.landing-preview-card {
		padding: 1.1rem;
		contain: layout paint style;
		min-width: 0;
		max-width: 100%;
	}

	.landing-preview-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.landing-preview-title {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		font-weight: 700;
		color: var(--color-ink-100);
	}

	.landing-preview-pill {
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: 0.12em;
		font-weight: 800;
		padding: 0.25rem 0.55rem;
		border-radius: 9999px;
		color: var(--color-success-400);
		background: rgb(16 185 129 / 0.1);
		border: 1px solid rgb(16 185 129 / 0.22);
	}

	.landing-live-dot {
		width: 8px;
		height: 8px;
		border-radius: 9999px;
		background: var(--color-success-400);
		box-shadow: 0 0 0 6px rgb(16 185 129 / 0.12);
		animation: livePulse 1.8s var(--ease-in-out) infinite;
	}

	@keyframes livePulse {
		0%,
		100% {
			transform: scale(1);
			opacity: 0.95;
		}
		50% {
			transform: scale(1.4);
			opacity: 0.55;
		}
	}

	.signal-state-headline {
		margin: 0;
		font-size: 1.08rem;
		font-weight: 600;
		color: var(--color-ink-200);
	}

	.signal-state-sub {
		margin: 0.35rem 0 0.8rem 0;
		font-size: 1rem;
		line-height: 1.5;
		color: var(--color-ink-400);
	}

	.signal-map {
		position: relative;
		border-radius: var(--radius-lg);
		overflow: hidden;
		contain: strict;
		border: 1px solid rgb(255 255 255 / 0.07);
		background:
			radial-gradient(
				120% 90% at 30% 20%,
				rgb(34 211 238 / 0.18) 0%,
				rgb(6 182 212 / 0.06) 38%,
				rgb(15 19 24 / 0.55) 70%
			),
			radial-gradient(90% 120% at 75% 70%, rgb(16 185 129 / 0.12) 0%, rgb(15 19 24 / 0) 62%);
		height: 344px;
	}

	.signal-map::after {
		content: '';
		position: absolute;
		inset: 0;
		background-image: radial-gradient(rgb(255 255 255 / 0.1) 1px, transparent 1px);
		background-size: 26px 26px;
		opacity: 0.12;
		pointer-events: none;
		z-index: 2;
	}

	.signal-svg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		z-index: 1;
	}

	.sig-grid line {
		stroke: rgb(255 255 255 / 0.06);
		stroke-width: 1;
	}

	.sig-link {
		opacity: 0.88;
		animation: lineDash 7s linear infinite;
	}

	.signal-map.is-paused .sig-link,
	.signal-map.is-paused .sig-node {
		animation-play-state: paused;
	}

	@keyframes lineDash {
		to {
			stroke-dashoffset: -220;
		}
	}

	.sig-node {
		fill: rgb(10 13 18 / 0.8);
		stroke: var(--color-accent-400);
		stroke-width: 2.2;
		filter: drop-shadow(0 0 10px rgb(34 211 238 / 0.2));
		transform-box: fill-box;
		transform-origin: center;
		animation: nodePulse 2.9s var(--ease-in-out) infinite;
	}

	.sig-node--center {
		fill: rgb(6 182 212 / 0.65);
		stroke: var(--color-accent-400);
		animation-duration: 3.8s;
	}

	@keyframes nodePulse {
		0%,
		100% {
			transform: scale(1);
		}
		50% {
			transform: scale(1.18);
		}
	}

	.sig-link.is-healthy {
		opacity: 0.92;
	}

	.sig-link.is-watch {
		stroke: var(--color-warning-400);
		opacity: 0.82;
	}

	.sig-link.is-critical {
		stroke: var(--color-danger-400);
		opacity: 0.95;
	}

	.sig-node.is-healthy {
		stroke: var(--color-success-400);
		filter: drop-shadow(0 0 10px rgb(16 185 129 / 0.24));
	}

	.sig-node.is-watch {
		stroke: var(--color-warning-400);
		filter: drop-shadow(0 0 10px rgb(245 158 11 / 0.24));
	}

	.sig-node.is-critical {
		stroke: var(--color-danger-400);
		filter: drop-shadow(0 0 10px rgb(244 63 94 / 0.26));
	}

	.sig-node.is-focused {
		stroke-width: 3.2;
		filter: drop-shadow(0 0 14px rgb(34 211 238 / 0.45));
	}

	@media (prefers-reduced-motion: reduce) {
		.landing-live-dot,
		.sig-link,
		.sig-node {
			animation: none !important;
		}
	}

	@media (max-width: 640px) {
		.landing-live-dot,
		.sig-link,
		.sig-node {
			animation-duration: 0.001ms;
			animation-iteration-count: 1;
		}
	}

	.signal-hotspot {
		position: absolute;
		width: 1.35rem;
		height: 1.35rem;
		border-radius: 9999px;
		border: 1px solid rgb(255 255 255 / 0.42);
		background: rgb(7 12 18 / 0.55);
		transform: translate(-50%, -50%);
		z-index: 4;
		transition: all var(--duration-fast) var(--ease-out);
	}

	.signal-hotspot:hover,
	.signal-hotspot.is-active {
		border-color: rgb(34 211 238 / 0.82);
		box-shadow: 0 0 0 3px rgb(34 211 238 / 0.2);
		background: rgb(34 211 238 / 0.2);
	}

	.signal-hotspot:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.signal-lane-controls {
		margin-top: 0.85rem;
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.45rem;
	}

	@media (min-width: 768px) {
		.signal-lane-controls {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.signal-lane-btn {
		border-radius: 0.75rem;
		border: 1px solid rgb(255 255 255 / 0.12);
		background: rgb(11 16 23 / 0.62);
		padding: 0.55rem 0.65rem;
		color: var(--color-ink-300);
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		text-align: left;
		transition: all var(--duration-fast) var(--ease-out);
	}

	.signal-lane-btn:hover {
		border-color: rgb(255 255 255 / 0.24);
		color: var(--color-ink-100);
	}

	.signal-lane-btn:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.signal-lane-btn.is-active {
		background: rgb(6 182 212 / 0.14);
		border-color: rgb(6 182 212 / 0.36);
		color: var(--color-accent-200);
	}

	.signal-lane-btn-title {
		font-size: 0.83rem;
		font-weight: 700;
		line-height: 1.2;
	}

	.signal-lane-btn-status {
		font-size: 0.75rem;
		font-weight: 700;
		letter-spacing: 0.03em;
		text-transform: uppercase;
		opacity: 0.85;
	}

	.signal-lane-detail-panel {
		margin-top: 0.65rem;
		border: 1px solid rgb(255 255 255 / 0.12);
		border-radius: var(--radius-lg);
		padding: 0.72rem 0.8rem;
		background: rgb(8 12 18 / 0.55);
	}

	.signal-lane-detail-k {
		margin: 0;
		font-size: 0.8rem;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 800;
		color: var(--color-accent-300);
	}

	.signal-lane-detail-v {
		margin: 0.4rem 0 0 0;
		font-size: 0.93rem;
		line-height: 1.45;
		color: var(--color-ink-200);
	}

	.signal-lane-detail-m {
		margin: 0.38rem 0 0 0;
		font-size: 0.86rem;
		line-height: 1.35;
		color: var(--color-ink-400);
	}

	.signal-label {
		position: absolute;
		padding: 0.55rem 0.65rem;
		border-radius: 0.85rem;
		background: rgb(10 13 18 / 0.55);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
		border: 1px solid rgb(255 255 255 / 0.08);
		pointer-events: none;
		max-width: 12.75rem;
		z-index: 3;
	}

	.signal-label-k {
		margin: 0;
		font-size: var(--text-xs);
		letter-spacing: 0.12em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-200);
	}

	.signal-label-v {
		margin: 0.15rem 0 0 0;
		font-size: 0.94rem;
		line-height: 1.35;
		color: var(--color-ink-400);
		display: -webkit-box;
		line-clamp: 2;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	.signal-label--center {
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		text-align: center;
		max-width: 10.5rem;
	}

	.signal-label--a {
		left: 18%;
		top: 34%;
		transform: translate(-8%, -96%);
	}

	.signal-label--b {
		left: 73%;
		top: 34%;
		transform: translate(-58%, -96%);
	}

	.signal-label--c {
		left: 77%;
		top: 66%;
		transform: translate(-36%, 0);
	}

	.signal-label--d {
		left: 16%;
		top: 66%;
		transform: translate(0, 0);
	}

	@media (max-width: 900px) {
		.signal-label {
			max-width: 10.25rem;
			padding: 0.45rem 0.55rem;
		}

		.signal-label-k {
			font-size: 0.68rem;
		}

		.signal-label-v {
			font-size: 0.82rem;
		}

		.signal-label--a {
			left: 6%;
			top: 10%;
			transform: none;
		}

		.signal-label--b {
			left: auto;
			right: 6%;
			top: 10%;
			transform: none;
			text-align: right;
		}

		.signal-label--c {
			left: auto;
			right: 6%;
			top: auto;
			bottom: 8%;
			transform: none;
			text-align: right;
		}

		.signal-label--d {
			left: 6%;
			top: auto;
			bottom: 8%;
			transform: none;
		}
	}

	@media (max-width: 560px) {
		.signal-label:not(.signal-label--center) {
			display: none;
		}

		.signal-label--center {
			max-width: 9rem;
			padding: 0.5rem 0.6rem;
		}
	}

	.landing-metrics {
		margin-top: 0.9rem;
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.75rem;
	}

	@media (max-width: 900px) {
		.landing-metrics {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	@media (max-width: 560px) {
		.landing-metrics {
			grid-template-columns: 1fr;
		}
	}

	.landing-metric {
		padding: 0.85rem 0.9rem;
		border-radius: var(--radius-lg);
	}

	.landing-metric-k {
		margin: 0;
		font-size: var(--text-xs);
		letter-spacing: 0.1em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-400);
	}

	.landing-metric-v {
		margin: 0.25rem 0 0 0;
		font-size: 1.1rem;
		font-weight: 800;
		line-height: 1.3;
	}

	.landing-metric-h {
		margin: 0.3rem 0 0 0;
		font-size: 0.95rem;
		color: var(--color-ink-500);
	}

	.landing-demo-strip {
		margin-top: 0.95rem;
		border: 1px solid rgb(255 255 255 / 0.09);
		border-radius: var(--radius-lg);
		padding: 0.8rem 0.9rem;
		background: rgb(7 12 18 / 0.5);
	}

	.landing-demo-k {
		margin: 0;
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: 0.12em;
		font-weight: 800;
		color: var(--color-accent-300);
	}

	.landing-demo-steps {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.45rem;
		margin-top: 0.55rem;
	}

	@media (min-width: 900px) {
		.landing-demo-steps {
			grid-template-columns: repeat(4, minmax(0, 1fr));
		}
	}

	.landing-demo-step {
		border-radius: 9999px;
		border: 1px solid rgb(255 255 255 / 0.14);
		background: rgb(21 30 40 / 0.78);
		color: var(--color-ink-300);
		font-size: var(--text-xs);
		font-weight: 700;
		padding: 0.35rem 0.5rem;
		transition: all var(--duration-fast) var(--ease-out);
	}

	.landing-demo-step:hover {
		color: var(--color-ink-100);
		border-color: rgb(255 255 255 / 0.24);
	}

	.landing-demo-step:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.landing-demo-step.is-active {
		background: rgb(6 182 212 / 0.18);
		border-color: rgb(6 182 212 / 0.36);
		color: var(--color-accent-300);
	}

	.landing-demo-detail {
		margin: 0.65rem 0 0 0;
		font-size: 0.9rem;
		line-height: 1.5;
		color: var(--color-ink-300);
	}

	.signal-snapshot-controls {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin-top: 0.95rem;
	}

	.signal-snapshot-btn {
		padding: 0.4rem 0.65rem;
		border-radius: 9999px;
		font-size: var(--text-xs);
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		border: 1px solid rgb(255 255 255 / 0.1);
		background: rgb(24 32 40 / 0.7);
		color: var(--color-ink-300);
		transition: all var(--duration-fast) var(--ease-out);
	}

	.signal-snapshot-btn:hover {
		color: var(--color-ink-100);
		border-color: rgb(255 255 255 / 0.2);
	}

	.signal-snapshot-btn:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.signal-snapshot-btn.is-active {
		background: rgb(6 182 212 / 0.16);
		border-color: rgb(6 182 212 / 0.35);
		color: var(--color-accent-400);
	}

	.landing-section-head {
		max-width: 52rem;
		margin: 0 auto 1.25rem auto;
		text-align: center;
	}

	.landing-h2 {
		font-family: ui-serif, 'Iowan Old Style', 'Palatino Linotype', Palatino, serif;
		font-weight: 800;
		letter-spacing: -0.03em;
		line-height: 1.1;
		font-size: clamp(1.85rem, 3vw, 2.3rem);
		margin: 0;
	}

	.landing-section-sub {
		margin: 0.7rem auto 0 auto;
		color: var(--color-ink-400);
		font-size: 1.05rem;
		max-width: 46rem;
	}

	.landing-h3 {
		font-weight: 700;
		font-size: 1.08rem;
		margin: 0 0 0.55rem 0;
	}

	.landing-p {
		margin: 0;
		color: var(--color-ink-300);
		font-size: 1rem;
		line-height: 1.65;
	}

	.landing-hook {
		padding: 1.25rem;
	}

	.landing-hook-highlight {
		margin-top: 1rem;
		border: 1px solid rgb(6 182 212 / 0.22);
		background: linear-gradient(120deg, rgb(6 182 212 / 0.14), rgb(16 185 129 / 0.08));
		border-radius: var(--radius-lg);
		padding: 0.85rem 1rem;
	}

	.landing-hook-highlight-k {
		margin: 0;
		font-size: var(--text-xs);
		letter-spacing: 0.11em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-accent-300);
	}

	.landing-hook-highlight-v {
		margin: 0.25rem 0 0 0;
		font-size: 1.02rem;
		font-weight: 700;
		color: var(--color-ink-100);
	}

	.landing-hook-switch {
		margin-top: 1rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem;
		align-items: stretch;
	}

	.landing-hook-switch-btn {
		padding: 0.45rem 0.72rem;
		border-radius: 9999px;
		border: 1px solid rgb(255 255 255 / 0.12);
		background: rgb(24 32 40 / 0.7);
		color: var(--color-ink-300);
		font-size: 0.86rem;
		font-weight: 700;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		line-height: 1.2;
		white-space: normal;
		transition: all var(--duration-fast) var(--ease-out);
	}

	.landing-hook-switch-btn:hover {
		color: var(--color-ink-100);
		border-color: rgb(255 255 255 / 0.2);
	}

	.landing-hook-switch-btn:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.landing-hook-switch-btn.is-active {
		background: rgb(6 182 212 / 0.16);
		border-color: rgb(6 182 212 / 0.35);
		color: var(--color-accent-400);
	}

	.landing-hook-scene {
		margin-top: 0.9rem;
		border: 1px solid rgb(244 63 94 / 0.22);
		border-radius: var(--radius-lg);
		padding: 0.95rem 1rem;
		background: linear-gradient(145deg, rgb(244 63 94 / 0.1), rgb(15 23 42 / 0.42));
		transition:
			background var(--duration-fast) var(--ease-out),
			border-color var(--duration-fast) var(--ease-out);
	}

	.landing-hook-scene.is-with {
		border-color: rgb(16 185 129 / 0.24);
		background: linear-gradient(145deg, rgb(6 182 212 / 0.12), rgb(16 185 129 / 0.08));
	}

	.landing-hook-sub {
		margin: 0 0 0.6rem 0;
		font-size: 0.9rem;
		color: var(--color-ink-200);
		font-weight: 600;
	}

	.landing-hook-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.5rem;
	}

	.landing-hook-list li {
		position: relative;
		padding-left: 1rem;
		color: var(--color-ink-200);
		line-height: 1.45;
	}

	.landing-hook-list li::before {
		content: '';
		position: absolute;
		left: 0;
		top: 0.46rem;
		width: 0.42rem;
		height: 0.42rem;
		border-radius: 9999px;
		background: var(--color-accent-400);
		box-shadow: 0 0 0 4px rgb(6 182 212 / 0.14);
	}

	.landing-hook-metrics {
		margin-top: 0.9rem;
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.55rem;
	}

	@media (min-width: 900px) {
		.landing-hook-metrics {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-hook-metric {
		border: 1px solid rgb(255 255 255 / 0.1);
		border-radius: var(--radius-lg);
		padding: 0.6rem 0.7rem;
		background: rgb(10 13 18 / 0.42);
	}

	.landing-hook-metric-k {
		margin: 0;
		font-size: var(--text-xs);
		letter-spacing: 0.1em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-500);
	}

	.landing-hook-metric-v {
		margin: 0.22rem 0 0 0;
		font-size: 0.94rem;
		font-weight: 700;
		color: var(--color-ink-100);
	}

	.landing-benefits-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	.landing-roi-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	.landing-sim-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	@media (min-width: 1024px) {
		.landing-sim-grid {
			grid-template-columns: 1fr 1fr;
		}
	}

	.landing-sim-controls {
		display: grid;
		gap: 0.95rem;
	}

	.landing-sim-results {
		display: grid;
		gap: 0.85rem;
	}

	.landing-sim-chart {
		display: grid;
		gap: 0.6rem;
	}

	.landing-sim-bar-row {
		display: grid;
		grid-template-columns: 9rem minmax(0, 1fr) 5.5rem;
		gap: 0.5rem;
		align-items: center;
	}

	@media (max-width: 640px) {
		.landing-sim-bar-row {
			grid-template-columns: 1fr;
			gap: 0.35rem;
		}
	}

	.landing-sim-bar-label {
		font-size: 0.84rem;
		font-weight: 700;
		color: var(--color-ink-300);
	}

	.landing-sim-bar-track {
		position: relative;
		height: 0.72rem;
		border-radius: 9999px;
		background: rgb(255 255 255 / 0.1);
		overflow: hidden;
	}

	.landing-sim-bar {
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		border-radius: 9999px;
	}

	.landing-sim-bar.is-reactive {
		background: linear-gradient(90deg, rgb(244 63 94 / 0.85), rgb(251 113 133 / 0.9));
	}

	.landing-sim-bar.is-governed {
		background: linear-gradient(90deg, rgb(6 182 212 / 0.82), rgb(16 185 129 / 0.88));
	}

	.landing-sim-bar-value {
		text-align: right;
		font-size: 0.88rem;
		font-weight: 700;
		color: var(--color-ink-100);
	}

	.landing-sim-metrics {
		display: grid;
		gap: 0.6rem;
		grid-template-columns: 1fr;
	}

	@media (min-width: 768px) {
		.landing-sim-metrics {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-sim-metric {
		border: 1px solid rgb(255 255 255 / 0.08);
		border-radius: var(--radius-lg);
		padding: 0.7rem 0.75rem;
		background: rgb(8 13 20 / 0.55);
	}

	.landing-sim-metric p {
		margin: 0;
		font-size: 0.76rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--color-ink-500);
	}

	.landing-sim-metric strong {
		display: block;
		margin-top: 0.32rem;
		font-size: 1rem;
		color: var(--color-accent-300);
	}

	@media (min-width: 1024px) {
		.landing-roi-grid {
			grid-template-columns: 1.05fr 0.95fr;
		}
	}

	.landing-roi-controls {
		display: grid;
		gap: 0.95rem;
	}

	.landing-roi-control {
		border: 1px solid rgb(255 255 255 / 0.08);
		border-radius: var(--radius-lg);
		padding: 0.7rem 0.8rem;
		background: rgb(11 16 24 / 0.45);
	}

	.landing-roi-grid-2 {
		display: grid;
		gap: 0.75rem;
	}

	@media (min-width: 768px) {
		.landing-roi-grid-2 {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.landing-roi-label {
		display: block;
		font-size: 0.86rem;
		font-weight: 700;
		color: var(--color-ink-200);
	}

	.landing-roi-meta {
		margin-top: 0.25rem;
		font-size: 0.95rem;
		font-weight: 700;
		color: var(--color-accent-300);
	}

	.landing-roi-control input[type='range'] {
		width: 100%;
		margin-top: 0.5rem;
		accent-color: var(--color-accent-500);
	}

	.landing-roi-results {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.landing-roi-metrics {
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.65rem;
	}

	@media (min-width: 768px) {
		.landing-roi-metrics {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.landing-roi-metric {
		border: 1px solid rgb(255 255 255 / 0.08);
		border-radius: var(--radius-lg);
		padding: 0.75rem 0.8rem;
		background: rgb(6 11 18 / 0.5);
	}

	.landing-roi-metric p {
		margin: 0;
		font-size: 0.82rem;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--color-ink-500);
		font-weight: 700;
	}

	.landing-roi-metric strong {
		display: block;
		margin-top: 0.35rem;
		font-size: 1.12rem;
		color: var(--color-ink-100);
	}

	.landing-roi-metric strong.is-positive {
		color: var(--color-success-400);
	}

	.landing-roi-metric strong.is-negative {
		color: var(--color-danger-400);
	}

	.landing-roi-cta {
		display: grid;
		gap: 0.6rem;
	}

	.landing-roi-note {
		margin: 0;
		font-size: 0.87rem;
		line-height: 1.45;
		color: var(--color-ink-400);
	}

	@media (min-width: 1024px) {
		.landing-benefits-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}

		.landing-benefits-grid .landing-benefit-card:last-child {
			grid-column: span 2;
		}
	}

	.landing-plans-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	@media (min-width: 1024px) {
		.landing-plans-grid {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-plan-card {
		display: grid;
		gap: 0.65rem;
	}

	.landing-free-tier-card {
		margin-bottom: 1rem;
		display: grid;
		gap: 0.8rem;
		border-color: rgb(16 185 129 / 0.32);
		background: linear-gradient(142deg, rgb(16 185 129 / 0.14), rgb(6 11 18 / 0.72));
	}

	.landing-free-tier-head {
		display: grid;
		gap: 0.7rem;
	}

	@media (min-width: 900px) {
		.landing-free-tier-head {
			grid-template-columns: 1fr auto;
			align-items: start;
		}
	}

	.landing-free-tier-price {
		border: 1px solid rgb(255 255 255 / 0.18);
		border-radius: var(--radius-lg);
		padding: 0.65rem 0.8rem;
		background: rgb(6 11 18 / 0.72);
		min-width: 7.5rem;
	}

	.landing-free-tier-price-k {
		margin: 0;
		font-size: 0.73rem;
		font-weight: 800;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: var(--color-ink-400);
	}

	.landing-free-tier-price-v {
		margin: 0.18rem 0 0 0;
		font-size: 1.4rem;
		font-weight: 900;
		color: var(--color-success-300);
	}

	.landing-free-tier-cta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem 0.8rem;
		align-items: center;
	}

	.landing-free-tier-note {
		font-size: 0.88rem;
		color: var(--color-ink-300);
	}

	.landing-plan-price {
		margin: 0;
		font-size: 1.25rem;
		font-weight: 800;
		color: var(--color-accent-300);
	}

	.landing-plan-features {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.45rem;
	}

	.landing-plan-features li {
		position: relative;
		padding-left: 0.95rem;
		font-size: 0.94rem;
		line-height: 1.4;
		color: var(--color-ink-300);
	}

	.landing-plan-features li::before {
		content: '';
		position: absolute;
		left: 0;
		top: 0.45rem;
		width: 0.4rem;
		height: 0.4rem;
		border-radius: 9999px;
		background: var(--color-success-400);
		box-shadow: 0 0 0 3px rgb(16 185 129 / 0.14);
	}

	.landing-onboard-flow {
		margin-top: 1rem;
	}

	.landing-onboard-steps {
		margin: 0.5rem 0 0 0;
		padding-left: 1rem;
		display: grid;
		gap: 0.45rem;
		color: var(--color-ink-300);
	}

	.landing-buyer-switch {
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem;
		justify-content: center;
	}

	.landing-buyer-btn {
		padding: 0.45rem 0.75rem;
		border-radius: 9999px;
		border: 1px solid rgb(255 255 255 / 0.15);
		background: rgb(24 32 40 / 0.7);
		color: var(--color-ink-300);
		font-size: var(--text-xs);
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		transition: all var(--duration-fast) var(--ease-out);
	}

	.landing-buyer-btn:hover {
		color: var(--color-ink-100);
		border-color: rgb(255 255 255 / 0.24);
	}

	.landing-buyer-btn:focus-visible {
		outline: 2px solid var(--color-accent-500);
		outline-offset: 2px;
	}

	.landing-buyer-btn.is-active {
		background: rgb(6 182 212 / 0.16);
		border-color: rgb(6 182 212 / 0.35);
		color: var(--color-accent-300);
	}

	.landing-buyer-panel {
		margin-top: 0.85rem;
	}

	.landing-buyer-signals {
		margin-top: 0.75rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.landing-buyer-signal {
		padding: 0.28rem 0.5rem;
		border-radius: 9999px;
		border: 1px solid rgb(255 255 255 / 0.14);
		background: rgb(8 12 17 / 0.48);
		font-size: 0.86rem;
		line-height: 1.2;
		color: var(--color-ink-200);
	}

	.landing-persona-proof {
		margin: 0.9rem auto 0 auto;
		max-width: 56rem;
		text-align: center;
		font-size: 0.92rem;
		font-weight: 600;
		line-height: 1.45;
		color: var(--color-ink-200);
	}

	.landing-buyer-outcomes {
		margin-top: 0.85rem;
		border: 1px solid rgb(255 255 255 / 0.1);
		border-radius: var(--radius-lg);
		padding: 0.75rem 0.8rem;
		background: rgb(8 12 17 / 0.48);
	}

	.landing-buyer-outcomes ul {
		margin: 0.35rem 0 0 0;
		padding-left: 1rem;
		display: grid;
		gap: 0.35rem;
		color: var(--color-ink-300);
		font-size: 0.93rem;
		line-height: 1.45;
	}

	.landing-steps {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	.landing-coverage-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	@media (min-width: 900px) {
		.landing-coverage-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.landing-coverage-card {
		border-color: rgb(16 185 129 / 0.2);
		background: linear-gradient(145deg, rgb(6 182 212 / 0.1), rgb(16 185 129 / 0.08));
	}

	.landing-validation-cta {
		margin-top: var(--space-4);
		display: grid;
		gap: 0.5rem;
	}

	@media (min-width: 768px) {
		.landing-steps {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-step {
		position: relative;
		overflow: hidden;
	}

	.landing-step::before {
		content: '';
		position: absolute;
		inset: 0 0 auto 0;
		height: 2px;
		background: linear-gradient(90deg, rgb(34 211 238 / 0.9), rgb(16 185 129 / 0.75));
		opacity: 0.75;
	}

	.landing-step-n {
		margin: 0 0 0.35rem 0;
		font-size: var(--text-xs);
		letter-spacing: 0.16em;
		font-weight: 900;
		color: var(--color-ink-500);
		text-transform: uppercase;
	}

	.landing-evidence-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	.landing-trust-ecosystem {
		margin-top: 1rem;
	}

	.landing-trust-badges {
		margin-top: 0.55rem;
		display: flex;
		flex-wrap: wrap;
		gap: 0.45rem;
	}

	.landing-trust-badge {
		padding: 0.33rem 0.62rem;
		border-radius: 9999px;
		border: 1px solid rgb(255 255 255 / 0.14);
		background: rgb(9 14 22 / 0.52);
		font-size: 0.84rem;
		font-weight: 700;
		color: var(--color-ink-200);
	}

	.landing-trust-benchmarks {
		margin-top: 1rem;
		display: grid;
		gap: var(--space-4);
		grid-template-columns: 1fr;
	}

	@media (min-width: 900px) {
		.landing-trust-benchmarks {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-trust-benchmark-k {
		margin: 0.65rem 0 0 0;
		font-size: 0.84rem;
		font-weight: 700;
		color: var(--color-ink-100);
	}

	.landing-trust-benchmark {
		background: rgb(6 12 18 / 0.76);
		border-color: rgb(255 255 255 / 0.14);
	}

	.landing-story-grid {
		margin-top: 1rem;
		display: grid;
		gap: var(--space-4);
		grid-template-columns: 1fr;
	}

	@media (min-width: 900px) {
		.landing-story-grid {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-story-card {
		display: grid;
		gap: 0.35rem;
	}

	.landing-story-label {
		margin: 0.2rem 0 0 0;
		font-size: 0.78rem;
		font-weight: 800;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--color-ink-500);
	}

	.landing-testimonial-grid {
		margin-top: 1rem;
		display: grid;
		gap: var(--space-4);
		grid-template-columns: 1fr;
	}

	@media (min-width: 900px) {
		.landing-testimonial-grid {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-testimonial-card {
		display: grid;
		gap: 0.6rem;
		border-left: 2px solid rgb(6 182 212 / 0.55);
		background: rgb(6 11 18 / 0.78);
		border-color: rgb(255 255 255 / 0.16);
	}

	.landing-testimonial-quote {
		margin: 0;
		font-size: 0.98rem;
		line-height: 1.55;
		color: var(--color-ink-100);
	}

	.landing-testimonial-cite {
		font-size: 0.84rem;
		font-style: normal;
		color: var(--color-ink-200);
	}

	.landing-compliance-block {
		margin-top: 1rem;
		border: 1px solid rgb(255 255 255 / 0.12);
		border-radius: var(--radius-lg);
		padding: 0.9rem;
		background: rgb(6 11 18 / 0.82);
	}

	.landing-compliance-block .landing-proof-k {
		color: var(--color-ink-100);
	}

	.landing-compliance-block .landing-trust-badge {
		background: rgb(8 13 20 / 0.9);
		color: var(--color-ink-100);
		border-color: rgb(255 255 255 / 0.22);
	}

	.landing-trust-note {
		margin: 0.9rem 0 0 0;
		font-size: 0.88rem;
		color: var(--color-ink-100);
		border: 1px solid rgb(255 255 255 / 0.12);
		border-radius: var(--radius-lg);
		padding: 0.6rem 0.75rem;
		background: rgb(6 11 18 / 0.86);
	}

	.landing-mobile-sticky-cta {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		z-index: 60;
		display: flex;
		gap: 0.6rem;
		padding: 0.75rem max(0.85rem, env(safe-area-inset-left)) calc(0.75rem + env(safe-area-inset-bottom))
			max(0.85rem, env(safe-area-inset-right));
		background: linear-gradient(180deg, rgb(2 6 11 / 0.35), rgb(2 6 11 / 0.94));
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
		border-top: 1px solid rgb(255 255 255 / 0.1);
		box-sizing: border-box;
	}

	.landing-mobile-sticky-cta :global(a) {
		flex: 1;
		justify-content: center;
		min-height: 2.7rem;
	}

	@media (max-width: 640px) {
		.landing-subtitle {
			font-size: 1.06rem;
			line-height: 1.62;
		}

		.landing-hook-switch {
			display: grid;
			grid-template-columns: repeat(2, minmax(0, 1fr));
			gap: 0.45rem;
		}

		.landing-demo-step,
		.signal-snapshot-btn,
		.landing-hook-switch-btn,
		.landing-buyer-btn {
			min-height: 2.5rem;
			padding: 0.5rem 0.78rem;
			font-size: 0.89rem;
		}

		.landing-hook-switch-btn {
			width: 100%;
			padding-inline: 0.6rem;
			letter-spacing: 0.03em;
		}
	}

	@media (min-width: 1024px) {
		.landing-evidence-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	@media (min-width: 768px) {
		.landing-mobile-sticky-cta {
			display: none;
		}
	}

	@media (max-width: 767px) {
		.landing {
			padding-bottom: 4.8rem;
		}
	}

</style>
