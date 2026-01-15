/**
 * Valdrix Resilient API Client
 * 
 * Provides a wrapper around the native fetch API to:
 * 1. Automatically handle 429 (Rate Limit) errors via uiState
 * 2. Standardize error handling for 500s
 * 3. Future-proof for multi-cloud adapters
 */

import { uiState } from './stores/ui.svelte';

export async function resilientFetch(url: string | URL, options: RequestInit = {}): Promise<Response> {
    try {
        const response = await fetch(url, options);

        if (response.status === 429) {
            uiState.showRateLimitWarning();
        }

        if (!response.ok && response.status >= 500) {
            console.error(`[API Error] ${response.status} at ${url}`);
            // We can add a generic error toast here if needed
        }

        return response;
    } catch (error) {
        console.error(`[Network Error] at ${url}`, error);
        throw error;
    }
}
export const api = {
    get: (url: string, options: RequestInit = {}) => resilientFetch(url, { ...options, method: 'GET' }),
    post: (url: string, body: any, options: RequestInit = {}) => resilientFetch(url, { 
        ...options, 
        method: 'POST', 
        body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json', ...options.headers }
    }),
    put: (url: string, body: any, options: RequestInit = {}) => resilientFetch(url, { 
        ...options, 
        method: 'PUT', 
        body: JSON.stringify(body),
        headers: { 'Content-Type': 'application/json', ...options.headers }
    }),
    delete: (url: string, options: RequestInit = {}) => resilientFetch(url, { ...options, method: 'DELETE' }),
};
