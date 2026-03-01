import { describe, expect, it } from 'vitest';

import {
	buildAuthCallbackPath,
	buildPostAuthRedirectPath,
	describePublicIntent,
	describePublicPersona,
	parsePublicAuthContext
} from './publicAuthIntent';

describe('publicAuthIntent', () => {
	it('defaults to login mode with no marketing context', () => {
		const context = parsePublicAuthContext(new URL('https://example.com/auth/login'));
		expect(context.mode).toBe('login');
		expect(context.intent).toBeUndefined();
		expect(context.persona).toBeUndefined();
		expect(context.nextPath).toBeUndefined();
		expect(buildPostAuthRedirectPath(context)).toBe('/');
	});

	it('auto-switches to signup mode when landing intent exists without explicit mode', () => {
		const context = parsePublicAuthContext(
			new URL(
				'https://example.com/auth/login?intent=roi_assessment&persona=cfo&utm_source=google&utm_medium=cpc'
			)
		);
		expect(context.mode).toBe('signup');
		expect(context.intent).toBe('roi_assessment');
		expect(context.persona).toBe('cfo');
		expect(describePublicIntent(context.intent)).toBe('ROI Assessment');
		expect(describePublicPersona(context.persona)).toBe('CFO');
		expect(buildPostAuthRedirectPath(context)).toBe(
			'/roi-planner?intent=roi_assessment&persona=cfo&utm_source=google&utm_medium=cpc'
		);
		expect(buildAuthCallbackPath(context)).toBe(
			'/auth/callback?next=%2Froi-planner%3Fintent%3Droi_assessment%26persona%3Dcfo%26utm_source%3Dgoogle%26utm_medium%3Dcpc'
		);
	});

	it('respects explicit login mode even with marketing intent', () => {
		const context = parsePublicAuthContext(
			new URL('https://example.com/auth/login?mode=login&intent=engineering_control&persona=cto')
		);
		expect(context.mode).toBe('login');
		expect(buildPostAuthRedirectPath(context)).toBe(
			'/onboarding?intent=engineering_control&persona=cto'
		);
	});

	it('keeps only safe next paths and rejects open redirects', () => {
		const safe = parsePublicAuthContext(
			new URL('https://example.com/auth/login?mode=login&next=%2Fops%3Ftab%3Dsignals')
		);
		expect(safe.nextPath).toBe('/ops?tab=signals');
		expect(buildPostAuthRedirectPath(safe)).toBe('/ops?tab=signals');

		const external = parsePublicAuthContext(
			new URL('https://example.com/auth/login?mode=login&next=https://evil.example')
		);
		expect(external.nextPath).toBeUndefined();
		expect(buildPostAuthRedirectPath(external)).toBe('/');

		const protocolRelative = parsePublicAuthContext(
			new URL('https://example.com/auth/login?mode=login&next=%2F%2Fevil.example')
		);
		expect(protocolRelative.nextPath).toBeUndefined();
		expect(buildPostAuthRedirectPath(protocolRelative)).toBe('/');
	});
});
