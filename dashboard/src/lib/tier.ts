export type Tier = 'free_trial' | 'starter' | 'growth' | 'pro' | 'enterprise';

const TIER_ORDER: Tier[] = ['free_trial', 'starter', 'growth', 'pro', 'enterprise'];

export function normalizeTier(value: unknown): Tier {
	const normalized = String(value || '')
		.toLowerCase()
		.trim();
	if (normalized === 'starter') return 'starter';
	if (normalized === 'growth') return 'growth';
	if (normalized === 'pro') return 'pro';
	if (normalized === 'enterprise') return 'enterprise';
	return 'free_trial';
}

function tierRank(tier: Tier): number {
	const idx = TIER_ORDER.indexOf(tier);
	return idx >= 0 ? idx : 0;
}

export function tierAtLeast(current: unknown, required: Tier): boolean {
	return tierRank(normalizeTier(current)) >= tierRank(required);
}

export function tierIn(current: unknown, allowed: Tier[]): boolean {
	const currentTier = normalizeTier(current);
	return allowed.includes(currentTier);
}

export function formatTierLabel(tier: unknown): string {
	const normalized = normalizeTier(tier);
	if (normalized === 'free_trial') return 'Free Trial';
	if (normalized === 'starter') return 'Starter';
	if (normalized === 'growth') return 'Growth';
	if (normalized === 'pro') return 'Pro';
	if (normalized === 'enterprise') return 'Enterprise';
	return 'Free Trial';
}

