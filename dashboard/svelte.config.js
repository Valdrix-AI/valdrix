import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	// Consult https://svelte.dev/docs/kit/integrations
	// for more information about preprocessors
	preprocess: vitePreprocess(),

	kit: {
		// adapter-node is used for production Docker environments
		adapter: adapter(),
		csp: {
			directives: {
				'default-src': ['self'],
				'script-src': ['self', 'https://*.supabase.co'],
				'style-src': ['self', 'unsafe-inline'], // Tailwind needs this
				'img-src': ['self', 'data:', 'https://*.supabase.co'],
				'font-src': ['self', 'data:'],
				'connect-src': [
					'self',
					'https://*.supabase.co',
					'http://localhost:*',
					'https://*.valdrix.ai'
				],
				'object-src': ['none'],
				'base-uri': ['self'],
				'form-action': ['self'],
				'frame-ancestors': ['none']
			}
		}
	}
};

export default config;
