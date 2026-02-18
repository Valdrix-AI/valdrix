<script lang="ts">
	import { assets, base } from '$app/paths';
	import { page } from '$app/stores';

	let { personaTitle = 'Cloud' } = $props<{ personaTitle?: string }>();

	const landingGridX = [...Array(13).keys()];
	const landingGridY = [...Array(9).keys()];
</script>

<div class="landing" itemscope itemtype="https://schema.org/SoftwareApplication">
	<meta itemprop="name" content="Valdrix" />
	<meta itemprop="operatingSystem" content="Web" />
	<meta itemprop="applicationCategory" content="BusinessApplication" />
	<meta
		itemprop="description"
		content="Valdrix unifies FinOps, GreenOps, and ActiveOps into a single cloud intelligence surface with policy-driven remediation and audit-ready evidence."
	/>
	<meta itemprop="url" content={new URL($page.url.pathname, $page.url.origin).toString()} />
	<meta
		itemprop="image"
		content={new URL(`${assets}/valdrix_icon.png`, $page.url.origin).toString()}
	/>
	<section class="landing-hero">
		<div class="container mx-auto px-6 pt-10 pb-14">
			<div class="landing-hero-grid">
				<div class="landing-copy">
					<div class="landing-kicker fade-in-up" style="animation-delay: 0ms;">
						<span class="badge badge-default">2026 Beta</span>
						<span class="landing-sep" aria-hidden="true">•</span>
						<span class="landing-kicker-text">FinOps + GreenOps + ActiveOps</span>
					</div>

					<h1 class="landing-title fade-in-up" style="animation-delay: 120ms;">
						Cloud Cost Intelligence,
						<span class="landing-kinetic">operationalized</span>.
					</h1>

					<p class="landing-subtitle fade-in-up" style="animation-delay: 220ms;">
						Unify spend, carbon, and risk into a single signal map with policy-driven remediation
						and an audit trail you can export.
					</p>

					<div class="landing-cta fade-in-up" style="animation-delay: 320ms;">
						<a href={`${base}/auth/login`} class="btn btn-primary text-base px-8 py-3 pulse-glow">
							Get Started Free →
						</a>
						<a href="#features" class="btn btn-secondary text-base px-8 py-3">
							Explore Features
						</a>
						<a href="#how" class="btn btn-ghost text-base px-6 py-3"> How It Works </a>
					</div>

					<div class="landing-proof fade-in-up" style="animation-delay: 420ms;">
						<div class="landing-proof-item">
							<p class="landing-proof-k">Policy-first remediation</p>
							<p class="landing-proof-v">Deterministic previews before you click approve.</p>
						</div>
						<div class="landing-proof-item">
							<p class="landing-proof-k">Audit-ready evidence</p>
							<p class="landing-proof-v">Event types, traces, and exports for reviews.</p>
						</div>
						<div class="landing-proof-item">
							<p class="landing-proof-k">Operator UX</p>
							<p class="landing-proof-v">Queues, jobs, and a command palette for speed.</p>
						</div>
					</div>
				</div>

				<div class="landing-preview fade-in-up" style="animation-delay: 180ms;">
					<div class="glass-panel landing-preview-card">
						<div class="landing-preview-header">
							<div class="landing-preview-title">
								<span class="landing-live-dot" aria-hidden="true"></span>
								Realtime Signal Map
							</div>
							<span class="landing-preview-pill">Live</span>
						</div>

						<div
							class="signal-map"
							role="img"
							aria-label="Signal map preview: cost, carbon, and remediation"
						>
							<svg class="signal-svg" viewBox="0 0 640 420" aria-hidden="true">
								<defs>
									<linearGradient id="sigLine" x1="0" y1="0" x2="1" y2="1">
										<stop offset="0" stop-color="var(--color-accent-400)" stop-opacity="0.9" />
										<stop offset="1" stop-color="var(--color-success-400)" stop-opacity="0.7" />
									</linearGradient>
									<radialGradient id="sigGlow" cx="50%" cy="50%" r="60%">
										<stop offset="0" stop-color="var(--color-accent-400)" stop-opacity="0.35" />
										<stop offset="1" stop-color="var(--color-accent-400)" stop-opacity="0" />
									</radialGradient>
								</defs>

								<rect x="0" y="0" width="640" height="420" fill="rgba(0,0,0,0)" />
								<g class="sig-grid">
									{#each landingGridX as i (i)}
										<line x1={i * 54} y1="0" x2={i * 54} y2="420" />
									{/each}
									{#each landingGridY as i (i)}
										<line x1="0" y1={i * 52} x2="640" y2={i * 52} />
									{/each}
								</g>

								<circle cx="320" cy="210" r="150" fill="url(#sigGlow)" />

								<path
									class="sig-line"
									d="M 320 210 L 140 120 L 460 88 L 520 300"
									fill="none"
									stroke="url(#sigLine)"
									stroke-width="2"
									stroke-linecap="round"
									stroke-dasharray="6 10"
								/>

								<circle class="sig-node sig-node--center" cx="320" cy="210" r="10" />
								<circle class="sig-node sig-node--a" cx="140" cy="120" r="8" />
								<circle class="sig-node sig-node--b" cx="460" cy="88" r="8" />
								<circle class="sig-node sig-node--c" cx="520" cy="300" r="8" />
							</svg>

							<div class="signal-label signal-label--center">
								<p class="signal-label-k">Valdrix</p>
								<p class="signal-label-v">Signals</p>
							</div>
							<div class="signal-label signal-label--a">
								<p class="signal-label-k">FinOps</p>
								<p class="signal-label-v">Spend + anomalies</p>
							</div>
							<div class="signal-label signal-label--b">
								<p class="signal-label-k">GreenOps</p>
								<p class="signal-label-v">Carbon + Graviton</p>
							</div>
							<div class="signal-label signal-label--c">
								<p class="signal-label-k">ActiveOps</p>
								<p class="signal-label-v">Policy remediation</p>
							</div>
						</div>

						<div class="landing-metrics">
							<div class="landing-metric glass-card">
								<p class="landing-metric-k">Drift</p>
								<p class="landing-metric-v text-gradient">-12%</p>
								<p class="landing-metric-h">Budget trend</p>
							</div>
							<div class="landing-metric glass-card">
								<p class="landing-metric-k">Carbon</p>
								<p class="landing-metric-v text-success-400">-8%</p>
								<p class="landing-metric-h">Graviton wins</p>
							</div>
							<div class="landing-metric glass-card">
								<p class="landing-metric-k">Waste</p>
								<p class="landing-metric-v text-warning-400">14</p>
								<p class="landing-metric-h">Zombies queued</p>
							</div>
						</div>
					</div>

					<div class="landing-pills fade-in-up" style="animation-delay: 520ms;">
						<span class="badge badge-accent">💰 Cost signals</span>
						<span class="badge badge-success">🌱 Carbon intelligence</span>
						<span class="badge badge-warning">👻 Zombie remediation</span>
						<span class="badge badge-default">🧾 Audit evidence</span>
					</div>
				</div>
			</div>
		</div>
	</section>

	<section id="features" class="container mx-auto px-6 pb-20">
		<div class="landing-section-head">
			<h2 class="landing-h2">A bento of operational leverage</h2>
			<p class="landing-section-sub">
				Built for teams that want fewer dashboards, clearer decisions, and actions that leave an
				audit trail.
			</p>
		</div>

		<div class="bento-grid">
			<div class="glass-panel col-span-2">
				<h3 class="landing-h3">Cost signals that don't rot</h3>
				<p class="landing-p">
					Track spend by provider, detect anomalies, and keep a freshness signal so you know when
					to trust the numbers.
				</p>
				<div class="landing-tag-row">
					<span class="badge badge-accent">Allocation</span>
					<span class="badge badge-default">Unit economics</span>
					<span class="badge badge-default">Data quality</span>
				</div>
			</div>

			<div class="glass-panel">
				<h3 class="landing-h3">Carbon without the guilt trip</h3>
				<p class="landing-p">
					Make carbon a first-class constraint alongside cost, and spotlight Graviton
					optimization.
				</p>
				<p class="landing-mini text-ink-400">GreenOps page included.</p>
			</div>

			<div class="glass-panel row-span-2">
				<h3 class="landing-h3">Zombie detection with policy gates</h3>
				<p class="landing-p">
					Surface likely waste, preview the policy outcome, then queue approved actions for
					controlled execution.
				</p>
				<div class="landing-mini-grid">
					<div class="landing-mini-card">
						<p class="landing-mini-k">Preview</p>
						<p class="landing-mini-v">Allow / Warn / Block</p>
					</div>
					<div class="landing-mini-card">
						<p class="landing-mini-k">Queue</p>
						<p class="landing-mini-v">Approve then execute</p>
					</div>
				</div>
			</div>

			<div class="glass-panel">
				<h3 class="landing-h3">Ops Center</h3>
				<p class="landing-p">
					Jobs, queues, and strategy recommendations in a single operator surface.
				</p>
				<p class="landing-mini text-ink-400">Designed for "runbook mode".</p>
			</div>

			<div class="glass-panel">
				<h3 class="landing-h3">Audit Logs</h3>
				<p class="landing-p">
					Event types, detail views, and CSV exports to support reviews and investigations.
				</p>
				<p class="landing-mini text-ink-400">Evidence-first workflow.</p>
			</div>

			<div class="glass-panel col-span-2">
				<h3 class="landing-h3">Ship with calm guardrails</h3>
				<p class="landing-p">
					Privacy-safe UI defaults, CSRF hygiene, and a design system tuned for high-signal,
					low-noise operations.
				</p>
				<div class="landing-tag-row">
					<span class="badge badge-default">Least privilege</span>
					<span class="badge badge-default">Exportability</span>
					<span class="badge badge-default">Progressive disclosure</span>
				</div>
			</div>
		</div>
	</section>

	<section id="how" class="container mx-auto px-6 pb-20">
		<div class="landing-section-head">
			<h2 class="landing-h2">How it works</h2>
			<p class="landing-section-sub">Connect, observe, decide, then act with guardrails.</p>
		</div>

		<div class="landing-steps">
			<div class="glass-panel landing-step">
				<p class="landing-step-n">01</p>
				<h3 class="landing-h3">Connect accounts</h3>
				<p class="landing-p">
					Bring AWS, Azure, or GCP under one model and normalize the messy parts.
				</p>
			</div>
			<div class="glass-panel landing-step">
				<p class="landing-step-n">02</p>
				<h3 class="landing-h3">Generate signals</h3>
				<p class="landing-p">
					Costs, carbon, and waste analysis are turned into prioritizable findings.
				</p>
			</div>
			<div class="glass-panel landing-step">
				<p class="landing-step-n">03</p>
				<h3 class="landing-h3">Remediate safely</h3>
				<p class="landing-p">
					Policy previews, approval queues, and audit logs keep actions accountable.
				</p>
			</div>
		</div>
	</section>

	<section class="container mx-auto px-6 pb-24">
		<div class="landing-final glass-panel">
			<div>
				<h2 class="landing-h2">Turn cloud waste into a controlled operation</h2>
				<p class="landing-section-sub">
					Start free. You can stay in observation mode, or graduate to policy-driven remediation
					when you're ready.
				</p>
			</div>
			<div class="landing-final-cta">
				<a href={`${base}/auth/login`} class="btn btn-primary text-base px-8 py-3 pulse-glow">
					Get Started Free →
				</a>
				<a href="#features" class="btn btn-secondary text-base px-8 py-3"> Review Features </a>
			</div>
		</div>
	</section>
</div>
