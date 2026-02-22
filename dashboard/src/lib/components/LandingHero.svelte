<script lang="ts">
	import { assets, base } from '$app/paths';
	import { page } from '$app/stores';

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
	<meta itemprop="image" content={new URL(`${assets}/og-image.png`, $page.url.origin).toString()} />
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
						<a href="#features" class="btn btn-secondary text-base px-8 py-3"> Explore Features </a>
						<a href="#how" class="btn btn-ghost text-ink-200 underline text-base px-6 py-3">
							How It Works
						</a>
					</div>

					<div class="landing-proof fade-in-up" style="animation-delay: 420ms;">
						<div class="landing-proof-item">
							<p class="landing-proof-k text-ink-100">Policy-first remediation</p>
							<p class="landing-proof-v text-ink-200">
								Deterministic previews before you click approve.
							</p>
						</div>
						<div class="landing-proof-item">
							<p class="landing-proof-k text-ink-100">Audit-ready evidence</p>
							<p class="landing-proof-v text-ink-200">
								Event types, traces, and exports for reviews.
							</p>
						</div>
						<div class="landing-proof-item">
							<p class="landing-proof-k text-ink-100">Operator UX</p>
							<p class="landing-proof-v text-ink-200">
								Queues, jobs, and a command palette for speed.
							</p>
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

							<div class="sr-only">
								Signal map summary: Valdrix signals connect FinOps spend and anomaly detection,
								GreenOps carbon and Graviton opportunities, and ActiveOps policy-driven remediation.
								Current highlights show budget drift at minus twelve percent, carbon improvement at
								minus eight percent, and fourteen queued zombie remediation targets.
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
					Track spend by provider, detect anomalies, and keep a freshness signal so you know when to
					trust the numbers.
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
					Make carbon a first-class constraint alongside cost, and spotlight Graviton optimization.
				</p>
				<p class="landing-mini text-ink-300">GreenOps page included.</p>
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
				<p class="landing-mini text-ink-300">Designed for "runbook mode".</p>
			</div>

			<div class="glass-panel">
				<h3 class="landing-h3">Audit Logs</h3>
				<p class="landing-p">
					Event types, detail views, and CSV exports to support reviews and investigations.
				</p>
				<p class="landing-mini text-ink-300">Evidence-first workflow.</p>
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

	<section id="problem" class="container mx-auto px-6 pb-20">
		<div class="landing-section-head">
			<h2 class="landing-h2">30% of cloud spend is often unaccounted for</h2>
			<p class="landing-section-sub">
				Valdrix is built for the moment when a team knows spend is rising but cannot explain why,
				where, or what to do safely next.
			</p>
		</div>

		<div class="landing-problem-grid">
			<article class="glass-panel landing-problem-card">
				<p class="landing-proof-k">Signal gap</p>
				<p class="landing-stat-v">30-35%</p>
				<p class="landing-p">
					Idle or orphaned resources can hide inside normal usage trends and inflate cloud bills.
				</p>
			</article>
			<article class="glass-panel landing-problem-card">
				<p class="landing-proof-k">Decision lag</p>
				<p class="landing-stat-v">Days lost</p>
				<p class="landing-p">
					Teams spend cycles proving findings instead of executing controlled remediations.
				</p>
			</article>
			<article class="glass-panel landing-problem-card">
				<p class="landing-proof-k">Audit burden</p>
				<p class="landing-stat-v">Every review</p>
				<p class="landing-p">
					Without evidence-first workflows, changes become hard to justify to leadership and audit.
				</p>
			</article>
		</div>
	</section>

	<section id="ai" class="container mx-auto px-6 pb-20">
		<div class="landing-section-head">
			<h2 class="landing-h2">AI-powered analysis you can control</h2>
			<p class="landing-section-sub">
				Ask plain-English questions, get contextual recommendations, and keep provider choice in
				your hands.
			</p>
		</div>

		<div class="landing-ai-grid">
			<div class="glass-panel">
				<h3 class="landing-h3">From metrics to explanations</h3>
				<p class="landing-p">
					Ask: "Why did database spend jump this week?" and get summarized cause analysis with
					resource-level context.
				</p>
				<div class="landing-tag-row">
					<span class="badge badge-default">Root cause hints</span>
					<span class="badge badge-default">Action suggestions</span>
					<span class="badge badge-default">Policy-ready output</span>
				</div>
			</div>

			<div class="glass-panel">
				<h3 class="landing-h3">Model choice + BYOK</h3>
				<p class="landing-p">
					Support for OpenAI, Anthropic, Google, and Groq, with Bring Your Own Key options for teams
					that require provider-level control.
				</p>
				<div class="landing-tag-row">
					<span class="badge badge-accent">GPT-4o</span>
					<span class="badge badge-success">Claude</span>
					<span class="badge badge-warning">Gemini</span>
					<span class="badge badge-default">Groq</span>
					<span class="badge badge-default">BYOK</span>
				</div>
			</div>
		</div>
	</section>

	<section id="zero-cost" class="container mx-auto px-6 pb-20">
		<div class="glass-panel landing-cost-callout">
			<div>
				<p class="landing-proof-k">Architecture principle</p>
				<h2 class="landing-h2">Zero hidden API cost design</h2>
				<p class="landing-p">
					Valdrix prioritizes free describe-style cloud APIs and exported billing feeds so cost
					analysis does not introduce heavy metering side effects.
				</p>
			</div>
			<div class="landing-cost-grid">
				<div class="landing-cost-card">
					<p class="landing-cost-k">AWS</p>
					<p class="landing-cost-v">CUR + Describe APIs</p>
				</div>
				<div class="landing-cost-card">
					<p class="landing-cost-k">GCP</p>
					<p class="landing-cost-v">Export + inventory-first</p>
				</div>
				<div class="landing-cost-card">
					<p class="landing-cost-k">Azure</p>
					<p class="landing-cost-v">Cost management baseline</p>
				</div>
			</div>
		</div>
	</section>

	<section id="integrations" class="container mx-auto px-6 pb-20">
		<div class="landing-section-head">
			<h2 class="landing-h2">Works where your operators already work</h2>
			<p class="landing-section-sub">
				Communication, ticketing, CI/CD, and infrastructure workflows stay in the loop.
			</p>
		</div>

		<div class="landing-integration-grid">
			<div class="glass-panel landing-problem-card">
				<h3 class="landing-h3">Communication</h3>
				<p class="landing-p">Slack alerts, digests, and leaderboard snapshots.</p>
			</div>
			<div class="glass-panel landing-problem-card">
				<h3 class="landing-h3">Ticketing</h3>
				<p class="landing-p">Jira-aligned operational handoff for tracked follow-up.</p>
			</div>
			<div class="glass-panel landing-problem-card">
				<h3 class="landing-h3">CI/CD</h3>
				<p class="landing-p">GitHub Actions and GitLab workflows for controlled execution.</p>
			</div>
			<div class="glass-panel landing-problem-card">
				<h3 class="landing-h3">IaC</h3>
				<p class="landing-p">
					Terraform-oriented remediation plans for predictable change control.
				</p>
			</div>
			<div class="glass-panel landing-problem-card">
				<h3 class="landing-h3">Webhooks</h3>
				<p class="landing-p">Generic webhook dispatch with retry-aware delivery patterns.</p>
			</div>
		</div>
	</section>

	<section id="faq" class="container mx-auto px-6 pb-20">
		<div class="landing-section-head">
			<h2 class="landing-h2">Frequently asked questions</h2>
			<p class="landing-section-sub">Straight answers for cost, risk, and operational control.</p>
		</div>

		<div class="landing-faq-list">
			<details class="landing-faq-item glass-panel">
				<summary>Will Valdrix increase our cloud API spend?</summary>
				<p class="landing-p">
					The platform is designed around low-overhead cloud telemetry patterns and cost exports,
					avoiding heavy paid API fan-out patterns where possible.
				</p>
			</details>
			<details class="landing-faq-item glass-panel">
				<summary>Can we use our own LLM API key?</summary>
				<p class="landing-p">
					Yes. BYOK workflows are supported for teams that want provider-level control and audit
					alignment.
				</p>
			</details>
			<details class="landing-faq-item glass-panel">
				<summary>Does Valdrix auto-delete resources without review?</summary>
				<p class="landing-p">
					No. The workflow is preview-first and policy-gated, with explicit human approval before
					execution.
				</p>
			</details>
			<details class="landing-faq-item glass-panel">
				<summary>How is tenant data isolated?</summary>
				<p class="landing-p">
					Isolation relies on tenant-aware controls and audit logging patterns designed for
					multi-tenant safety.
				</p>
			</details>
		</div>
	</section>

	<section id="social" class="container mx-auto px-6 pb-20">
		<div class="glass-panel landing-social">
			<h2 class="landing-h2">Built by operators who lived this problem</h2>
			<blockquote class="landing-quote">
				"Cloud bills should not be a monthly fire drill. Teams need one surface that shows what to
				trust and what to do next."
			</blockquote>
			<div class="landing-author">
				<p class="landing-author-name">Dare AbdulGoniyy</p>
				<p class="landing-author-role">Creator, Valdrix</p>
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

