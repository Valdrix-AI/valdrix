import { defineConfig } from '@playwright/test';

export default defineConfig({
	use: {
		baseURL: process.env.DASHBOARD_URL || 'http://localhost:4173'
	},
	webServer: [
			{
				command:
					'TESTING=true E2E_AUTH_SECRET=playwright E2E_ALLOW_PROD_PREVIEW=true npm run build && TESTING=true E2E_AUTH_SECRET=playwright E2E_ALLOW_PROD_PREVIEW=true npm run preview',
				port: 4173,
				reuseExistingServer: true
			},
		{
			command:
				'cd .. && DATABASE_URL="sqlite+aiosqlite:///:memory:" TESTING=true SUPABASE_JWT_SECRET="test-jwt-secret-at-least-32-bytes-long" ENCRYPTION_KEY="32-byte-long-test-encryption-key" CSRF_SECRET_KEY="32-byte-long-test-csrf-secret-key" KDF_SALT="S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s=" uv run uvicorn app.main:app --host 127.0.0.1 --port 8000',
			port: 8000,
			reuseExistingServer: true
		}
	],
	testDir: '.',
	testMatch: ['tests/e2e/**/*.{test,spec}.ts', 'e2e/**/*.{test,spec}.ts']
});
