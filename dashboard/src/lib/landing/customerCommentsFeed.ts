export type CustomerCommentStage = 'design_partner' | 'customer';

export interface CustomerCommentRecord {
	quote: string;
	attribution: string;
	stage: CustomerCommentStage;
}

const MAX_QUOTE_LENGTH = 360;
const MAX_ATTRIBUTION_LENGTH = 120;

const FALLBACK_CUSTOMER_COMMENTS: readonly CustomerCommentRecord[] = Object.freeze([
	{
		quote:
			'We stopped debating whose queue a cost issue belongs to. Ownership is now explicit in the workflow.',
		attribution: 'Design-partner workshop, Head of FinOps',
		stage: 'design_partner'
	},
	{
		quote:
			'The value is not another dashboard. It is moving from signal to controlled action without drama.',
		attribution: 'Design-partner workshop, VP Engineering',
		stage: 'design_partner'
	},
	{
		quote:
			'Leadership reviews got shorter because the economic story is consistent from platform to finance.',
		attribution: 'Design-partner workshop, CFO',
		stage: 'design_partner'
	}
]);

function normalizeText(value: unknown, maxLength: number): string {
	const text = typeof value === 'string' ? value.trim() : '';
	if (!text) return '';
	return text.slice(0, maxLength);
}

export function normalizeCustomerCommentsFeed(
	input: readonly Partial<CustomerCommentRecord>[] | unknown
): CustomerCommentRecord[] {
	if (!Array.isArray(input)) {
		return [...FALLBACK_CUSTOMER_COMMENTS];
	}
	const normalized = input
		.map((record): CustomerCommentRecord => {
			const stage: CustomerCommentStage =
				record.stage === 'customer' ? 'customer' : 'design_partner';
			return {
				quote: normalizeText(record.quote, MAX_QUOTE_LENGTH),
				attribution: normalizeText(record.attribution, MAX_ATTRIBUTION_LENGTH),
				stage
			};
		})
		.filter((record) => record.quote && record.attribution);
	return normalized.length > 0 ? normalized : [...FALLBACK_CUSTOMER_COMMENTS];
}

export function getPublicCustomerCommentsFeed(): CustomerCommentRecord[] {
	return [...FALLBACK_CUSTOMER_COMMENTS];
}
