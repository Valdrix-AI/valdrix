import fs from 'node:fs/promises';
import path from 'node:path';

const projectRoot = process.cwd();
const immutableDir = path.join(projectRoot, 'build', 'client', '_app', 'immutable');

const MAX_CHUNK_KB = Number(process.env.BUNDLE_MAX_CHUNK_KB ?? '350');
const MAX_TOTAL_KB = Number(process.env.BUNDLE_MAX_TOTAL_KB ?? '4000');

const MAX_CHUNK_BYTES = Math.max(1, MAX_CHUNK_KB) * 1024;
const MAX_TOTAL_BYTES = Math.max(1, MAX_TOTAL_KB) * 1024;

async function listFiles(dir) {
	const entries = await fs.readdir(dir, { withFileTypes: true });
	const files = [];
	for (const entry of entries) {
		const fullPath = path.join(dir, entry.name);
		if (entry.isDirectory()) {
			files.push(...(await listFiles(fullPath)));
			continue;
		}
		files.push(fullPath);
	}
	return files;
}

function formatKb(bytes) {
	return `${(bytes / 1024).toFixed(2)} KB`;
}

async function main() {
	try {
		await fs.access(immutableDir);
	} catch {
		console.error(
			`Bundle directory not found: ${immutableDir}\n` +
				`Run 'pnpm -C dashboard build' before checking bundle budgets.`
		);
		process.exit(2);
	}

	const allFiles = await listFiles(immutableDir);
	const jsFiles = allFiles
		.filter((file) => file.endsWith('.js'))
		.filter((file) => !file.endsWith('.map.js'));

	const sizes = await Promise.all(
		jsFiles.map(async (file) => {
			const stat = await fs.stat(file);
			return { file, bytes: stat.size };
		})
	);

	sizes.sort((a, b) => b.bytes - a.bytes);

	const total = sizes.reduce((sum, item) => sum + item.bytes, 0);
	const largest = sizes[0];

	const failures = [];
	if (largest && largest.bytes > MAX_CHUNK_BYTES) {
		failures.push(
			`Largest JS chunk exceeds budget: ${formatKb(largest.bytes)} > ${MAX_CHUNK_KB} KB\n` +
				`  ${path.relative(projectRoot, largest.file)}`
		);
	}

	if (total > MAX_TOTAL_BYTES) {
		failures.push(
			`Total client JS exceeds budget: ${formatKb(total)} > ${MAX_TOTAL_KB} KB\n` +
				`  (sum of all .js files under build/client/_app/immutable)`
		);
	}

	if (failures.length > 0) {
		console.error(failures.join('\n\n'));
		console.error('\nTop JS chunks:');
		for (const item of sizes.slice(0, 10)) {
			console.error(
				`- ${formatKb(item.bytes).padStart(10)}  ${path.relative(projectRoot, item.file)}`
			);
		}
		process.exit(1);
	}

	console.log(
		`Bundle budgets OK: largest=${largest ? formatKb(largest.bytes) : 'n/a'} (<= ${MAX_CHUNK_KB} KB), ` +
			`total=${formatKb(total)} (<= ${MAX_TOTAL_KB} KB)`
	);
}

await main();
