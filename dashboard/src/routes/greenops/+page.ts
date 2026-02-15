import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, parent, url }) => {
	await parent();
	const selectedRegion = url.searchParams.get('region') || 'us-east-1';
	void fetch; // keep signature stable while moving data hydration client-side
	return { selectedRegion };
};
