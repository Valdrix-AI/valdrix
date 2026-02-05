import { defineConfig } from '@playwright/test';

export default defineConfig({
	webServer: [
		{ command: 'npm run build && npm run preview', port: 4173, reuseExistingServer: true },
		{ 
			command: 'cd .. && source .venv/bin/activate && export DATABASE_URL="sqlite+aiosqlite:///:memory:" && export TESTING=true && export SUPABASE_JWT_SECRET="test-jwt-secret-at-least-32-bytes-long" && export ENCRYPTION_KEY="32-byte-long-test-encryption-key" && export CSRF_SECRET_KEY="32-byte-long-test-csrf-secret-key" && export KDF_SALT="S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s=" && python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000', 
			port: 8000,
			reuseExistingServer: true
		}
	],
	testDir: '.',
	testMatch: ['tests/e2e/**/*.{test,spec}.ts', 'e2e/**/*.{test,spec}.ts']
});
