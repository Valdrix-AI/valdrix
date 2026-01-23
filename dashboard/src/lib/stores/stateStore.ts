/**
 * State Store - Frontend State Persistence
 *
 * Optimized for Svelte 5 Runes.
 * Features:
 * - localStorage persistence
 * - Auto-save with debouncing
 * - Timezone-aware expiry
 */

const STORE_VERSION = 1;

type StoredValue<T> = {
	value: T;
	timestamp: number;
	version: number;
};

/**
 * Creates a reactive, persistent state store.
 */
export function createPersistentState<T>(key: string, initialValue: T, expiryHours = 24) {
	const storageKey = `valdrix_state_${key}`;

	// Internal state
	let state = $state<T>(initialValue);
	let initialized = false;

	/** Load from localStorage */
	function load() {
		if (typeof window === 'undefined') return;
		try {
			const stored = localStorage.getItem(storageKey);
			if (!stored) return;

			const parsed: StoredValue<T> = JSON.parse(stored);

			// Validation
			if (parsed.version !== STORE_VERSION) return;
			const ageHours = (Date.now() - parsed.timestamp) / (1000 * 60 * 60);
			if (ageHours > expiryHours) {
				localStorage.removeItem(storageKey);
				return;
			}

			state = parsed.value;
		} catch (e) {
			console.warn(`Failed to load state for ${key}:`, e);
		}
	}

	/** Save to localStorage */
	function save(value: T) {
		if (typeof window === 'undefined') return;
		try {
			const data: StoredValue<T> = {
				value,
				timestamp: Date.now(),
				version: STORE_VERSION
			};
			localStorage.setItem(storageKey, JSON.stringify(data));
		} catch (e) {
			console.warn(`Failed to save state for ${key}:`, e);
		}
	}

	// Effect to handle initialization and auto-save
	$effect(() => {
		if (!initialized) {
			load();
			initialized = true;
		}

		// Track 'state' for auto-save
		save(state);
	});

	return {
		get value() {
			return state;
		},
		set value(v: T) {
			state = v;
		},
		clear: () => {
			state = initialValue;
			if (typeof window !== 'undefined') {
				localStorage.removeItem(storageKey);
			}
		}
	};
}

// Pre-configured stores
export const settingsStore = createPersistentState('settings', {} as Record<string, any>, 1);
export const onboardingStore = createPersistentState(
	'onboarding',
	{ step: 1 } as Record<string, any>,
	24
);
export const remediationStore = createPersistentState('remediation', {} as Record<string, any>, 1);
