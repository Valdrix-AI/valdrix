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
	wasteUsd?: number;
	actionLabel?: string;
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
			wasteUsd?: number;
			actionLabel?: string;
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
		title: 'Signal Scoped',
		subtitle: 'Issue + workload context attached',
		x: 138,
		y: 122,
		labelClass: 'signal-label--a'
	},
	{
		id: 'deterministic_enforcement',
		title: 'Checks Applied',
		subtitle: 'Policy + risk guardrails loaded',
		x: 488,
		y: 90,
		labelClass: 'signal-label--b'
	},
	{
		id: 'financial_governance',
		title: 'Approval Routed',
		subtitle: 'Owner + finance sign-off attached',
		x: 540,
		y: 302,
		labelClass: 'signal-label--c'
	},
	{
		id: 'operational_resilience',
		title: 'Outcome Recorded',
		subtitle: 'Decision trail + savings proof saved',
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
		headline: 'One issue moves from signal to owner without leaving the loop.',
		decisionSummary: 'The same record carries context, checks, approval, and proof.',
		lanes: {
			economic_visibility: {
				status: 'Watch',
				metric: 'Waste anomaly linked to shared-services workload',
				detail:
					'Affected workload, owner queue, and budget context are attached before anyone debates where the issue belongs.',
				severity: 'watch',
				wasteUsd: 12400,
				actionLabel: 'Assign Owner'
			},
			deterministic_enforcement: {
				status: 'Stable',
				metric: 'Pre-change guardrails loaded',
				detail:
					'Risk boundaries, blast-radius checks, and execution conditions stay attached before action moves forward.',
				severity: 'healthy'
			},
			financial_governance: {
				status: 'Stable',
				metric: 'Finance approver pre-routed',
				detail:
					'Budget owner and finance reviewer are already in the path before the remediation request is approved.',
				severity: 'healthy'
			},
			operational_resilience: {
				status: 'Stable',
				metric: 'Decision log prepared',
				detail:
					'If the action completes, rationale, owner, and savings proof are captured in one reviewable record.',
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
		headline: 'Owner and approval routing stay aligned before any change moves.',
		decisionSummary: 'Engineering, finance, and security review one chain instead of parallel threads.',
		lanes: {
			economic_visibility: {
				status: 'Stable',
				metric: 'Owner candidate confirmed',
				detail:
					'The issue is already scoped to the responsible team and workload before escalation starts.',
				severity: 'healthy'
			},
			deterministic_enforcement: {
				status: 'Watch',
				metric: 'Exception review required',
				detail:
					'One remediation path needs additional policy review before execution can proceed safely.',
				severity: 'watch',
				wasteUsd: 8200,
				actionLabel: 'Review Guardrails'
			},
			financial_governance: {
				status: 'Stable',
				metric: 'Approver chain complete',
				detail:
					'Budget owner, finance, and platform sign-off are visible in one route before approval is granted.',
				severity: 'healthy'
			},
			operational_resilience: {
				status: 'Stable',
				metric: 'Audit record linked',
				detail:
					'The future export record is already linked so leadership can review the full chain after execution.',
				severity: 'healthy'
			}
		},
		sources: ['Pricing decision records', 'Approval routing checks']
	},
	{
		id: 'snp-2026-02-28-c',
		label: 'Snapshot C',
		capturedAt: '2026-02-28T12:00:00Z',
		headline: 'Leadership can review one decision trail during cost pressure.',
		decisionSummary: 'The same record carries the owner, the check, the approval, and the proof.',
		lanes: {
			economic_visibility: {
				status: 'Stable',
				metric: 'Anomaly linked to product area',
				detail:
					'The spend movement is already scoped to the affected team so triage starts with accountable context.',
				severity: 'healthy'
			},
			deterministic_enforcement: {
				status: 'Stable',
				metric: 'Change checks rerun passed',
				detail:
					'Policy and execution checks validate the action path before anyone pushes a remediation forward.',
				severity: 'healthy'
			},
			financial_governance: {
				status: 'Watch',
				metric: 'Commercial limit review opened',
				detail:
					'The approval path is paused until the right commercial owner confirms the new boundary.',
				severity: 'watch',
				wasteUsd: 15800,
				actionLabel: 'Adjust Approval Limit'
			},
			operational_resilience: {
				status: 'Stable',
				metric: 'Executive summary queued',
				detail:
					'Leadership review gets a concise saved narrative once the action closes and proof is recorded.',
				severity: 'healthy'
			}
		},
		sources: ['Finance telemetry snapshot', 'Control gap register', 'Post-release sanity checks']
	},
	{
		id: 'snp-2026-03-01-d',
		label: 'Snapshot D',
		capturedAt: '2026-03-01T09:00:00Z',
		headline: 'Safety checks keep execution calm during remediation.',
		decisionSummary: 'Guardrails and rollback context stay visible before approval is granted.',
		lanes: {
			economic_visibility: {
				status: 'Stable',
				metric: 'Billing signal in sync',
				detail:
					'The spend event is scoped fast enough that owner routing begins before the issue hits close week.',
				severity: 'healthy'
			},
			deterministic_enforcement: {
				status: 'Stable',
				metric: 'Rollback plan attached',
				detail:
					'Risk checks and rollback context remain attached so remediation does not trade speed for control.',
				severity: 'healthy'
			},
			financial_governance: {
				status: 'Stable',
				metric: 'Forecast sign-off current',
				detail:
					'Approvers can see the financial impact before execution because the decision path holds forecast context.',
				severity: 'healthy'
			},
			operational_resilience: {
				status: 'Watch',
				metric: 'Proof export refresh needed',
				detail:
					'The record is ready to close, but the final outcome pack needs one more refresh before export.',
				severity: 'watch',
				wasteUsd: 9400,
				actionLabel: 'Refresh Record'
			}
		},
		sources: ['Resilience audit logs', 'Recovery playbook telemetry']
	},
	{
		id: 'snp-2026-03-02-e',
		label: 'Snapshot E (Global)',
		capturedAt: '2026-03-02T11:00:00Z',
		headline: 'Global spillover is routed through one accountable chain.',
		decisionSummary:
			'Cross-region spend pressure, sovereignty checks, and sign-off stay inside the same decision record.',
		lanes: {
			economic_visibility: {
				status: 'Watch',
				metric: 'Cross-region spike scoped',
				detail:
					'The anomaly is already tied to the responsible region, workload, and owner queue before triage starts.',
				severity: 'watch',
				wasteUsd: 21500,
				actionLabel: 'Open Owner Queue'
			},
			deterministic_enforcement: {
				status: 'Stable',
				metric: 'Sovereignty checks active',
				detail:
					'Regional guardrails remain attached so the remediation path respects data-locality and risk boundaries.',
				severity: 'healthy'
			},
			financial_governance: {
				status: 'Stable',
				metric: 'Regional approvers preloaded',
				detail:
					'The right commercial and operational approvers are already in the route before execution is approved.',
				severity: 'healthy'
			},
			operational_resilience: {
				status: 'Stable',
				metric: 'Global review pack ready',
				detail:
					'The final record is prepared so leaders can review cost, control, and outcome in one place.',
				severity: 'healthy'
			}
		},
		sources: ['Global egress telemetry', 'Data sovereignty checks']
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
