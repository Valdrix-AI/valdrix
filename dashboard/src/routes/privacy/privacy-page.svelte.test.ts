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
		const privacyMailLink = screen.getByRole('link', { name: /privacy@valdrics.ai/i });
		expect(privacyMailLink.getAttribute('href')).toBe('mailto:privacy@valdrics.ai');
	});
});
