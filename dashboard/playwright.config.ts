import { defineConfig } from '@playwright/test';

const isPublicOnly = process.env.PLAYWRIGHT_PUBLIC_ONLY === '1';

const webServer = [
	{
		command:
			'TESTING=true E2E_AUTH_SECRET=playwright E2E_ALLOW_PROD_PREVIEW=true pnpm run build && TESTING=true E2E_AUTH_SECRET=playwright E2E_ALLOW_PROD_PREVIEW=true pnpm run preview',
		port: 4173,
		reuseExistingServer: true
	}
];

if (!isPublicOnly) {
	webServer.push({
		command:
			'cd .. && DATABASE_URL="sqlite+aiosqlite:///:memory:" TESTING=true DEBUG=false SUPABASE_JWT_SECRET="test-jwt-secret-at-least-32-bytes-long" ENCRYPTION_KEY="32-byte-long-test-encryption-key" CSRF_SECRET_KEY="32-byte-long-test-csrf-secret-key" KDF_SALT="S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s=" uv run uvicorn app.main:app --host 127.0.0.1 --port 8000',
		port: 8000,
		reuseExistingServer: true
	});
}

export default defineConfig({
	use: {
		baseURL: process.env.DASHBOARD_URL || 'http://localhost:4173'
	},
	webServer,
	testDir: '.',
	testMatch: ['tests/e2e/**/*.{test,spec}.ts', 'e2e/**/*.{test,spec}.ts']
});
