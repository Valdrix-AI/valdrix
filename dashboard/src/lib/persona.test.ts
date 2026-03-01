import { describe, expect, it } from 'vitest';
import { allowedNavHrefs, normalizePersona } from './persona';

describe('persona helpers', () => {
	it('normalizes unknown personas to engineering', () => {
		expect(normalizePersona(undefined)).toBe('engineering');
		expect(normalizePersona('')).toBe('engineering');
		expect(normalizePersona('UNKNOWN')).toBe('engineering');
	});

	it('returns finance allowlist without engineering-only routes', () => {
		const hrefs = allowedNavHrefs('finance', 'member');
		expect(hrefs.has('/billing')).toBe(true);
		expect(hrefs.has('/leaderboards')).toBe(true);
		expect(hrefs.has('/llm')).toBe(false);
		expect(hrefs.has('/settings')).toBe(true);
		expect(hrefs.has('/onboarding')).toBe(true);
		expect(hrefs.has('/roi-planner')).toBe(true);
	});

	it('removes admin-only routes for non-admin roles', () => {
		const hrefs = allowedNavHrefs('platform', 'member');
		expect(hrefs.has('/admin/health')).toBe(false);
		expect(hrefs.has('/ops')).toBe(true);
	});

	it('keeps admin-only routes for admin roles', () => {
		const hrefs = allowedNavHrefs('platform', 'admin');
		expect(hrefs.has('/admin/health')).toBe(true);
		expect(hrefs.has('/billing')).toBe(true);
	});
});
