import { json } from '@sveltejs/kit';
import { listCustomerComments } from '$lib/server/customerCommentsStore';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async () => {
	const items = (await listCustomerComments()).map((record) => ({
		quote: record.quote,
		attribution: record.attribution,
		stage: record.stage
	}));
	return json(
		{
			items,
			meta: {
				total: items.length,
				hasLiveCustomerEvidence: items.some((item) => item.stage === 'customer')
			}
		},
		{
			headers: {
				'cache-control': 'public, max-age=15, stale-while-revalidate=60'
			}
		}
	);
};
