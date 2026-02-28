import { describe, expect, it } from 'vitest';
import {
	buildLandingWeeklyTrendChecks,
	captureLandingAttribution,
	incrementLandingFunnelStage,
	incrementLandingWeeklyStage,
	readLandingAttribution,
	readLandingFunnelReport,
	readLandingWeeklyFunnelReport
} from './landingFunnel';
import type { StorageLike } from './landingExperiment';

class MemoryStorage implements StorageLike {
	private readonly store = new Map<string, string>();

	getItem(key: string): string | null {
		return this.store.get(key) ?? null;
	}

	setItem(key: string, value: string): void {
		this.store.set(key, value);
	}
}

describe('landingFunnel', () => {
	it('captures utm attribution and preserves first touch timestamp', () => {
		const storage = new MemoryStorage();
		const first = captureLandingAttribution(
			new URL('https://example.com/?utm_source=google&utm_medium=cpc&utm_campaign=launch'),
			storage,
			new Date('2026-02-28T01:00:00.000Z')
		);
		const second = captureLandingAttribution(
			new URL('https://example.com/?utm_source=linkedin&utm_medium=social&utm_campaign=retarget'),
			storage,
			new Date('2026-02-28T02:00:00.000Z')
		);

		expect(first.utm.source).toBe('google');
		expect(second.utm.source).toBe('linkedin');
		expect(second.firstTouchAt).toBe('2026-02-28T01:00:00.000Z');
		expect(second.lastTouchAt).toBe('2026-02-28T02:00:00.000Z');
	});

	it('reads persisted attribution when no new utm params exist', () => {
		const storage = new MemoryStorage();
		captureLandingAttribution(
			new URL('https://example.com/?utm_source=partner&utm_medium=referral'),
			storage,
			new Date('2026-02-28T03:00:00.000Z')
		);

		const existing = captureLandingAttribution(new URL('https://example.com/'), storage);
		expect(existing.utm.source).toBe('partner');
		expect(readLandingAttribution(storage).utm.medium).toBe('referral');
	});

	it('increments funnel stage counters and computes conversion rates', () => {
		const storage = new MemoryStorage();
		incrementLandingFunnelStage('view', storage);
		incrementLandingFunnelStage('engaged', storage);
		incrementLandingFunnelStage('cta', storage);
		const report = incrementLandingFunnelStage('signup_intent', storage);

		expect(report.counts.view).toBe(1);
		expect(report.counts.engaged).toBe(1);
		expect(report.counts.cta).toBe(1);
		expect(report.counts.signup_intent).toBe(1);
		expect(report.conversion.engagementRate).toBe(1);
		expect(report.conversion.ctaRate).toBe(1);
		expect(report.conversion.signupIntentRate).toBe(1);
	});

	it('returns zero rates when no view events were captured', () => {
		const report = readLandingFunnelReport(new MemoryStorage());
		expect(report.counts.view).toBe(0);
		expect(report.conversion.engagementRate).toBe(0);
		expect(report.conversion.ctaRate).toBe(0);
		expect(report.conversion.signupIntentRate).toBe(0);
	});

	it('tracks weekly funnel windows and computes trend checks', () => {
		const storage = new MemoryStorage();

		incrementLandingWeeklyStage('view', storage, new Date('2026-02-16T12:00:00.000Z'));
		incrementLandingWeeklyStage('engaged', storage, new Date('2026-02-16T12:05:00.000Z'));
		incrementLandingWeeklyStage('view', storage, new Date('2026-02-23T12:00:00.000Z'));
		incrementLandingWeeklyStage('engaged', storage, new Date('2026-02-23T12:05:00.000Z'));
		incrementLandingWeeklyStage('cta', storage, new Date('2026-02-23T12:10:00.000Z'));
		incrementLandingWeeklyStage('signup_intent', storage, new Date('2026-02-23T12:15:00.000Z'));

		const weekly = readLandingWeeklyFunnelReport(storage, 8);
		expect(weekly).toHaveLength(2);
		expect(weekly[0]?.weekStart).toBe('2026-02-16');
		expect(weekly[1]?.weekStart).toBe('2026-02-23');
		expect(weekly[0]?.conversion.ctaRate).toBe(0);
		expect(weekly[1]?.conversion.ctaRate).toBe(1);

		const trends = buildLandingWeeklyTrendChecks(weekly);
		const ctaTrend = trends.find((trend) => trend.metric === 'ctaRate');
		const signupTrend = trends.find((trend) => trend.metric === 'signupIntentRate');
		expect(ctaTrend?.direction).toBe('up');
		expect(ctaTrend?.delta).toBe(1);
		expect(signupTrend?.direction).toBe('up');
		expect(signupTrend?.latest).toBe(1);
	});

	it('increments weekly aggregates when stage increments are recorded', () => {
		const storage = new MemoryStorage();
		incrementLandingFunnelStage('view', storage, new Date('2026-02-23T08:00:00.000Z'));
		incrementLandingFunnelStage('cta', storage, new Date('2026-02-23T08:05:00.000Z'));

		const weekly = readLandingWeeklyFunnelReport(storage, 1);
		expect(weekly).toHaveLength(1);
		expect(weekly[0]?.weekStart).toBe('2026-02-23');
		expect(weekly[0]?.counts.view).toBe(1);
		expect(weekly[0]?.counts.cta).toBe(1);
	});
});
