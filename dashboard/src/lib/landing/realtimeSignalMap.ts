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
		subtitle: 'Risk checks + approvals',
		x: 488,
		y: 90,
		labelClass: 'signal-label--b'
	},
	{
		id: 'financial_governance',
		title: 'Financial Governance',
		subtitle: 'Budgets + ownership',
		x: 540,
		y: 302,
		labelClass: 'signal-label--c'
	},
	{
		id: 'operational_resilience',
		title: 'Operational Resilience',
		subtitle: 'Continuity + response',
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
				detail: 'Cost and usage signals are aligned across connected environments.',
				severity: 'healthy'
			},
			deterministic_enforcement: {
				status: 'Watch',
				metric: 'Coverage expansion in progress',
				detail: 'More high-impact actions are being moved into pre-change checks and approvals.',
				severity: 'watch'
			},
			financial_governance: {
				status: 'Stable',
				metric: 'Budget thresholds aligned',
				detail:
					'Budget boundaries and escalation paths stay aligned across finance and engineering.',
				severity: 'healthy'
			},
			operational_resilience: {
				status: 'Stable',
				metric: 'Response drills completed',
				detail: 'Teams have practiced response paths so action stays calm during cost pressure.',
				severity: 'healthy'
			}
		},
		sources: [
			'Cloud cost telemetry',
			'Stress and failure drill evidence',
			'Execution coverage report'
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
				metric: 'Unit economics baseline validated',
				detail:
					'Pricing assumptions stay aligned across starter, growth, pro, and enterprise plans.',
				severity: 'healthy'
			},
			deterministic_enforcement: {
				status: 'Stable',
				metric: 'Approval routing active',
				detail: 'Approval sign-offs include finance, product, and engineering owners.',
				severity: 'healthy'
			},
			financial_governance: {
				status: 'Watch',
				metric: 'Pricing updates intentionally paused',
				detail: 'Commercial changes stay paused until more live operating data is collected.',
				severity: 'watch'
			},
			operational_resilience: {
				status: 'Stable',
				metric: 'Replay and rollback readiness maintained',
				detail: 'Critical action paths are tested for predictable rollback and recovery.',
				severity: 'healthy'
			}
		},
		sources: ['Pricing decision records', 'Approval routing checks']
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
				detail: 'Current subscription mix gives teams a representative operating baseline.',
				severity: 'healthy'
			},
			deterministic_enforcement: {
				status: 'Stable',
				metric: 'Release checks rerun passed',
				detail: 'Release checks validate that control paths and exports remain intact.',
				severity: 'healthy'
			},
			financial_governance: {
				status: 'Stable',
				metric: 'Free-tier margin watch bounded',
				detail: 'Free-tier compute usage remains bounded against starter-tier economics.',
				severity: 'healthy'
			},
			operational_resilience: {
				status: 'Watch',
				metric: 'Operational follow-through required',
				detail: 'Remaining items are operational cadence tasks, not core product capability gaps.',
				severity: 'watch'
			}
		},
		sources: ['Finance telemetry snapshot', 'Control gap register', 'Post-release sanity checks']
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
