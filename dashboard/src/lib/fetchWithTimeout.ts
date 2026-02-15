export class TimeoutError extends Error {
	constructor(timeoutMs: number) {
		super(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
		this.name = 'TimeoutError';
	}
}

export async function fetchWithTimeout(
	fetchFn: typeof fetch,
	input: RequestInfo | URL,
	init: RequestInit = {},
	timeoutMs = 10000
): Promise<Response> {
	const controller = new AbortController();
	let timedOut = false;
	let timeoutId: ReturnType<typeof setTimeout> | undefined;
	let cleanupAbortForwarding: (() => void) | undefined;

	// Merge caller-provided AbortSignal (if any) with our timeout AbortController.
	// AbortSignal.any is widely supported in modern runtimes, but we still provide a fallback.
	let signal: AbortSignal = controller.signal;
	if (init.signal) {
		const any = (AbortSignal as unknown as { any?: (signals: AbortSignal[]) => AbortSignal }).any;
		if (typeof any === 'function') {
			signal = any([init.signal, controller.signal]);
		} else {
			// Fallback: forward caller aborts into our controller (keeps behaviour correct, but loses reason).
			const onAbort = () => controller.abort();
			init.signal.addEventListener('abort', onAbort, { once: true });
			cleanupAbortForwarding = () => init.signal?.removeEventListener('abort', onAbort);
			if (init.signal.aborted) controller.abort();
			signal = controller.signal;
		}
	}

	try {
		timeoutId = setTimeout(() => {
			timedOut = true;
			controller.abort();
		}, timeoutMs);

		return await fetchFn(input, { ...init, signal });
	} catch (err) {
		if (timedOut) throw new TimeoutError(timeoutMs);
		throw err;
	} finally {
		if (timeoutId) clearTimeout(timeoutId);
		cleanupAbortForwarding?.();
	}
}
