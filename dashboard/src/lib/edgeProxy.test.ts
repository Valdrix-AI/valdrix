import { describe, expect, it, vi } from 'vitest';

vi.mock('$env/static/public', () => ({
	PUBLIC_API_URL: 'https://api.test.local/api/v1'
}));

vi.mock('$env/dynamic/public', () => ({
	env: {
		PUBLIC_API_URL: 'https://api.test.local/api/v1'
	}
}));

import { buildEdgeApiPath, edgeApiPath } from './edgeProxy';

describe('edgeProxy helpers', () => {
	it('builds proxied paths from absolute API base URLs', () => {
		expect(buildEdgeApiPath('https://api.example.com/api/v1', '/costs?start=2026-01-01')).toBe(
			'/api/edge/api/v1/costs?start=2026-01-01'
		);
	});

	it('normalizes relative API base URLs and missing leading slash', () => {
		expect(buildEdgeApiPath('api/v1', 'zombies?analyze=true')).toBe(
			'/api/edge/api/v1/zombies?analyze=true'
		);
	});

	it('handles root-path API base URLs without duplicating slashes', () => {
		expect(buildEdgeApiPath('https://api.example.com', '/health/live')).toBe(
			'/api/edge/health/live'
		);
	});

	it('uses PUBLIC_API_URL in edgeApiPath', () => {
		expect(edgeApiPath('/billing/subscription')).toBe('/api/edge/api/v1/billing/subscription');
	});
});
