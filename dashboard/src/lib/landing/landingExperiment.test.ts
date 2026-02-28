import { describe, expect, it } from 'vitest';
import {
	resolveLandingExperiments,
	resolveOrCreateLandingVisitorId,
	shouldIncludeExperimentQueryParams,
	type StorageLike
} from './landingExperiment';

class MemoryStorage implements StorageLike {
	private readonly store = new Map<string, string>();

	getItem(key: string): string | null {
		return this.store.get(key) ?? null;
	}

	setItem(key: string, value: string): void {
		this.store.set(key, value);
	}
}

describe('landingExperiment', () => {
	it('persists and reuses deterministic visitor ids once generated', () => {
		const storage = new MemoryStorage();
		const created = resolveOrCreateLandingVisitorId(storage, new Date('2026-02-28T00:00:00.000Z'));
		const reused = resolveOrCreateLandingVisitorId(storage, new Date('2030-02-28T00:00:00.000Z'));
		expect(created).toMatch(/^vldx-[a-f0-9]{8}-[a-f0-9]{8}$/);
		expect(reused).toBe(created);
	});

	it('returns stable default assignments when no overrides are provided', () => {
		const url = new URL('https://example.com/');
		const first = resolveLandingExperiments(url, 'visitor-123');
		const second = resolveLandingExperiments(url, 'visitor-123');
		expect(second).toEqual(first);
		expect(first.buyerPersonaDefault).toBe('cto');
		expect(first.heroVariant).toBe('control_every_dollar');
		expect(first.ctaVariant).toBe('start_free');
		expect(first.sectionOrderVariant).toBe('problem_first');
	});

	it('supports explicit url overrides for buyer and experiment variants', () => {
		const url = new URL(
			'https://example.com/?buyer=cfo&exp_hero=from_metrics_to_control&exp_cta=book_briefing&exp_order=workflow_first'
		);
		const assignment = resolveLandingExperiments(url, 'visitor-override');
		expect(assignment.buyerPersonaDefault).toBe('cfo');
		expect(assignment.heroVariant).toBe('from_metrics_to_control');
		expect(assignment.ctaVariant).toBe('book_briefing');
		expect(assignment.sectionOrderVariant).toBe('workflow_first');
	});

	it('ignores invalid overrides and falls back to defaults', () => {
		const url = new URL(
			'https://example.com/?buyer=invalid&exp_hero=invalid&exp_cta=invalid&exp_order=invalid'
		);
		const assignment = resolveLandingExperiments(url, 'visitor-fallback');
		expect(assignment.buyerPersonaDefault).toBe('cto');
		expect(assignment.heroVariant).toBe('control_every_dollar');
		expect(assignment.ctaVariant).toBe('start_free');
		expect(assignment.sectionOrderVariant).toBe('problem_first');
	});

	it('exposes experiment params only in dev or explicit QA mode', () => {
		expect(shouldIncludeExperimentQueryParams(new URL('https://example.com/'), false)).toBe(false);
		expect(
			shouldIncludeExperimentQueryParams(new URL('https://example.com/?qa_exp=1'), false)
		).toBe(true);
		expect(
			shouldIncludeExperimentQueryParams(new URL('https://example.com/?qa_exp=true'), false)
		).toBe(true);
		expect(shouldIncludeExperimentQueryParams(new URL('https://example.com/'), true)).toBe(true);
	});
});
