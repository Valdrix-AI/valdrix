import type { PageLoad } from './$types';

const VALID_PERIODS = new Set(['7d', '30d', '90d', 'all']);

export const load: PageLoad = async ({ parent, url }) => {
	await parent();
	const requestedPeriod = url.searchParams.get('period') || '30d';
	const period = VALID_PERIODS.has(requestedPeriod) ? requestedPeriod : '30d';
	return { period };
};
