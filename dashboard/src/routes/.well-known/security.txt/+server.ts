import type { RequestHandler } from './$types';

const SECURITY_TEXT = `Contact: mailto:security@valdrics.com
Contact: mailto:privacy@valdrics.com
Policy: https://valdrics.com/privacy
Canonical: https://valdrics.com/.well-known/security.txt
Expires: 2027-03-04T00:00:00.000Z
Preferred-Languages: en
`;

export const GET: RequestHandler = () => {
	return new Response(SECURITY_TEXT, {
		headers: {
			'Content-Type': 'text/plain; charset=utf-8',
			'Cache-Control': 'public, max-age=3600'
		}
	});
};
