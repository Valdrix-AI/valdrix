import { describe, expect, it, vi } from 'vitest';
import { buildLandingTelemetryEvent, emitLandingTelemetry } from './landingTelemetry';

describe('landingTelemetry', () => {
	it('builds normalized deterministic payloads', () => {
		const payload = buildLandingTelemetryEvent('  cta_click  ', ' hero ', ' start_free ', {}, new Date(0));
		expect(payload).toMatchObject({
			name: 'cta_click',
			section: 'hero',
			value: 'start_free',
			timestamp: '1970-01-01T00:00:00.000Z'
		});
		expect(payload.eventId).toMatch(/^evt-/);
	});

	it('falls back when action/section are blank and trims oversized values', () => {
		const oversized = 'x'.repeat(300);
		const payload = buildLandingTelemetryEvent('', '', oversized, {}, new Date(0));
		expect(payload.name).toBe('unknown_action');
		expect(payload.section).toBe('unknown_section');
		expect(payload.value).toHaveLength(96);
	});

	it('includes funnel, experiment, and utm context when provided', () => {
		const payload = buildLandingTelemetryEvent(
			'landing_view',
			'landing',
			'public',
			{
				visitorId: 'visitor-1',
				persona: 'finops',
				funnelStage: 'view',
				experiment: {
					hero: 'control_every_dollar',
					cta: 'start_free',
					order: 'problem_first'
				},
				utm: {
					source: 'google',
					medium: 'cpc',
					campaign: 'launch'
				}
			},
			new Date(0)
		);
		expect(payload.visitorId).toBe('visitor-1');
		expect(payload.persona).toBe('finops');
		expect(payload.funnelStage).toBe('view');
		expect(payload.experiment?.hero).toBe('control_every_dollar');
		expect(payload.utm?.source).toBe('google');
	});

	it('dispatches custom events and pushes data layer payloads when target is configured', () => {
		const dispatchEvent = vi.fn();
		const customEvent = {} as Event;
		const createCustomEvent = vi.fn(() => customEvent);
		const dataLayer: unknown[] = [];
		const sendToBackend = vi.fn();

		const payload = emitLandingTelemetry('hook_toggle', 'cloud_hook', 'with', {
			dispatchEvent,
			createCustomEvent,
			dataLayer,
			sendToBackend
		});

		expect(createCustomEvent).toHaveBeenCalledTimes(1);
		expect(createCustomEvent).toHaveBeenCalledWith('valdrix:landing_event', {
			detail: payload
		});
		expect(dispatchEvent).toHaveBeenCalledWith(customEvent);
		expect(dataLayer).toHaveLength(1);
		expect(dataLayer[0]).toMatchObject({
			event: 'valdrix_landing_event',
			name: 'hook_toggle',
			section: 'cloud_hook',
			value: 'with'
		});
		expect(sendToBackend).toHaveBeenCalledOnce();
		expect(sendToBackend).toHaveBeenCalledWith(payload);
	});

	it('never throws when dispatch fails and still returns payload', () => {
		const payload = emitLandingTelemetry('cta_click', 'hero', 'start_free', {
			dispatchEvent: () => {
				throw new Error('synthetic failure');
			},
			createCustomEvent: () => ({} as Event)
		});

		expect(payload.name).toBe('cta_click');
		expect(payload.section).toBe('hero');
		expect(payload.value).toBe('start_free');
	});

	it('is safe to call without browser globals', () => {
		const payload = emitLandingTelemetry('section_view', 'landing');
		expect(payload.name).toBe('section_view');
		expect(payload.section).toBe('landing');
	});

	it('never throws when backend transport callback errors', () => {
		const payload = emitLandingTelemetry('cta_click', 'hero', 'start_free', {
			sendToBackend: () => {
				throw new Error('backend down');
			}
		});
		expect(payload.name).toBe('cta_click');
	});

	it('accepts context and target simultaneously with backward-compatible signature', () => {
		const dispatchEvent = vi.fn();
		const dataLayer: unknown[] = [];

		const payload = emitLandingTelemetry(
			'cta_click',
			'hero',
			'book_briefing',
			{
				visitorId: 'visitor-2',
				funnelStage: 'cta'
			},
			{ dispatchEvent, dataLayer, createCustomEvent: () => ({} as Event) }
		);

		expect(payload.visitorId).toBe('visitor-2');
		expect(payload.funnelStage).toBe('cta');
		expect(dispatchEvent).toHaveBeenCalledTimes(1);
		expect(dataLayer).toHaveLength(1);
	});
});
