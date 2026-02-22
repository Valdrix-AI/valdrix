import { expect, test } from '@playwright/test';

const BASE_URL = process.env.DASHBOARD_URL || 'http://localhost:4173';

async function assertPublicRoute(
	page: Parameters<typeof test>[0]['page'],
	path: string,
	heading: RegExp
) {
	await page.goto(`${BASE_URL}${path}`);
	await expect(page).toHaveURL(new RegExp(`${path.replace('/', '\\/')}(\\?.*)?$`));
	await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
}

test.describe('Public marketing smoke (desktop)', () => {
	test('covers landing, pricing, docs, api docs, and status navigation', async ({ page }) => {
		await page.goto(BASE_URL);

		await expect(
			page.getByRole('heading', { level: 1, name: /cloud cost intelligence/i })
		).toBeVisible();
		await expect(page.getByRole('contentinfo')).toBeVisible();

		const primaryCta = page.getByRole('link', { name: /get started free/i }).first();
		await expect(primaryCta).toHaveAttribute('href', '/auth/login');

		const footer = page.getByRole('contentinfo');
		await footer.getByRole('link', { name: /documentation/i }).click();
		await expect(page).toHaveURL(/\/docs$/);
		await expect(page.getByRole('heading', { level: 1, name: /documentation/i })).toBeVisible();

		await page.getByRole('link', { name: /open api docs/i }).click();
		await expect(page).toHaveURL(/\/docs\/api$/);
		await expect(page.getByRole('heading', { level: 1, name: /api reference/i })).toBeVisible();

		await page.getByRole('link', { name: /system status/i }).click();
		await expect(page).toHaveURL(/\/status$/);
		await expect(page.getByRole('heading', { level: 1, name: /system status/i })).toBeVisible();

		await page.goto(`${BASE_URL}/pricing`);
		await expect(
			page.getByRole('heading', { level: 1, name: /simple, transparent pricing/i })
		).toBeVisible();
		const switchButton = page.getByRole('switch', { name: /toggle billing cycle/i });
		await expect(switchButton).toHaveAttribute('aria-checked', 'false');
		await switchButton.click();
		await expect(switchButton).toHaveAttribute('aria-checked', 'true');
	});
});

test.describe('Public marketing smoke (mobile)', () => {
	test.use({ viewport: { width: 390, height: 844 } });

	test('key landing sections and docs pages remain usable', async ({ page }) => {
		await page.goto(BASE_URL);
		await expect(
			page.getByRole('heading', { level: 1, name: /cloud cost intelligence/i })
		).toBeVisible();
		await expect(page.locator('#problem')).toBeVisible();
		await expect(page.locator('#ai')).toBeVisible();
		await expect(page.locator('#integrations')).toBeVisible();
		await expect(page.locator('#faq')).toBeVisible();

		await assertPublicRoute(page, '/docs', /documentation/i);
		await assertPublicRoute(page, '/docs/api', /api reference/i);
		await assertPublicRoute(page, '/status', /system status/i);
	});
});
