import { describe, expect, it } from 'vitest';
import { isPublicPath } from './routeProtection';

describe('isPublicPath', () => {
	it('treats landing as public', () => {
		expect(isPublicPath('/')).toBe(true);
	});

	it('treats auth routes as public', () => {
		expect(isPublicPath('/auth/login')).toBe(true);
		expect(isPublicPath('/auth/logout')).toBe(true);
	});

	it('treats pricing routes as public', () => {
		expect(isPublicPath('/pricing')).toBe(true);
		expect(isPublicPath('/pricing/compare')).toBe(true);
	});

	it('treats SvelteKit build assets as public', () => {
		expect(isPublicPath('/_app/immutable/entry/start.js')).toBe(true);
	});

	it('treats common static metadata as public', () => {
		expect(isPublicPath('/robots.txt')).toBe(true);
		expect(isPublicPath('/sitemap.xml')).toBe(true);
		expect(isPublicPath('/favicon.ico')).toBe(true);
		expect(isPublicPath('/og-image.png')).toBe(true);
	});

	it('treats legal pages as public', () => {
		expect(isPublicPath('/terms')).toBe(true);
		expect(isPublicPath('/privacy')).toBe(true);
	});

	it('treats docs and status routes as public', () => {
		expect(isPublicPath('/docs')).toBe(true);
		expect(isPublicPath('/docs/api')).toBe(true);
		expect(isPublicPath('/status')).toBe(true);
		expect(isPublicPath('/resources')).toBe(true);
		expect(isPublicPath('/insights')).toBe(true);
		expect(isPublicPath('/resources/valdrics-enterprise-one-pager.md')).toBe(true);
		expect(isPublicPath('/talk-to-sales')).toBe(true);
		expect(isPublicPath('/api/marketing/subscribe')).toBe(true);
	});

	it('protects app routes by default', () => {
		expect(isPublicPath('/ops')).toBe(false);
		expect(isPublicPath('/settings')).toBe(false);
		expect(isPublicPath('/connections')).toBe(false);
	});
});
