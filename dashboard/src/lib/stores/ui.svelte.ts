/**
 * UI State Store (Svelte 5 Runes)
 *
 * Manages global UI states like toasts, loading indicators, and rate-limit warnings.
 */

export type ToastType = 'info' | 'success' | 'warning' | 'error' | 'rate-limit';

export interface Toast {
	id: string;
	message: string;
	type: ToastType;
	duration?: number;
}

class UIState {
	toasts = $state<Toast[]>([]);
	isSidebarOpen = $state(true);

	addToast(message: string, type: ToastType = 'info', duration = 5000) {
		const id = Math.random().toString(36).substring(2, 9);
		const toast: Toast = { id, message, type, duration };
		this.toasts = [...this.toasts, toast];

		if (duration > 0) {
			setTimeout(() => {
				this.removeToast(id);
			}, duration);
		}
		return id;
	}

	removeToast(id: string) {
		this.toasts = this.toasts.filter((t) => t.id !== id);
	}

	toggleSidebar() {
		this.isSidebarOpen = !this.isSidebarOpen;
	}

	/**
	 * Special handler for 429 Rate Limit errors.
	 * Prevents toast-storming by checking if a rate-limit toast already exists.
	 */
	showRateLimitWarning() {
		const existing = this.toasts.find((t) => t.type === 'rate-limit');
		if (!existing) {
			this.addToast(
				'System busy (Rate limit reached). Please wait a moment before trying again.',
				'rate-limit',
				8000
			);
		}
	}
}

export const uiState = new UIState();
