const LOCAL_HOSTNAMES = new Set(['localhost', '127.0.0.1', '::1']);

export function isLocalHostname(hostname: string): boolean {
	return LOCAL_HOSTNAMES.has(hostname.toLowerCase());
}

export function shouldUseSecureCookies(url: URL, nodeEnv: string): boolean {
	if (url.protocol === 'https:') return true;
	if (isLocalHostname(url.hostname)) return false;
	return nodeEnv === 'production';
}

export function canUseE2EAuthBypass(params: {
	testingMode: boolean;
	allowProdPreviewBypass: boolean;
	isDevBuild: boolean;
	hostname: string;
}): boolean {
	if (!params.testingMode) return false;
	if (params.isDevBuild) return true;
	if (!params.allowProdPreviewBypass) return false;
	return isLocalHostname(params.hostname);
}
