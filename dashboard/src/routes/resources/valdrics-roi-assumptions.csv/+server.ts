import type { RequestHandler } from './$types';

const ROI_TEMPLATE = [
	'variable,description,example_value',
	'monthly_spend_usd,Total cloud + software monthly spend,120000',
	'expected_reduction_pct,Controllable waste reduction target (%),12',
	'rollout_days,Days from kickoff to first governed action loop,30',
	'team_members,People participating in rollout,2',
	'blended_hourly_usd,Average blended hourly cost,145',
	'platform_annual_cost_usd,Projected annual platform cost,9600'
].join('\n');

export const GET: RequestHandler = () => {
	return new Response(ROI_TEMPLATE, {
		headers: {
			'Content-Type': 'text/csv; charset=utf-8',
			'Content-Disposition': 'attachment; filename="valdrics-roi-assumptions.csv"',
			'Cache-Control': 'public, max-age=3600'
		}
	});
};
