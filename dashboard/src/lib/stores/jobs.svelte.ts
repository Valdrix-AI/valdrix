import { PUBLIC_API_URL } from '$env/static/public';
import { uiState } from './ui.svelte';
import { createSupabaseBrowserClient } from '../supabase';

export interface JobUpdate {
	id: string;
	job_type: string;
	status: string;
	updated_at: string;
	error_message?: string;
}

class JobStore {
	#jobs = $state<Record<string, JobUpdate>>({});
	#eventSource = $state<EventSource | null>(null);
	#isConnected = $state(false);

	get jobs() {
		return Object.values(this.#jobs).sort(
			(a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime()
		);
	}

	get isConnected() {
		return this.#isConnected;
	}

	get activeJobsCount() {
		return this.jobs.filter((j) => j.status === 'pending' || j.status === 'running').length;
	}

	async init() {
		if (this.#eventSource) return;

		const supabase = createSupabaseBrowserClient();
		const {
			data: { session }
		} = await supabase.auth.getSession();

		if (!session) return;

		const url = new URL(`${PUBLIC_API_URL}/jobs/stream`);
		// Since SSE doesn't support Authorization headers easily without polyfills,
		// we rely on the session cookie if available, or we could pass tokens in query params
		// (though cookies are preferred for security if the API is same-origin/configured).
		// For this implementation, we'll try standard EventSource which sends cookies.

		this.#eventSource = new EventSource(url, { withCredentials: true });

		this.#eventSource.onopen = () => {
			this.#isConnected = true;
		};

		this.#eventSource.addEventListener('job_update', (event) => {
			const updates = JSON.parse(event.data) as JobUpdate[];
			updates.forEach((update) => {
				this.#jobs[update.id] = update;

				// Optional: Show toast for important state changes
				if (update.status === 'completed') {
					uiState.addToast(`Job ${update.job_type} completed successfully`, 'success');
				} else if (update.status === 'failed') {
					uiState.addToast(
						`Job ${update.job_type} failed: ${update.error_message}`,
						'error',
						10000
					);
				}
			});
		});

		this.#eventSource.onerror = (error) => {
			this.#isConnected = false;
			this.#eventSource?.close();
			this.#eventSource = null;

			// Retry after delay
			setTimeout(() => this.init(), 5000);
		};
	}

	disconnect() {
		this.#eventSource?.close();
		this.#eventSource = null;
		this.#isConnected = false;
	}
}

export const jobStore = new JobStore();
