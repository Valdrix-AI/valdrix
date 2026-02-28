export type SignalLaneId =
	| 'economic_visibility'
	| 'deterministic_enforcement'
	| 'financial_governance'
	| 'operational_resilience';

export type SignalLaneSeverity = 'healthy' | 'watch' | 'critical';

export interface SignalLaneDefinition {
	id: SignalLaneId;
	title: string;
	subtitle: string;
	x: number;
	y: number;
	labelClass: string;
}

export interface SignalLaneSnapshot extends SignalLaneDefinition {
	status: string;
	metric: string;
	detail: string;
	severity: SignalLaneSeverity;
}

interface SignalSnapshotInput {
	id: string;
	label: string;
	capturedAt: string;
	headline: string;
	decisionSummary: string;
	lanes: Record<
		SignalLaneId,
		{
			status: string;
			metric: string;
			detail: string;
			severity: SignalLaneSeverity;
		}
	>;
	sources: readonly string[];
}

export interface SignalSnapshot {
	id: string;
	label: string;
	capturedAt: string;
	headline: string;
	decisionSummary: string;
	traceId: string;
	lanes: readonly SignalLaneSnapshot[];
	sources: readonly string[];
}

export const SIGNAL_MAP_VIEWBOX = Object.freeze({
	width: 640,
	height: 420
});

export const SIGNAL_LANE_DEFINITIONS: readonly SignalLaneDefinition[] = Object.freeze([
	{
		id: 'economic_visibility',
		title: 'Economic Visibility',
		subtitle: 'Spend + attribution telemetry',
		x: 138,
		y: 122,
		labelClass: 'signal-label--a'
	},
	{
		id: 'deterministic_enforcement',
		title: 'Execution Controls',
		subtitle: 'Policy checks + approvals',
		x: 488,
		y: 90,
		labelClass: 'signal-label--b'
	},
	{
		id: 'financial_governance',
		title: 'Financial Governance',
		subtitle: 'Approvals + ceilings',
		x: 540,
		y: 302,
		labelClass: 'signal-label--c'
	},
	{
		id: 'operational_resilience',
		title: 'Operational Resilience',
		subtitle: 'Failure drills + replay',
		x: 170,
		y: 320,
		labelClass: 'signal-label--d'
	}
]);

const RAW_SIGNAL_SNAPSHOTS: readonly SignalSnapshotInput[] = [
	{
		id: 'snp-2026-02-27-a',
		label: 'Snapshot A',
		capturedAt: '2026-02-27T20:55:58Z',
		headline: 'Signal quality stays stable as workloads change.',
		decisionSummary: 'Teams can prioritize cost and risk from one shared view.',
		lanes: {
			economic_visibility: {
				status: 'Stable',
				metric: 'Attribution + anomaly telemetry current',
				detail: 'Telemetry and pricing references match the release evidence packet.',
				severity: 'healthy'
			},
			deterministic_enforcement: {
				status: 'Watch',
				metric: 'Gate expansion in progress',
				detail: 'Policy controls are enforced at API boundaries with tier-aware guards.',
				severity: 'watch'
			},
			financial_governance: {
				status: 'Stable',
				metric: 'Policy decisions codified',
				detail: 'Commercial boundaries and migration windows are explicitly documented.',
				severity: 'healthy'
			},
			operational_resilience: {
				status: 'Stable',
				metric: 'Stress and failure evidence present',
				detail: 'Stress and failure-injection artifacts are attached and verifiable.',
				severity: 'healthy'
			}
		},
		sources: [
			'docs/ops/feature_enforceability_matrix_2026-02-27.json',
			'docs/ops/evidence/enforcement_stress_artifact_2026-02-27.json',
			'docs/ops/evidence/enforcement_failure_injection_2026-02-27.json'
		]
	},
	{
		id: 'snp-2026-02-28-b',
		label: 'Snapshot B',
		capturedAt: '2026-02-28T06:30:00Z',
		headline: 'Approval workflows keep decisions coordinated.',
		decisionSummary: 'Platform and finance stay aligned before operational changes.',
		lanes: {
			economic_visibility: {
				status: 'Stable',
				metric: 'Unit economics window validated',
				detail: 'Tier economics include starter, growth, pro, and enterprise coverage.',
				severity: 'healthy'
			},
			deterministic_enforcement: {
				status: 'Stable',
				metric: 'Approval routing active',
				detail: 'Approval sign-offs include finance, product, and go-to-market ownership.',
				severity: 'healthy'
			},
			financial_governance: {
				status: 'Watch',
				metric: 'Pricing motion intentionally locked',
				detail:
					'Commercial changes remain blocked until post-launch telemetry confirms guardrails.',
				severity: 'watch'
			},
			operational_resilience: {
				status: 'Stable',
				metric: 'Deterministic replay posture maintained',
				detail: 'Post-closure sanity policy enforces replay and failure-mode validation.',
				severity: 'healthy'
			}
		},
		sources: [
			'docs/ops/evidence/pkg_fin_policy_decisions_2026-02-28.json',
			'docs/ops/enforcement_control_plane_gap_register_2026-02-23.md'
		]
	},
	{
		id: 'snp-2026-02-28-c',
		label: 'Snapshot C',
		capturedAt: '2026-02-28T12:00:00Z',
		headline: 'Cross-team response stays calm during cost pressure.',
		decisionSummary: 'Leaders can triage faster with shared context and clear ownership.',
		lanes: {
			economic_visibility: {
				status: 'Stable',
				metric: '490 active subscriptions in telemetry set',
				detail: 'Telemetry snapshot includes active tenant and dunning profile by tier.',
				severity: 'healthy'
			},
			deterministic_enforcement: {
				status: 'Stable',
				metric: 'Evidence gate rerun passed',
				detail: 'Release evidence gate passed with full evidence-pack integrity checks.',
				severity: 'healthy'
			},
			financial_governance: {
				status: 'Stable',
				metric: 'Free-tier margin watch bounded',
				detail: 'Free-tier LLM cost remains bounded against starter gross MRR guardrails.',
				severity: 'healthy'
			},
			operational_resilience: {
				status: 'Watch',
				metric: 'Operational follow-through required',
				detail:
					'Remaining PKG/FIN items are operating-policy cadence, not core implementation gaps.',
				severity: 'watch'
			}
		},
		sources: [
			'docs/ops/evidence/finance_telemetry_snapshot_2026-02-28.json',
			'docs/ops/enforcement_control_plane_gap_register_2026-02-23.md',
			'docs/ops/enforcement_post_closure_sanity_2026-02-26.md'
		]
	}
] as const;

