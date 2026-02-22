import { describe, expect, it } from 'vitest';
import { canUseE2EAuthBypass, isLocalHostname, shouldUseSecureCookies } from './serverSecurity';

describe('serverSecurity', () => {
	describe('isLocalHostname', () => {
		it('detects local loopback hostnames', () => {
			expect(isLocalHostname('localhost')).toBe(true);
			expect(isLocalHostname('127.0.0.1')).toBe(true);
			expect(isLocalHostname('::1')).toBe(true);
			expect(isLocalHostname('api.valdrix.ai')).toBe(false);
		});
	});

	describe('shouldUseSecureCookies', () => {
		it('uses secure cookies for https requests', () => {
			expect(shouldUseSecureCookies(new URL('https://app.valdrix.ai/'), 'production')).toBe(true);
		});

		it('keeps secure cookies disabled for localhost over http', () => {
			expect(shouldUseSecureCookies(new URL('http://localhost:4173/'), 'development')).toBe(false);
		});

		it('fails closed in production on non-local http URLs', () => {
			expect(shouldUseSecureCookies(new URL('http://app.valdrix.ai/'), 'production')).toBe(true);
		});
	});

	describe('canUseE2EAuthBypass', () => {
		it('allows bypass during dev builds with testing mode', () => {
			expect(
				canUseE2EAuthBypass({
					testingMode: true,
					allowProdPreviewBypass: false,
					isDevBuild: true,
					hostname: 'localhost'
				})
			).toBe(true);
		});

		it('allows production preview bypass only on localhost', () => {
			expect(
				canUseE2EAuthBypass({
					testingMode: true,
					allowProdPreviewBypass: true,
					isDevBuild: false,
					hostname: '127.0.0.1'
				})
			).toBe(true);
			expect(
				canUseE2EAuthBypass({
					testingMode: true,
					allowProdPreviewBypass: true,
					isDevBuild: false,
					hostname: 'app.valdrix.ai'
				})
			).toBe(false);
		});

		it('denies bypass when testing mode is off', () => {
			expect(
				canUseE2EAuthBypass({
					testingMode: false,
					allowProdPreviewBypass: true,
					isDevBuild: true,
					hostname: 'localhost'
				})
			).toBe(false);
		});
	});
});
