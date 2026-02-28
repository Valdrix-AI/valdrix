import { expect, test } from '@playwright/test';

async function prepareStableLanding(page: Parameters<typeof test>[0]['page']) {
	await page.addInitScript(() => {
		const originalSetInterval = window.setInterval.bind(window);
		window.setInterval = ((handler: TimerHandler, timeout?: number, ...args: unknown[]) => {
			if (typeof timeout === 'number' && timeout >= 1000) {
				return 0 as unknown as number;
			}
			return originalSetInterval(handler, timeout, ...args);
		}) as typeof window.setInterval;
	});

	await page.emulateMedia({ reducedMotion: 'reduce' });
	await page.goto('/');
	await page.waitForLoadState('networkidle');
	await page.waitForTimeout(300);
}

test.describe('Landing visual snapshots', () => {
	test.describe('Desktop', () => {
		test.use({ viewport: { width: 1440, height: 900 } });

		test('hero and core sections stay visually stable', async ({ page }) => {
			await prepareStableLanding(page);
			await expect(page.locator('.landing-hero')).toHaveScreenshot('landing-hero-desktop.png', {
				animations: 'disabled',
				caret: 'hide'
			});
			await expect(page.locator('#cloud-hook')).toHaveScreenshot('landing-hook-desktop.png', {
				animations: 'disabled',
				caret: 'hide'
			});
			await expect(page.locator('#trust')).toHaveScreenshot('landing-trust-desktop.png', {
				animations: 'disabled',
				caret: 'hide'
			});
		});
	});

	test.describe('Mobile', () => {
		test.use({ viewport: { width: 390, height: 844 } });

		test('hero and core sections stay visually stable', async ({ page }) => {
			await prepareStableLanding(page);
			await expect(page.locator('.landing-hero')).toHaveScreenshot('landing-hero-mobile.png', {
				animations: 'disabled',
				caret: 'hide'
			});
			await expect(page.locator('#cloud-hook')).toHaveScreenshot('landing-hook-mobile.png', {
				animations: 'disabled',
				caret: 'hide'
			});
			await expect(page.locator('#trust')).toHaveScreenshot('landing-trust-mobile.png', {
				animations: 'disabled',
				caret: 'hide'
			});
		});
	});
});
