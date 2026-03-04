import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/svelte';
import Page from './+page.svelte';

describe('privacy page', () => {
	it('renders production legal sections', () => {
		render(Page);

		expect(screen.getByRole('heading', { level: 1, name: /privacy policy/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /data we collect/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /legal bases/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /data retention/i })).toBeTruthy();
		expect(screen.getByRole('heading', { name: /data subject rights/i })).toBeTruthy();
		const privacyMailLink = screen.getByRole('link', { name: /privacy@valdrics.com/i });
		expect(privacyMailLink.getAttribute('href')).toBe('mailto:privacy@valdrics.com');
		const supportMailLink = screen.getByRole('link', { name: /support@valdrics.com/i });
		expect(supportMailLink.getAttribute('href')).toBe('mailto:support@valdrics.com');
		const securityMailLink = screen.getByRole('link', { name: /security@valdrics.com/i });
		expect(securityMailLink.getAttribute('href')).toBe('mailto:security@valdrics.com');
	});
});