export function nextSnapshotIndex(currentIndex: number, totalSnapshots: number): number {
	if (!Number.isFinite(totalSnapshots) || totalSnapshots <= 0) {
		return 0;
	}
	if (!Number.isFinite(currentIndex)) {
		return 0;
	}

	const normalizedTotal = Math.floor(totalSnapshots);
	const normalizedCurrent = Math.trunc(currentIndex);
	const safeCurrent = ((normalizedCurrent % normalizedTotal) + normalizedTotal) % normalizedTotal;
	return (safeCurrent + 1) % normalizedTotal;
}

export function laneSeverityClass(severity: SignalLaneSeverity): string {
	switch (severity) {
		case 'healthy':
			return 'is-healthy';
		case 'critical':
			return 'is-critical';
		case 'watch':
		default:
			return 'is-watch';
	}
}

export function lanePositionPercent(lane: Pick<SignalLaneDefinition, 'x' | 'y'>): {
	leftPct: number;
	topPct: number;
} {
	const leftPct = Math.max(
		0,
		Math.min(100, Number(((lane.x / SIGNAL_MAP_VIEWBOX.width) * 100).toFixed(3)))
	);
	const topPct = Math.max(
		0,
		Math.min(100, Number(((lane.y / SIGNAL_MAP_VIEWBOX.height) * 100).toFixed(3)))
	);
	return { leftPct, topPct };
}

export function buildSnapshotTrace(
	snapshotId: string,
	capturedAt: string,
	summary: string
): string {
	const value = `${snapshotId}|${capturedAt}|${summary}`;
	let hash = 0x811c9dc5;

	for (let index = 0; index < value.length; index += 1) {
		hash ^= value.charCodeAt(index);
		hash = Math.imul(hash, 0x01000193);
	}

	return `TRC-${(hash >>> 0).toString(16).toUpperCase().padStart(8, '0')}`;
}

function hydrateSnapshot(input: SignalSnapshotInput): SignalSnapshot {
	const lanes = SIGNAL_LANE_DEFINITIONS.map((lane) => {
		const state = input.lanes[lane.id];
		return Object.freeze({
			...lane,
			...state
		});
	});

	return Object.freeze({
		id: input.id,
		label: input.label,
		capturedAt: input.capturedAt,
		headline: input.headline,
		decisionSummary: input.decisionSummary,
		traceId: buildSnapshotTrace(input.id, input.capturedAt, input.decisionSummary),
		lanes: Object.freeze(lanes),
		sources: Object.freeze([...input.sources])
	});
}

export const REALTIME_SIGNAL_SNAPSHOTS: readonly SignalSnapshot[] = Object.freeze(
	RAW_SIGNAL_SNAPSHOTS.map((snapshot) => hydrateSnapshot(snapshot))
);
