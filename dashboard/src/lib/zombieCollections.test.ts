import { describe, expect, it } from 'vitest';
import { countZombieFindings } from './zombieCollections';

describe('countZombieFindings', () => {
	it('counts only known zombie finding arrays', () => {
		const count = countZombieFindings({
			unattached_volumes: [{ resource_id: 'vol-1' }, { resource_id: 'vol-2' }],
			old_snapshots: [{ resource_id: 'snap-1' }],
			ai_analysis: {
				resources: [{ resource_id: 'ai-1' }, { resource_id: 'ai-2' }],
				general_recommendations: ['item-a', 'item-b']
			},
			// Simulates future backend additions that should not inflate zombie totals.
			experimental_tags: ['x', 'y', 'z']
		} as unknown as Parameters<typeof countZombieFindings>[0]);

		expect(count).toBe(3);
	});

	it('returns zero for nullish payloads', () => {
		expect(countZombieFindings(null)).toBe(0);
		expect(countZombieFindings(undefined)).toBe(0);
	});
});
