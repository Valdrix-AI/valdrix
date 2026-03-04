import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { GET, POST } from './+server';
import { GET as PUBLIC_GET } from '../../marketing/customer-comments/+server';

const ORIGINAL_STORE_PATH = process.env.CUSTOMER_COMMENTS_STORE_PATH;
const ORIGINAL_ALLOWLIST = process.env.CUSTOMER_COMMENTS_ADMIN_EMAIL_ALLOWLIST;

let tempDir = '';

function buildRequest(body: unknown): Request {
	return new Request('https://example.com/api/admin/customer-comments', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	});
}

function authedLocals(email = 'admin@valdrics.test'): App.Locals {
	return {
		supabase: {} as App.Locals['supabase'],
		safeGetSession: async () => ({
			session: { access_token: 'token' } as unknown as Awaited<
				ReturnType<App.Locals['safeGetSession']>
			>['session'],
			user: { email } as unknown as Awaited<ReturnType<App.Locals['safeGetSession']>>['user']
		})
	};
}

function unauthLocals(): App.Locals {
	return {
		supabase: {} as App.Locals['supabase'],
		safeGetSession: async () => ({ session: null, user: null })
	};
}

beforeEach(async () => {
	tempDir = await mkdtemp(path.join(os.tmpdir(), 'valdrics-comments-admin-'));
	process.env.CUSTOMER_COMMENTS_STORE_PATH = path.join(tempDir, 'customer-comments.store.json');
	delete process.env.CUSTOMER_COMMENTS_ADMIN_EMAIL_ALLOWLIST;
});

afterEach(async () => {
	if (tempDir) {
		await rm(tempDir, { recursive: true, force: true });
	}
	if (ORIGINAL_STORE_PATH === undefined) {
		delete process.env.CUSTOMER_COMMENTS_STORE_PATH;
	} else {
		process.env.CUSTOMER_COMMENTS_STORE_PATH = ORIGINAL_STORE_PATH;
	}
	if (ORIGINAL_ALLOWLIST === undefined) {
		delete process.env.CUSTOMER_COMMENTS_ADMIN_EMAIL_ALLOWLIST;
	} else {
		process.env.CUSTOMER_COMMENTS_ADMIN_EMAIL_ALLOWLIST = ORIGINAL_ALLOWLIST;
	}
});

describe('admin customer comments route', () => {
	it('requires authentication for admin feed reads', async () => {
		const response = await GET({
			locals: unauthLocals()
		} as Parameters<typeof GET>[0]);
		expect(response.status).toBe(401);
	});

	it('enforces allowlisted admin emails', async () => {
		process.env.CUSTOMER_COMMENTS_ADMIN_EMAIL_ALLOWLIST = 'owner@valdrics.test';
		const response = await GET({
			locals: authedLocals('non-admin@valdrics.test')
		} as Parameters<typeof GET>[0]);
		expect(response.status).toBe(403);
	});

	it('accepts comment writes and updates public feed output', async () => {
		const postResponse = await POST({
			locals: authedLocals(),
			request: buildRequest({
				quote: 'We cut month-end firefighting by routing owners immediately.',
				attribution: 'Finance Systems Lead, Enterprise',
				stage: 'customer'
			})
		} as Parameters<typeof POST>[0]);
		expect(postResponse.status).toBe(201);
		const postPayload = (await postResponse.json()) as {
			ok: boolean;
			items: Array<{ quote: string; attribution: string; stage: string }>;
		};
		expect(postPayload.ok).toBe(true);
		expect(postPayload.items[0]?.stage).toBe('customer');
		expect(postPayload.items[0]?.quote).toContain('month-end firefighting');

		const adminGet = await GET({
			locals: authedLocals()
		} as Parameters<typeof GET>[0]);
		expect(adminGet.status).toBe(200);
		const adminPayload = (await adminGet.json()) as {
			ok: boolean;
			items: Array<{ quote: string; attribution: string; stage: string }>;
			meta: { total: number; hasLiveCustomerEvidence: boolean };
		};
		expect(adminPayload.ok).toBe(true);
		expect(adminPayload.meta.hasLiveCustomerEvidence).toBe(true);
		expect(adminPayload.meta.total).toBeGreaterThan(0);

		const publicGet = await PUBLIC_GET({} as Parameters<typeof PUBLIC_GET>[0]);
		expect(publicGet.status).toBe(200);
		const publicPayload = (await publicGet.json()) as {
			items: Array<{ quote: string; attribution: string; stage: string }>;
		};
		expect(publicPayload.items[0]?.quote).toContain('month-end firefighting');
	});

	it('rejects invalid payloads', async () => {
		const response = await POST({
			locals: authedLocals(),
			request: buildRequest({ quote: '', attribution: '' })
		} as Parameters<typeof POST>[0]);
		expect(response.status).toBe(400);
	});
});
