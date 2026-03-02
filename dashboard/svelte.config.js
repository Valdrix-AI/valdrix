import adapter from '@sveltejs/adapter-cloudflare';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

const isDev = process.env.NODE_ENV !== 'production';
const connectSrc = [
	'self',
	'https://*.supabase.co',
	'https://*.valdrics.ai',
	'https://challenges.cloudflare.com'
];

if (isDev) {
	connectSrc.push('http://localhost:*');
}

/** @type {import('@sveltejs/kit').Config} */
const config = {
	// Consult https://svelte.dev/docs/kit/integrations
	// for more information about preprocessors
	preprocess: vitePreprocess(),

	kit: {
		// Cloudflare Pages/Workers runtime adapter
		adapter: adapter(),
		csp: {
			directives: {
				'default-src': ['self'],
				'script-src': ['self', 'https://*.supabase.co', 'https://challenges.cloudflare.com'],
				'style-src': ['self', 'unsafe-inline'], // Tailwind needs this
				'img-src': ['self', 'data:', 'https://*.supabase.co'],
				'font-src': ['self', 'data:'],
				'connect-src': connectSrc,
				'frame-src': ['self', 'https://challenges.cloudflare.com'],
				'object-src': ['none'],
				'base-uri': ['self'],
				'form-action': ['self'],
				'frame-ancestors': ['none']
			}
		}
	}
};

export default config;
