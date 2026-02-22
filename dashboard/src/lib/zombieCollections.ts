export const ZOMBIE_COLLECTION_KEYS = [
	'unattached_volumes',
	'old_snapshots',
	'unused_elastic_ips',
	'idle_instances',
	'orphan_load_balancers',
	'idle_rds_databases',
	'underused_nat_gateways',
	'idle_s3_buckets',
	'stale_ecr_images',
	'idle_sagemaker_endpoints',
	'cold_redshift_clusters'
] as const;

export type ZombieCollectionKey = (typeof ZOMBIE_COLLECTION_KEYS)[number];

export type ZombieCollections<TFinding = Record<string, unknown>> = Partial<
	Record<ZombieCollectionKey, TFinding[]>
> & {
	total_monthly_waste?: number;
	ai_analysis?: {
		resources?: TFinding[];
		[key: string]: unknown;
	} | null;
};

export function countZombieFindings<TFinding>(
	zombies: ZombieCollections<TFinding> | null | undefined
): number {
	if (!zombies || typeof zombies !== 'object') return 0;
	return ZOMBIE_COLLECTION_KEYS.reduce((count, key) => {
		const findings = zombies[key];
		return count + (Array.isArray(findings) ? findings.length : 0);
	}, 0);
}
