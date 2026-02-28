import { describe, expect, it } from 'vitest';
import {
	REALTIME_SIGNAL_SNAPSHOTS,
	SIGNAL_LANE_DEFINITIONS,
	SIGNAL_MAP_VIEWBOX,
	buildSnapshotTrace,
	lanePositionPercent,
	laneSeverityClass,
	nextSnapshotIndex
} from './realtimeSignalMap';

describe('realtimeSignalMap', () => {
	it('publishes deterministic snapshots with complete lane coverage', () => {
		expect(REALTIME_SIGNAL_SNAPSHOTS.length).toBeGreaterThan(0);

		for (const snapshot of REALTIME_SIGNAL_SNAPSHOTS) {
			expect(snapshot.lanes).toHaveLength(SIGNAL_LANE_DEFINITIONS.length);
			const laneIds = snapshot.lanes.map((lane) => lane.id).sort();
			expect(laneIds).toEqual([...SIGNAL_LANE_DEFINITIONS.map((lane) => lane.id)].sort());
			expect(Number.isNaN(Date.parse(snapshot.capturedAt))).toBe(false);
		}
	});

	it('produces stable trace ids for deterministic replay metadata', () => {
		const [first] = REALTIME_SIGNAL_SNAPSHOTS;
		expect(first).toBeDefined();
		if (!first) {
			return;
		}

		const computed = buildSnapshotTrace(first.id, first.capturedAt, first.decisionSummary);
		expect(computed).toBe(first.traceId);
		expect(computed).toMatch(/^TRC-[A-F0-9]{8}$/);
	});

	it('advances snapshot indices safely and wraps deterministically', () => {
		expect(nextSnapshotIndex(0, 3)).toBe(1);
		expect(nextSnapshotIndex(1, 3)).toBe(2);
		expect(nextSnapshotIndex(2, 3)).toBe(0);
		expect(nextSnapshotIndex(-1, 3)).toBe(0);
		expect(nextSnapshotIndex(Number.NaN, 3)).toBe(0);
		expect(nextSnapshotIndex(1, 0)).toBe(0);
	});

	it('maps severity values to explicit css state classes', () => {
		expect(laneSeverityClass('healthy')).toBe('is-healthy');
		expect(laneSeverityClass('watch')).toBe('is-watch');
		expect(laneSeverityClass('critical')).toBe('is-critical');
	});

	it('projects lane coordinates into bounded viewbox percentages', () => {
		const lane = SIGNAL_LANE_DEFINITIONS[0];
		expect(lane).toBeDefined();
		if (!lane) return;

		const position = lanePositionPercent(lane);
		expect(position.leftPct).toBeGreaterThanOrEqual(0);
		expect(position.leftPct).toBeLessThanOrEqual(100);
		expect(position.topPct).toBeGreaterThanOrEqual(0);
		expect(position.topPct).toBeLessThanOrEqual(100);

		expect(SIGNAL_MAP_VIEWBOX.width).toBe(640);
		expect(SIGNAL_MAP_VIEWBOX.height).toBe(420);
	});
});
