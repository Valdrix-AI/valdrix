import { describe, expect, it } from 'vitest';
import {
	buildUnitEconomicsUrl,
	defaultDateWindow,
	formatDelta,
	hasInvalidUnitWindow,
	unitDeltaClass
} from './unitEconomics';

describe('ops unit economics helpers', () => {
	it('builds a stable default window from a fixed date', () => {
		const now = new Date('2026-02-12T16:30:00Z');
		const window = defaultDateWindow(30, now);

		expect(window.end).toBe('2026-02-12');
		expect(window.start).toBe('2026-01-14');
	});

	it('builds the expected API URL with alert flag', () => {
		const url = buildUnitEconomicsUrl(
			'https://api.example.com/api/v1',
			'2026-01-01',
			'2026-01-31',
			false
		);

		expect(url).toBe(
			'https://api.example.com/api/v1/costs/unit-economics?start_date=2026-01-01&end_date=2026-01-31&alert_on_anomaly=false'
		);
	});

	it('validates windows and delta rendering classes', () => {
		expect(hasInvalidUnitWindow('2026-02-20', '2026-02-19')).toBe(true);
		expect(hasInvalidUnitWindow('2026-02-19', '2026-02-19')).toBe(false);

		expect(formatDelta(5.123)).toBe('+5.12%');
		expect(formatDelta(-3.5)).toBe('-3.50%');

		expect(unitDeltaClass({ delta_percent: 10, is_anomalous: false })).toBe(
			'text-danger-400 font-semibold'
		);
		expect(unitDeltaClass({ delta_percent: -4, is_anomalous: false })).toBe(
			'text-success-400 font-semibold'
		);
		expect(unitDeltaClass({ delta_percent: 0, is_anomalous: false })).toBe('text-ink-300');
		expect(unitDeltaClass({ delta_percent: 0.1, is_anomalous: true })).toBe(
			'text-danger-400 font-semibold'
		);
	});
});
