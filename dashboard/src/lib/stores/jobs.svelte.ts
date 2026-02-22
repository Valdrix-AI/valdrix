import { uiState } from './ui.svelte';
import { createSupabaseBrowserClient } from '../supabase';
import { edgeApiPath } from '../edgeProxy';

const INITIAL_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 60000;
const MAX_RECONNECT_EXPONENT = 6;
const MAX_RECONNECT_JITTER_MS = 500;
const JOB_STREAM_EDGE_PATH = edgeApiPath('/jobs/stream');

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
	#reconnectTimer = $state<ReturnType<typeof setTimeout> | null>(null);
	#reconnectAttempts = $state(0);
	#shouldReconnect = $state(true);

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
		this.#shouldReconnect = true;
		if (this.#eventSource || this.#reconnectTimer) return;

		const supabase = createSupabaseBrowserClient();
		const {
			data: { session }
		} = await supabase.auth.getSession();

		if (!session?.access_token) return;

		// EventSource cannot send custom Authorization headers; always go through edge proxy.
		if (!JOB_STREAM_EDGE_PATH.startsWith('/api/edge')) {
			uiState.addToast('Live job updates are unavailable: invalid stream path.', 'error', 7000);
			return;
		}

		const url = new URL(JOB_STREAM_EDGE_PATH, window.location.origin);
		// Defense-in-depth: never allow token fallbacks via query string.
		url.searchParams.delete('access_token');
		url.searchParams.delete('sse_access_token');

		this.#eventSource = new EventSource(url.toString(), { withCredentials: true });

		this.#eventSource.onopen = () => {
			this.#isConnected = true;
			this.#reconnectAttempts = 0;
		};

		this.#eventSource.addEventListener('job_update', (event) => {
			try {
				const updates = JSON.parse((event as MessageEvent<string>).data) as JobUpdate[];
				updates.forEach((update) => {
					this.#jobs[update.id] = update;

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
			} catch {
				uiState.addToast('Unable to parse live job updates. Reconnecting...', 'warning', 7000);
			}
		});

		this.#eventSource.onerror = () => {
			this.#isConnected = false;
			this.#eventSource?.close();
			this.#eventSource = null;
			this.#scheduleReconnect();
		};
	}

	#scheduleReconnect() {
		if (!this.#shouldReconnect || this.#reconnectTimer) return;
		const exponent = Math.min(this.#reconnectAttempts, MAX_RECONNECT_EXPONENT);
		const delay = Math.min(INITIAL_RECONNECT_DELAY_MS * 2 ** exponent, MAX_RECONNECT_DELAY_MS);
		const jitter = Math.floor(Math.random() * MAX_RECONNECT_JITTER_MS);
		this.#reconnectAttempts += 1;
		this.#reconnectTimer = setTimeout(() => {
			this.#reconnectTimer = null;
			void this.init();
		}, delay + jitter);
	}

	disconnect() {
		this.#shouldReconnect = false;
		if (this.#reconnectTimer) {
			clearTimeout(this.#reconnectTimer);
			this.#reconnectTimer = null;
		}
		this.#eventSource?.close();
		this.#eventSource = null;
		this.#isConnected = false;
		this.#reconnectAttempts = 0;
	}
}

export const jobStore = new JobStore();
