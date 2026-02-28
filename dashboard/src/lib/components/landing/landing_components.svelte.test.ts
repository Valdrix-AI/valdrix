import { describe, expect, it } from 'vitest';
import {
	REALTIME_SIGNAL_SNAPSHOTS,
	lanePositionPercent,
	laneSeverityClass
} from '$lib/landing/realtimeSignalMap';
import { PUBLIC_MOBILE_LINKS, PUBLIC_PRIMARY_LINKS, PUBLIC_SIGNAL_STRIP } from '$lib/landing/publicNav';

describe('Landing Component Data Hardening', () => {
	it('provides stable realtime snapshots with unique lane ids', () => {
		expect(REALTIME_SIGNAL_SNAPSHOTS.length).toBeGreaterThanOrEqual(3);
		for (const snapshot of REALTIME_SIGNAL_SNAPSHOTS) {
			const laneIds = new Set(snapshot.lanes.map((lane) => lane.id));
			expect(laneIds.size).toBe(snapshot.lanes.length);
			expect(snapshot.headline.length).toBeGreaterThan(10);
			expect(snapshot.decisionSummary.length).toBeGreaterThan(10);
		}
	});

	it('normalizes lane classes and positions into render-safe values', () => {
		const firstLane = REALTIME_SIGNAL_SNAPSHOTS[0]?.lanes[0];
		expect(firstLane).toBeTruthy();
		if (!firstLane) return;
		expect(['is-healthy', 'is-watch', 'is-critical']).toContain(laneSeverityClass(firstLane.severity));
		const pos = lanePositionPercent(firstLane);
		expect(pos.leftPct).toBeGreaterThanOrEqual(0);
		expect(pos.leftPct).toBeLessThanOrEqual(100);
		expect(pos.topPct).toBeGreaterThanOrEqual(0);
		expect(pos.topPct).toBeLessThanOrEqual(100);
	});

	it('keeps public navigation focused on buyer-facing routes and signal copy', () => {
		expect(PUBLIC_PRIMARY_LINKS.some((link) => link.href === '/#benefits')).toBe(true);
		expect(PUBLIC_PRIMARY_LINKS.some((link) => link.href === '/pricing')).toBe(true);
		expect(PUBLIC_MOBILE_LINKS.some((link) => link.href === '/#trust')).toBe(true);
		expect(PUBLIC_SIGNAL_STRIP.length).toBeGreaterThanOrEqual(3);
	});
});
