export type PricingPlan = {
	id: string;
	name: string;
	price_monthly: number;
	price_annual: number;
	period: string;
	description: string;
	features: string[];
	cta: string;
	popular: boolean;
};

export const DEFAULT_PRICING_PLANS: PricingPlan[] = [
	{
		id: 'starter',
		name: 'Starter',
		price_monthly: 29,
		price_annual: 290,
		period: '/mo',
		description: 'For small teams getting started with cloud cost visibility.',
		features: [
			'Single cloud provider (AWS)',
			'Cost dashboards + budget alerts',
			'BYOK supported (no additional platform surcharge)'
		],
		cta: 'Start with Starter',
		popular: false
	},
	{
		id: 'growth',
		name: 'Growth',
		price_monthly: 79,
		price_annual: 790,
		period: '/mo',
		description: 'For growing teams who need AI-powered cost intelligence.',
		features: [
			'Multi-cloud support',
			'AI analyses + GreenOps',
			'BYOK supported (no additional platform surcharge)'
		],
		cta: 'Start with Growth',
		popular: true
	},
	{
		id: 'pro',
		name: 'Pro',
		price_monthly: 199,
		price_annual: 1990,
		period: '/mo',
		description: 'For teams who want automated optimization and full API access.',
		features: [
			'Automated remediation',
			'Priority support + full API access',
			'BYOK supported (no additional platform surcharge)'
		],
		cta: 'Start with Pro',
		popular: false
	}
];
