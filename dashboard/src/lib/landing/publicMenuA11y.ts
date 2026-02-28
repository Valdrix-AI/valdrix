const FOCUSABLE_SELECTOR =
	'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function isHidden(element: HTMLElement): boolean {
	if (element.hidden) return true;
	const style = element.style;
	return style.display === 'none' || style.visibility === 'hidden';
}

export function getFocusableElements(container: HTMLElement | null): HTMLElement[] {
	if (!container) return [];
	const elements = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
	return elements.filter((element) => {
		if (isHidden(element)) return false;
		if (element.getAttribute('aria-hidden') === 'true') return false;
		return true;
	});
}

export type FocusDirection = 'forward' | 'backward';

export function resolveNextFocusTarget(
	container: HTMLElement | null,
	activeElement: HTMLElement | null,
	direction: FocusDirection
): HTMLElement | null {
	const focusables = getFocusableElements(container);
	if (focusables.length === 0) return null;
	if (!activeElement) return focusables[0] ?? null;

	const currentIndex = focusables.indexOf(activeElement);
	if (currentIndex < 0) {
		return direction === 'forward'
			? (focusables[0] ?? null)
			: (focusables[focusables.length - 1] ?? null);
	}

	const delta = direction === 'forward' ? 1 : -1;
	const nextIndex = (currentIndex + delta + focusables.length) % focusables.length;
	return focusables[nextIndex] ?? null;
}

export function lockBodyScroll(doc: Document): () => void {
	const previousOverflow = doc.body.style.overflow;
	const previousTouchAction = doc.body.style.touchAction;
	doc.body.style.overflow = 'hidden';
	doc.body.style.touchAction = 'none';
	return () => {
		doc.body.style.overflow = previousOverflow;
		doc.body.style.touchAction = previousTouchAction;
	};
}