<style>
	/* ===== Landing (2026) ===== */
	.landing {
		position: relative;
		isolation: isolate;
	}

	.landing-hero {
		position: relative;
		overflow: hidden;
	}

	/* Atmospheric mesh + dot grid */
	.landing-hero::before {
		content: '';
		position: absolute;
		inset: -260px -120px auto -120px;
		height: 640px;
		background:
			radial-gradient(520px 320px at 18% 18%, rgb(6 182 212 / 0.22), transparent 62%),
			radial-gradient(520px 360px at 58% 22%, rgb(34 211 238 / 0.18), transparent 65%),
			radial-gradient(520px 420px at 82% 38%, rgb(16 185 129 / 0.14), transparent 68%),
			radial-gradient(420px 360px at 70% 74%, rgb(245 158 11 / 0.1), transparent 70%);
		filter: blur(46px);
		opacity: 1;
		pointer-events: none;
		z-index: 0;
	}

	.landing-hero::after {
		content: '';
		position: absolute;
		inset: 0;
		background-image: radial-gradient(rgb(255 255 255 / 0.1) 1px, transparent 1px);
		background-size: 24px 24px;
		opacity: 0.1;
		pointer-events: none;
		z-index: 0;
	}

	.landing-hero :global(.container) {
		position: relative;
		z-index: 1;
	}

	.landing-hero-grid {
		display: grid;
		gap: 2.5rem;
		align-items: start;
	}

	@media (min-width: 1024px) {
		.landing-hero-grid {
			grid-template-columns: 1.15fr 0.85fr;
			gap: 3rem;
		}
	}

	.landing-copy {
		text-align: center;
	}

	@media (min-width: 1024px) {
		.landing-copy {
			text-align: left;
			padding-top: 0.75rem;
		}
	}

	.landing-kicker {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.55rem;
		flex-wrap: wrap;
	}

	@media (min-width: 1024px) {
		.landing-kicker {
			justify-content: flex-start;
		}
	}

	.landing-kicker-text {
		color: var(--color-ink-400);
		font-size: 0.9rem;
		font-weight: 500;
		letter-spacing: 0.01em;
	}

	.landing-sep {
		color: var(--color-ink-600);
	}

	.landing-title {
		font-family: ui-serif, 'Iowan Old Style', 'Palatino Linotype', Palatino, serif;
		font-weight: 800;
		letter-spacing: -0.04em;
		line-height: 1.02;
		font-size: clamp(2.6rem, 5vw, 4.4rem);
		margin-top: 0.9rem;
		margin-bottom: 1rem;
	}

	.landing-kinetic {
		display: inline-block;
		padding: 0 0.08em;
		background: linear-gradient(135deg, var(--color-accent-400), var(--color-success-400));
		background-size: 200% 200%;
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
		color: transparent;
		animation: kineticShift 6s var(--ease-in-out) infinite;
	}

	@keyframes kineticShift {
		0% {
			background-position: 0% 50%;
		}
		50% {
			background-position: 100% 50%;
		}
		100% {
			background-position: 0% 50%;
		}
	}

	.landing-subtitle {
		color: var(--color-ink-300);
		font-size: 1.125rem;
		line-height: 1.65;
		max-width: 42rem;
		margin: 0 auto;
	}

	@media (min-width: 1024px) {
		.landing-subtitle {
			margin-left: 0;
		}
	}

	.landing-cta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		justify-content: center;
		margin-top: 1.4rem;
	}

	@media (min-width: 1024px) {
		.landing-cta {
			justify-content: flex-start;
		}
	}

	.landing-proof {
		margin-top: 1.75rem;
		display: grid;
		gap: 0.85rem;
		grid-template-columns: 1fr;
	}

	@media (min-width: 768px) {
		.landing-proof {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-proof-item {
		border: 1px solid rgb(255 255 255 / 0.06);
		border-radius: var(--radius-lg);
		padding: 0.95rem 1rem;
		background: rgb(15 19 24 / 0.35);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
	}

	.landing-proof-k {
		margin: 0 0 0.25rem 0;
		font-size: 0.72rem;
		letter-spacing: 0.09em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-200);
	}

	.landing-proof-v {
		margin: 0;
		font-size: 0.875rem;
		color: var(--color-ink-400);
	}

	.landing-preview {
		max-width: 40rem;
		margin: 0 auto;
	}

	@media (min-width: 1024px) {
		.landing-preview {
			max-width: none;
			margin: 0;
		}
	}

	.landing-preview-card {
		padding: 1.1rem;
	}

	.landing-preview-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.85rem;
	}

	.landing-preview-title {
		display: flex;
		align-items: center;
		gap: 0.55rem;
		font-weight: 700;
		color: var(--color-ink-100);
	}

	.landing-preview-pill {
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.12em;
		font-weight: 800;
		padding: 0.25rem 0.55rem;
		border-radius: 9999px;
		color: var(--color-success-400);
		background: rgb(16 185 129 / 0.1);
		border: 1px solid rgb(16 185 129 / 0.22);
	}

	.landing-live-dot {
		width: 8px;
		height: 8px;
		border-radius: 9999px;
		background: var(--color-success-400);
		box-shadow: 0 0 0 6px rgb(16 185 129 / 0.12);
		animation: livePulse 1.8s var(--ease-in-out) infinite;
	}

	@keyframes livePulse {
		0%,
		100% {
			transform: scale(1);
			opacity: 0.95;
		}
		50% {
			transform: scale(1.4);
			opacity: 0.55;
		}
	}

	.signal-map {
		position: relative;
		border-radius: var(--radius-lg);
		overflow: hidden;
		border: 1px solid rgb(255 255 255 / 0.07);
		background:
			radial-gradient(
				120% 90% at 30% 20%,
				rgb(34 211 238 / 0.18) 0%,
				rgb(6 182 212 / 0.06) 38%,
				rgb(15 19 24 / 0.55) 70%
			),
			radial-gradient(90% 120% at 75% 70%, rgb(16 185 129 / 0.12) 0%, rgb(15 19 24 / 0) 62%);
		height: 300px;
	}

	.signal-map::after {
		content: '';
		position: absolute;
		inset: 0;
		background-image: radial-gradient(rgb(255 255 255 / 0.1) 1px, transparent 1px);
		background-size: 26px 26px;
		opacity: 0.12;
		pointer-events: none;
	}

	.signal-svg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}

	.sig-grid line {
		stroke: rgb(255 255 255 / 0.06);
		stroke-width: 1;
	}

	.sig-line {
		opacity: 0.85;
		animation: lineDash 7s linear infinite;
	}

	@keyframes lineDash {
		to {
			stroke-dashoffset: -220;
		}
	}

	.sig-node {
		fill: rgb(10 13 18 / 0.8);
		stroke: var(--color-accent-400);
		stroke-width: 2.2;
		filter: drop-shadow(0 0 10px rgb(34 211 238 / 0.2));
		transform-box: fill-box;
		transform-origin: center;
		animation: nodePulse 2.9s var(--ease-in-out) infinite;
	}

	.sig-node--center {
		fill: rgb(6 182 212 / 0.65);
		stroke: var(--color-accent-400);
		animation-duration: 3.8s;
	}

	.sig-node--a {
		stroke: var(--color-accent-400);
	}

	.sig-node--b {
		stroke: var(--color-success-400);
		filter: drop-shadow(0 0 10px rgb(16 185 129 / 0.22));
	}

	.sig-node--c {
		stroke: var(--color-warning-400);
		filter: drop-shadow(0 0 10px rgb(245 158 11 / 0.2));
	}

	@keyframes nodePulse {
		0%,
		100% {
			transform: scale(1);
		}
		50% {
			transform: scale(1.18);
		}
	}

	.signal-label {
		position: absolute;
		padding: 0.55rem 0.65rem;
		border-radius: 0.85rem;
		background: rgb(10 13 18 / 0.55);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
		border: 1px solid rgb(255 255 255 / 0.08);
		pointer-events: none;
	}

	.signal-label-k {
		margin: 0;
		font-size: 0.7rem;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-200);
	}

	.signal-label-v {
		margin: 0.15rem 0 0 0;
		font-size: 0.8rem;
		color: var(--color-ink-400);
	}

	.signal-label--center {
		left: 50%;
		top: 50%;
		transform: translate(-50%, -50%);
		text-align: center;
	}

	.signal-label--a {
		left: 22%;
		top: 28%;
		transform: translate(-10%, -100%);
	}

	.signal-label--b {
		left: 72%;
		top: 22%;
		transform: translate(-50%, -110%);
	}

	.signal-label--c {
		left: 78%;
		top: 72%;
		transform: translate(-20%, 10%);
	}

	.landing-metrics {
		margin-top: 0.9rem;
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.75rem;
	}

	@media (max-width: 420px) {
		.landing-metrics {
			grid-template-columns: 1fr;
		}
	}

	.landing-metric {
		padding: 0.85rem 0.9rem;
		border-radius: var(--radius-lg);
	}

	.landing-metric-k {
		margin: 0;
		font-size: 0.72rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-400);
	}

	.landing-metric-v {
		margin: 0.25rem 0 0 0;
		font-size: 1.4rem;
		font-weight: 800;
		line-height: 1.1;
	}

	.landing-metric-h {
		margin: 0.25rem 0 0 0;
		font-size: 0.8rem;
		color: var(--color-ink-500);
	}

	.landing-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem;
		margin-top: 1rem;
		justify-content: center;
	}

	@media (min-width: 1024px) {
		.landing-pills {
			justify-content: flex-end;
		}
	}

	.landing-section-head {
		max-width: 52rem;
		margin: 0 auto 1.25rem auto;
		text-align: center;
	}

	.landing-h2 {
		font-family: ui-serif, 'Iowan Old Style', 'Palatino Linotype', Palatino, serif;
		font-weight: 800;
		letter-spacing: -0.03em;
		line-height: 1.1;
		font-size: clamp(1.85rem, 3vw, 2.3rem);
		margin: 0;
	}

	.landing-section-sub {
		margin: 0.7rem auto 0 auto;
		color: var(--color-ink-400);
		font-size: 1.05rem;
		max-width: 46rem;
	}

	.landing-h3 {
		font-weight: 700;
		font-size: 1.1rem;
		margin: 0 0 0.55rem 0;
	}

	.landing-p {
		margin: 0;
		color: var(--color-ink-300);
		font-size: 0.95rem;
		line-height: 1.65;
	}

	.landing-mini {
		margin-top: 0.8rem;
		font-size: 0.85rem;
	}

	.landing-tag-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.55rem;
		margin-top: 0.95rem;
	}

	.landing-mini-grid {
		margin-top: 1rem;
		display: grid;
		gap: 0.65rem;
		grid-template-columns: 1fr;
	}

	.landing-mini-card {
		border: 1px solid rgb(255 255 255 / 0.06);
		border-radius: var(--radius-lg);
		padding: 0.75rem 0.85rem;
		background: rgb(15 19 24 / 0.25);
	}

	.landing-mini-k {
		margin: 0;
		font-size: 0.72rem;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		font-weight: 800;
		color: var(--color-ink-500);
	}

	.landing-mini-v {
		margin: 0.25rem 0 0 0;
		font-size: 0.9rem;
		color: var(--color-ink-300);
	}

	.landing-problem-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	@media (min-width: 768px) {
		.landing-problem-grid {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-problem-card {
		height: 100%;
	}

	.landing-stat-v {
		margin: 0 0 0.45rem 0;
		font-size: clamp(1.4rem, 2.2vw, 2rem);
		font-weight: 800;
		line-height: 1.1;
		color: var(--color-ink-100);
	}

	.landing-ai-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	@media (min-width: 1024px) {
		.landing-ai-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	.landing-cost-callout {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-5);
	}

	@media (min-width: 1024px) {
		.landing-cost-callout {
			grid-template-columns: 1.2fr 0.8fr;
			align-items: start;
		}
	}

	.landing-cost-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: 0.7rem;
	}

	.landing-cost-card {
		border: 1px solid rgb(255 255 255 / 0.08);
		border-radius: var(--radius-lg);
		padding: 0.85rem 0.95rem;
		background: rgb(15 19 24 / 0.35);
	}

	.landing-cost-k {
		margin: 0;
		font-size: 0.7rem;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--color-ink-500);
		font-weight: 800;
	}

	.landing-cost-v {
		margin: 0.3rem 0 0 0;
		font-size: 0.92rem;
		color: var(--color-ink-200);
	}

	.landing-integration-grid {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	@media (min-width: 768px) {
		.landing-integration-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}

	@media (min-width: 1200px) {
		.landing-integration-grid {
			grid-template-columns: repeat(5, minmax(0, 1fr));
		}
	}

	.landing-faq-list {
		display: grid;
		gap: var(--space-3);
	}

	.landing-faq-item summary {
		cursor: pointer;
		font-weight: 700;
		color: var(--color-ink-100);
		list-style: none;
	}

	.landing-faq-item summary::-webkit-details-marker {
		display: none;
	}

	.landing-faq-item summary::after {
		content: '+';
		float: right;
		color: var(--color-ink-400);
		font-weight: 700;
	}

	.landing-faq-item[open] summary::after {
		content: '-';
	}

	.landing-faq-item .landing-p {
		margin-top: 0.85rem;
	}

	.landing-social {
		text-align: center;
	}

	.landing-quote {
		margin: 1rem auto 0 auto;
		max-width: 52rem;
		font-size: 1.06rem;
		line-height: 1.7;
		color: var(--color-ink-200);
	}

	.landing-author {
		margin-top: 1rem;
	}

	.landing-author-name {
		margin: 0;
		font-weight: 700;
		color: var(--color-ink-100);
	}

	.landing-author-role {
		margin: 0.25rem 0 0 0;
		color: var(--color-ink-400);
		font-size: 0.9rem;
	}

	.landing-steps {
		display: grid;
		grid-template-columns: 1fr;
		gap: var(--space-4);
	}

	@media (min-width: 768px) {
		.landing-steps {
			grid-template-columns: repeat(3, minmax(0, 1fr));
		}
	}

	.landing-step {
		position: relative;
		overflow: hidden;
	}

	.landing-step::before {
		content: '';
		position: absolute;
		inset: 0 0 auto 0;
		height: 2px;
		background: linear-gradient(90deg, rgb(34 211 238 / 0.9), rgb(16 185 129 / 0.75));
		opacity: 0.75;
	}

	.landing-step-n {
		margin: 0 0 0.35rem 0;
		font-size: 0.75rem;
		letter-spacing: 0.16em;
		font-weight: 900;
		color: var(--color-ink-500);
		text-transform: uppercase;
	}

	.landing-final {
		display: flex;
		flex-direction: column;
		gap: 1.1rem;
		align-items: stretch;
		text-align: center;
	}

	@media (min-width: 768px) {
		.landing-final {
			flex-direction: row;
			align-items: center;
			justify-content: space-between;
			text-align: left;
		}
	}

	.landing-final-cta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		justify-content: center;
	}

	@media (min-width: 768px) {
		.landing-final-cta {
			justify-content: flex-end;
		}
	}
</style>
