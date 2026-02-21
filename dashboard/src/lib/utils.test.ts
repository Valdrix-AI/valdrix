/* eslint-disable no-constant-binary-expression */
import { describe, it, expect } from 'vitest';
import { cn, normalizeCheckoutUrl } from './utils';

describe('cn utility', () => {
	it('merges class names correctly', () => {
		expect(cn('btn', 'btn-primary')).toBe('btn btn-primary');
	});

	it('handles conditional classes', () => {
		expect(cn('btn', 1 > 0 && 'active', 1 < 0 && 'hidden')).toBe('btn active');
	});

	it('resolves tailwind conflicts', () => {
		// p-4 and p-2 conflict, p-2 should win if it comes later
		expect(cn('p-4', 'p-2')).toBe('p-2');
		expect(cn('text-red-500', 'text-blue-500')).toBe('text-blue-500');
	});

	it('handles undefined and null', () => {
		expect(cn('btn', undefined, null)).toBe('btn');
	});
});

describe('normalizeCheckoutUrl', () => {
	it('accepts absolute https urls', () => {
		expect(
			normalizeCheckoutUrl('https://checkout.example.com/session/abc', 'https://app.example.com')
		).toBe('https://checkout.example.com/session/abc');
	});

	it('resolves relative urls against base origin', () => {
		expect(normalizeCheckoutUrl('/billing/checkout/session/abc', 'https://app.example.com')).toBe(
			'https://app.example.com/billing/checkout/session/abc'
		);
	});

	it('rejects non-http(s) schemes', () => {
		expect(() => normalizeCheckoutUrl('javascript:alert(1)', 'https://app.example.com')).toThrow(
			'Checkout URL must use http(s).'
		);
	});

	it('rejects empty values', () => {
		expect(() => normalizeCheckoutUrl('', 'https://app.example.com')).toThrow(
			'Checkout URL is missing or invalid.'
		);
	});
});
