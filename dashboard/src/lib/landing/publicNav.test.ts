import { describe, expect, it } from 'vitest';
import {
	PUBLIC_FOOTER_BADGES,
	PUBLIC_CONTACT_CHANNELS,
	PUBLIC_FOOTER_LINKS,
	PUBLIC_MOBILE_LINKS,
	PUBLIC_PRIMARY_LINKS,
	PUBLIC_RESOURCES_DROPDOWN_LINKS,
	PUBLIC_SECONDARY_LINKS,
	PUBLIC_SIGNAL_STRIP
} from './publicNav';

const LINK_GROUPS = [
	PUBLIC_PRIMARY_LINKS,
	PUBLIC_SECONDARY_LINKS,
	PUBLIC_MOBILE_LINKS,
	PUBLIC_FOOTER_LINKS
];

describe('publicNav', () => {
	it('keeps public navigation free of proof-pack and internal audit paths', () => {
		for (const links of LINK_GROUPS) {
			for (const link of links) {
				expect(link.href.toLowerCase()).not.toContain('/proof');
				expect(link.label.toLowerCase()).not.toContain('audit');
				expect(link.label.toLowerCase()).not.toContain('telemetry');
				expect(link.label.toLowerCase()).not.toContain('capture');
			}
		}
	});

	it('uses valid href semantics for internal and external links', () => {
		for (const links of LINK_GROUPS) {
			for (const link of links) {
				if (link.external) {
					expect(link.href.startsWith('https://')).toBe(true);
					continue;
				}
				expect(link.href.startsWith('/')).toBe(true);
			}
		}
	});

	it('has no duplicates in each link group', () => {
		for (const links of LINK_GROUPS) {
			const labels = links.map((link) => link.label);
			const hrefs = links.map((link) => link.href);
			expect(new Set(labels).size).toBe(labels.length);
			expect(new Set(hrefs).size).toBe(hrefs.length);
		}
	});

	it('keeps landing jump links aligned to active default-page sections', () => {
		expect(PUBLIC_PRIMARY_LINKS.some((link) => link.href === '/#product')).toBe(true);
		expect(PUBLIC_PRIMARY_LINKS.some((link) => link.href === '/#signal-map')).toBe(true);
		expect(PUBLIC_PRIMARY_LINKS.some((link) => link.href === '/#simulator')).toBe(true);
		expect(PUBLIC_MOBILE_LINKS.some((link) => link.href === '/#product')).toBe(true);
		expect(PUBLIC_MOBILE_LINKS.some((link) => link.href === '/#signal-map')).toBe(true);
		expect(PUBLIC_MOBILE_LINKS.some((link) => link.href === '/#simulator')).toBe(true);
		expect(PUBLIC_PRIMARY_LINKS.some((link) => link.href === '/#workflow')).toBe(false);
		expect(PUBLIC_PRIMARY_LINKS.some((link) => link.href === '/#benefits')).toBe(false);
		expect(PUBLIC_MOBILE_LINKS.some((link) => link.href === '/#workflow')).toBe(false);
		expect(PUBLIC_MOBILE_LINKS.some((link) => link.href === '/#benefits')).toBe(false);
	});

	it('keeps proof, enterprise, docs, and pricing routes surfaced consistently', () => {
		expect(PUBLIC_RESOURCES_DROPDOWN_LINKS.some((link) => link.href === '/#trust')).toBe(true);
		expect(PUBLIC_FOOTER_LINKS.some((link) => link.href === '/#trust')).toBe(true);
		expect(PUBLIC_PRIMARY_LINKS.some((link) => link.href === '/pricing')).toBe(true);
		expect(PUBLIC_MOBILE_LINKS.some((link) => link.href === '/pricing')).toBe(true);
		expect(PUBLIC_FOOTER_LINKS.some((link) => link.href === '/pricing')).toBe(true);
		expect(PUBLIC_PRIMARY_LINKS.some((link) => link.href === '/enterprise')).toBe(true);
		expect(PUBLIC_MOBILE_LINKS.some((link) => link.href === '/enterprise')).toBe(true);
		expect(PUBLIC_FOOTER_LINKS.some((link) => link.href === '/enterprise')).toBe(true);
		expect(PUBLIC_SECONDARY_LINKS.some((link) => link.href === '/docs')).toBe(true);
		expect(PUBLIC_SECONDARY_LINKS.some((link) => link.href === '/insights')).toBe(true);
		expect(PUBLIC_FOOTER_LINKS.some((link) => link.href === '/insights')).toBe(true);
		expect(PUBLIC_SECONDARY_LINKS.some((link) => link.href === '/talk-to-sales')).toBe(true);
		expect(PUBLIC_FOOTER_LINKS.some((link) => link.href === '/talk-to-sales')).toBe(true);
		expect(PUBLIC_MOBILE_LINKS.some((link) => link.href === '/resources')).toBe(true);
		expect(PUBLIC_RESOURCES_DROPDOWN_LINKS.some((link) => link.href === '/docs')).toBe(true);
	});

	it('keeps only customer-facing strip and badge language', () => {
		const joined = [...PUBLIC_SIGNAL_STRIP, ...PUBLIC_FOOTER_BADGES].join(' ').toLowerCase();
		expect(joined).not.toContain('trace');
		expect(joined).not.toContain('capture');
		expect(joined).not.toContain('telemetry');
		expect(joined).not.toContain('audit');
	});

	it('keeps footer contact channels aligned to valdrics.com mailboxes', () => {
		expect(PUBLIC_CONTACT_CHANNELS.length).toBeGreaterThanOrEqual(3);
		for (const channel of PUBLIC_CONTACT_CHANNELS) {
			expect(channel.href.startsWith('mailto:')).toBe(true);
			expect(channel.email.endsWith('@valdrics.com')).toBe(true);
			expect(channel.href).toBe(`mailto:${channel.email}`);
		}
	});
});
