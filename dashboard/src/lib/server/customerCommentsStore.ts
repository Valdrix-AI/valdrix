import { env } from '$env/dynamic/private';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import {
	getPublicCustomerCommentsFeed,
	normalizeCustomerCommentsFeed,
	type CustomerCommentRecord,
	type CustomerCommentStage
} from '$lib/landing/customerCommentsFeed';

type CustomerCommentsStoreFile = {
	version: 1;
	updated_at: string;
	items: CustomerCommentRecord[];
};

const MAX_PERSISTED_CUSTOMER_COMMENTS = 24;
const DEFAULT_STORE_RELATIVE_PATH = '.valdrics/customer-comments.store.json';
let writeLock: Promise<void> = Promise.resolve();

function resolveStorePath(): string {
	const configuredPath = String(
		env.CUSTOMER_COMMENTS_STORE_PATH || process.env.CUSTOMER_COMMENTS_STORE_PATH || ''
	).trim();
	if (configuredPath) {
		return configuredPath;
	}
	return path.join(process.cwd(), DEFAULT_STORE_RELATIVE_PATH);
}

function normalizeSingleComment(input: unknown): CustomerCommentRecord | null {
	if (!input || typeof input !== 'object') return null;
	const candidate = input as Record<string, unknown>;
	const quote = String(candidate.quote ?? '')
		.trim()
		.slice(0, 360);
	const attribution = String(candidate.attribution ?? '')
		.trim()
		.slice(0, 120);
	const stage = candidate.stage === 'customer' ? 'customer' : 'design_partner';
	if (!quote || !attribution) return null;
	return { quote, attribution, stage };
}

function dedupeComments(items: readonly CustomerCommentRecord[]): CustomerCommentRecord[] {
	const seen = new Set<string>();
	const deduped: CustomerCommentRecord[] = [];
	for (const item of items) {
		const key = `${item.quote.toLowerCase()}::${item.attribution.toLowerCase()}`;
		if (seen.has(key)) continue;
		seen.add(key);
		deduped.push(item);
	}
	return deduped;
}

async function readStoreFile(): Promise<CustomerCommentRecord[] | null> {
	try {
		const raw = await readFile(resolveStorePath(), 'utf8');
		const parsed = JSON.parse(raw) as Partial<CustomerCommentsStoreFile> | unknown;
		if (!parsed || typeof parsed !== 'object') return null;
		const items = Array.isArray((parsed as { items?: unknown }).items)
			? (parsed as { items: unknown[] }).items
					.map((entry) => normalizeSingleComment(entry))
					.filter((entry): entry is CustomerCommentRecord => !!entry)
			: [];
		if (!items.length) return null;
		return normalizeCustomerCommentsFeed(items);
	} catch (error) {
		const maybeCode = (error as { code?: string } | undefined)?.code;
		if (maybeCode === 'ENOENT') {
			return null;
		}
		return null;
	}
}

async function writeStoreFile(items: readonly CustomerCommentRecord[]): Promise<void> {
	const destination = resolveStorePath();
	const payload: CustomerCommentsStoreFile = {
		version: 1,
		updated_at: new Date().toISOString(),
		items: items.slice(0, MAX_PERSISTED_CUSTOMER_COMMENTS)
	};
	await mkdir(path.dirname(destination), { recursive: true });
	const tempPath = `${destination}.${process.pid}.${Date.now()}.tmp`;
	await writeFile(tempPath, JSON.stringify(payload, null, 2), 'utf8');
	await rename(tempPath, destination);
}

function withWriteLock<T>(operation: () => Promise<T>): Promise<T> {
	const run = writeLock.then(operation, operation);
	writeLock = run.then(
		() => undefined,
		() => undefined
	);
	return run;
}

export async function listCustomerComments(): Promise<CustomerCommentRecord[]> {
	const stored = await readStoreFile();
	if (stored && stored.length) {
		return stored;
	}
	return getPublicCustomerCommentsFeed();
}

export async function appendCustomerComment(input: {
	quote: string;
	attribution: string;
	stage?: CustomerCommentStage;
}): Promise<CustomerCommentRecord[]> {
	const comment = normalizeSingleComment(input);
	if (!comment) {
		throw new Error('invalid_comment');
	}
	return withWriteLock(async () => {
		const current = await listCustomerComments();
		const next = dedupeComments([comment, ...current]).slice(0, MAX_PERSISTED_CUSTOMER_COMMENTS);
		await writeStoreFile(next);
		return next;
	});
}
