import { describe, expect, it } from 'vitest';
import { getFocusableElements, lockBodyScroll, resolveNextFocusTarget } from './publicMenuA11y';

describe('publicMenuA11y', () => {
	it('collects focusable elements while ignoring hidden nodes', () => {
		const host = document.createElement('div');
		host.innerHTML = `
			<a id="a" href="/x">A</a>
			<button id="b" type="button">B</button>
			<button id="c" type="button" style="display:none">C</button>
			<input id="d" type="text" />
			<div id="e" tabindex="-1"></div>
		`;

		const focusables = getFocusableElements(host);
		expect(focusables.map((node) => node.id)).toEqual(['a', 'b', 'd']);
	});

	it('cycles focus forward and backward with wraparound', () => {
		const host = document.createElement('div');
		host.innerHTML = `
			<button id="first" type="button">First</button>
			<button id="middle" type="button">Middle</button>
			<button id="last" type="button">Last</button>
		`;

		const first = host.querySelector<HTMLElement>('#first');
		const middle = host.querySelector<HTMLElement>('#middle');
		const last = host.querySelector<HTMLElement>('#last');
		expect(first).toBeTruthy();
		expect(middle).toBeTruthy();
		expect(last).toBeTruthy();

		expect(resolveNextFocusTarget(host, first ?? null, 'forward')?.id).toBe('middle');
		expect(resolveNextFocusTarget(host, last ?? null, 'forward')?.id).toBe('first');
		expect(resolveNextFocusTarget(host, first ?? null, 'backward')?.id).toBe('last');
		expect(resolveNextFocusTarget(host, null, 'forward')?.id).toBe('first');
		expect(resolveNextFocusTarget(host, null, 'backward')?.id).toBe('first');
	});

	it('locks and restores body scroll styles deterministically', () => {
		document.body.style.overflow = 'auto';
		document.body.style.touchAction = 'pan-y';
		const restore = lockBodyScroll(document);

		expect(document.body.style.overflow).toBe('hidden');
		expect(document.body.style.touchAction).toBe('none');

		restore();
		expect(document.body.style.overflow).toBe('auto');
		expect(document.body.style.touchAction).toBe('pan-y');
	});
});
