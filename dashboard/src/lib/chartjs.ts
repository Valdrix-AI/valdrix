import type * as ChartJs from 'chart.js';

let chartJsPromise: Promise<typeof ChartJs> | null = null;
let registered = false;

/**
 * Lazy-load Chart.js and register built-in chart types/plugins once.
 *
 * This keeps Chart.js out of the initial route bundle and improves Core Web Vitals
 * on pages where charts are not immediately needed.
 */
export async function loadChartJs(): Promise<typeof ChartJs> {
	if (!chartJsPromise) {
		chartJsPromise = import('chart.js');
	}

	const mod = await chartJsPromise;
	if (!registered) {
		mod.Chart.register(...mod.registerables);
		registered = true;
	}
	return mod;
}
