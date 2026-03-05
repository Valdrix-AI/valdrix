<script lang="ts">
	import { base } from '$app/paths';
	import CloudLogo from '$lib/components/CloudLogo.svelte';

	const enterpriseMailHref =
		'mailto:enterprise@valdrics.com?cc=sales@valdrics.com&subject=Valdrics%20Enterprise%20Evaluation&body=Organization%20name%3A%0AStakeholders%3A%0ACloud%2FSaaS%20scope%3A%0ATarget%20timeline%3A';

	const governancePillars = [
		{
			title: 'Control Architecture',
			detail:
				'Map policy intent to owner-routed remediation, approval gates, and deterministic evidence exports.'
		},
		{
			title: 'Security Posture',
			detail:
				'Validate SSO, SCIM, role boundaries, and audit trails against internal security review criteria.'
		},
		{
			title: 'Commercial Readiness',
			detail:
				'Align procurement, legal, and finance stakeholders around rollout scope, responsibilities, and support model.'
		},
		{
			title: 'Operational Reliability',
			detail:
				'Confirm observability, rollback readiness, and failure-mode controls before production governance cutover.'
		}
	] as const;
</script>

<svelte:head>
	<title>Enterprise Governance | Valdrics</title>
	<meta
		name="description"
		content="Evaluate Valdrics enterprise governance readiness for cloud and software spend control, including security review, procurement diligence, and rollout operating model."
	/>
</svelte:head>

<div class="enterprise-shell">
	<div class="enterprise-bg-glow enterprise-bg-glow-a" aria-hidden="true"></div>
	<div class="enterprise-bg-glow enterprise-bg-glow-b" aria-hidden="true"></div>
	<div class="enterprise-bg-grid" aria-hidden="true"></div>
	<div class="enterprise-bg-aurora" aria-hidden="true"></div>
	<div class="enterprise-signal-field" aria-hidden="true">
		<div class="enterprise-signal-core">
			<CloudLogo provider="valdrics" size={176} />
		</div>
		<span class="enterprise-signal-ring enterprise-signal-ring-a"></span>
		<span class="enterprise-signal-ring enterprise-signal-ring-b"></span>
		<span class="enterprise-signal-ring enterprise-signal-ring-c"></span>
		<span class="enterprise-signal-line enterprise-signal-line-a"></span>
		<span class="enterprise-signal-line enterprise-signal-line-b"></span>
		<span class="enterprise-signal-line enterprise-signal-line-c"></span>
		<span class="enterprise-signal-node enterprise-signal-node-a"></span>
		<span class="enterprise-signal-node enterprise-signal-node-b"></span>
		<span class="enterprise-signal-node enterprise-signal-node-c"></span>
		<span class="enterprise-signal-node enterprise-signal-node-d"></span>
		<span class="enterprise-signal-node enterprise-signal-node-e"></span>
	</div>
	<div class="enterprise-logo-orbit enterprise-logo-orbit-a" aria-hidden="true">
		<CloudLogo provider="valdrics" size={104} />
	</div>
	<div class="enterprise-logo-orbit enterprise-logo-orbit-b" aria-hidden="true">
		<CloudLogo provider="valdrics" size={92} />
	</div>
	<div class="enterprise-logo-orbit enterprise-logo-orbit-c" aria-hidden="true">
		<CloudLogo provider="valdrics" size={80} />
	</div>

	<section class="enterprise-hero glass-panel">
		<p class="enterprise-kicker">Enterprise Governance Lane</p>
		<h1>Control cloud and software economics with procurement-grade confidence</h1>
		<p class="enterprise-hero-sub">
			Valdrics supports two buying paths: rapid self-serve activation for Starter, Growth, and Pro,
			and a formal enterprise diligence lane for security, risk, procurement, and executive review.
		</p>
		<div class="enterprise-hero-cta">
			<a href={enterpriseMailHref} class="btn btn-primary pulse-glow">Request Enterprise Briefing</a>
			<a href={`${base}/talk-to-sales`} class="btn btn-secondary">Talk to Sales</a>
			<a href={`${base}/auth/login?intent=enterprise_preview`} class="btn btn-secondary"
				>Start Free Workspace</a
			>
		</div>
		<p class="enterprise-cta-note">Validation briefing is ungated. No login required.</p>
		<div class="enterprise-metric-grid" aria-label="Enterprise readiness highlights">
			<article class="enterprise-metric-card">
				<p class="enterprise-metric-k">Validation Scope</p>
				<p class="enterprise-metric-v">Security + Finance + Platform</p>
			</article>
			<article class="enterprise-metric-card">
				<p class="enterprise-metric-k">Operating Model</p>
				<p class="enterprise-metric-v">Owner-routed controls with approvals</p>
			</article>
			<article class="enterprise-metric-card">
				<p class="enterprise-metric-k">Evidence Surface</p>
				<p class="enterprise-metric-v">Audit-ready exports and control traces</p>
			</article>
		</div>
	</section>

	<section class="enterprise-section">
		<div class="enterprise-section-head">
			<p class="enterprise-kicker">Control Stack</p>
			<h2>Enterprise-critical control pillars</h2>
		</div>
		<div class="enterprise-pillar-grid">
			{#each governancePillars as pillar (pillar.title)}
				<article class="enterprise-pillar-card glass-panel">
					<h3>{pillar.title}</h3>
					<p>{pillar.detail}</p>
				</article>
			{/each}
		</div>
	</section>

	<section class="enterprise-section enterprise-track-grid">
		<article class="glass-panel enterprise-track-card">
			<p class="enterprise-kicker">Self-Serve Track</p>
			<h3>Starter, Growth, and Pro teams</h3>
			<ul>
				<li>Launch quickly with plan-based controls and guided onboarding.</li>
				<li>Run ROI and remediation loops directly in your workspace.</li>
				<li>Expand governance depth as teams and spend surface grow.</li>
			</ul>
			<a href={`${base}/pricing`} class="btn btn-secondary">View Plans</a>
		</article>
		<article class="glass-panel enterprise-track-card enterprise-track-card-featured">
			<p class="enterprise-kicker">Enterprise Track</p>
			<h3>Formal diligence and procurement workflows</h3>
			<ul>
				<li>Coordinate security, legal, procurement, and finance sign-off.</li>
				<li>Review governance artifacts before full production activation.</li>
				<li>Operate a staged rollout with explicit control checkpoints.</li>
			</ul>
			<a href={enterpriseMailHref} class="btn btn-primary">Open Enterprise Intake</a>
		</article>
	</section>

	<section class="enterprise-section glass-panel enterprise-proof-card">
		<div class="enterprise-proof-copy">
			<p class="enterprise-kicker">Procurement Readiness Pack</p>
			<h2>Use externally framed diligence artifacts</h2>
			<p>
				Package your internal review quickly with buyer-facing artifacts covering governance controls,
				access posture, rollout risk, and commercial readiness assumptions.
			</p>
		</div>
		<div class="enterprise-proof-actions">
			<a href={`${base}/resources/valdrics-enterprise-one-pager.md`} class="btn btn-secondary">
				Download Executive One-Pager
			</a>
			<a href={`${base}/resources/global-finops-compliance-workbook.md`} class="btn btn-secondary">
				Download Compliance Checklist
			</a>
			<a href={`${base}/docs/technical-validation`} class="btn btn-secondary">
				Open Technical Validation
			</a>
		</div>
	</section>
</div>

<style>
	.enterprise-shell {
		position: relative;
		max-width: 1180px;
		margin: 0 auto;
		padding: 2.5rem 1.5rem 4.5rem;
		display: grid;
		gap: 1.5rem;
		overflow: hidden;
	}

	.enterprise-bg-glow {
		position: absolute;
		pointer-events: none;
		border-radius: 999px;
		filter: blur(56px);
		opacity: 0.5;
		z-index: 0;
	}

	.enterprise-bg-glow-a {
		width: 22rem;
		height: 22rem;
		top: -7rem;
		left: -8rem;
		background: radial-gradient(circle, rgb(34 211 238 / 0.34), transparent 70%);
	}

	.enterprise-bg-glow-b {
		width: 24rem;
		height: 24rem;
		right: -9rem;
		top: 11rem;
		background: radial-gradient(circle, rgb(16 185 129 / 0.27), transparent 72%);
	}

	.enterprise-bg-grid {
		position: absolute;
		inset: -14% -12% -8% -12%;
		pointer-events: none;
		background-image:
			linear-gradient(rgb(34 211 238 / 0.14) 1px, transparent 1px),
			linear-gradient(90deg, rgb(34 211 238 / 0.12) 1px, transparent 1px);
		background-size: 56px 56px;
		mask-image: radial-gradient(ellipse at 55% 35%, rgb(0 0 0 / 0.78), transparent 80%);
		-webkit-mask-image: radial-gradient(ellipse at 55% 35%, rgb(0 0 0 / 0.78), transparent 80%);
		opacity: 0.34;
		z-index: 0;
		animation: enterpriseGridDrift 18s linear infinite;
	}

	.enterprise-bg-aurora {
		position: absolute;
		inset: -12% -18% auto -18%;
		height: 68%;
		pointer-events: none;
		background:
			radial-gradient(45% 36% at 18% 45%, rgb(34 211 238 / 0.2), transparent 70%),
			radial-gradient(45% 38% at 80% 28%, rgb(16 185 129 / 0.14), transparent 72%),
			radial-gradient(35% 28% at 52% 12%, rgb(79 70 229 / 0.11), transparent 78%);
		filter: blur(2px);
		opacity: 0.72;
		z-index: 0;
		animation: enterpriseAuroraShift 14s ease-in-out infinite alternate;
	}

	.enterprise-signal-field {
		position: absolute;
		inset: -8% -9% auto -9%;
		height: 36rem;
		pointer-events: none;
		z-index: 0;
	}

	.enterprise-signal-core {
		position: absolute;
		left: 50%;
		top: 42%;
		width: 15rem;
		height: 15rem;
		transform: translate(-50%, -50%);
		border-radius: 999px;
		display: grid;
		place-items: center;
		background: radial-gradient(circle, rgb(34 211 238 / 0.19), transparent 70%);
		border: 1px solid rgb(34 211 238 / 0.24);
		box-shadow:
			0 0 90px rgb(34 211 238 / 0.19),
			0 0 130px rgb(16 185 129 / 0.09);
	}

	.enterprise-signal-core::before,
	.enterprise-signal-core::after {
		content: '';
		position: absolute;
		border-radius: inherit;
		pointer-events: none;
	}

	.enterprise-signal-core::before {
		inset: -3rem;
		background: conic-gradient(
			from 0deg,
			transparent 0deg 38deg,
			rgb(34 211 238 / 0.5) 38deg 62deg,
			transparent 62deg 156deg,
			rgb(16 185 129 / 0.46) 156deg 188deg,
			transparent 188deg 274deg,
			rgb(79 70 229 / 0.4) 274deg 302deg,
			transparent 302deg 360deg
		);
		filter: blur(0.55px);
		opacity: 0.72;
		animation: enterpriseSignalRotate 22s linear infinite;
	}

	.enterprise-signal-core::after {
		inset: -1rem;
		border: 1px solid rgb(34 211 238 / 0.34);
		opacity: 0.7;
	}

	.enterprise-signal-core :global(svg) {
		opacity: 0.28;
		filter: saturate(135%);
	}

	.enterprise-signal-ring {
		position: absolute;
		left: 50%;
		top: 42%;
		transform: translate(-50%, -50%);
		border-radius: 999px;
		mix-blend-mode: screen;
	}

	.enterprise-signal-ring-a {
		width: 21rem;
		height: 21rem;
		border: 1.5px dashed rgb(34 211 238 / 0.36);
		animation: enterpriseSignalRotate 24s linear infinite;
	}

	.enterprise-signal-ring-b {
		width: 33rem;
		height: 33rem;
		border: 1.5px dashed rgb(16 185 129 / 0.31);
		animation: enterpriseSignalRotateReverse 32s linear infinite;
	}

	.enterprise-signal-ring-c {
		width: 45rem;
		height: 45rem;
		border: 1px solid rgb(79 70 229 / 0.22);
		animation: enterpriseSignalRotate 42s linear infinite;
	}

	.enterprise-signal-line {
		position: absolute;
		height: 2px;
		background: linear-gradient(90deg, transparent, rgb(34 211 238 / 0.7), transparent);
		filter: drop-shadow(0 0 10px rgb(34 211 238 / 0.3));
		transform-origin: left center;
		animation: enterpriseSignalPulse 7s ease-in-out infinite;
	}

	.enterprise-signal-line-a {
		top: 24%;
		left: 17%;
		width: 32%;
		transform: rotate(11deg);
		animation-delay: 0.6s;
	}

	.enterprise-signal-line-b {
		top: 54%;
		right: 14%;
		width: 34%;
		transform: rotate(-16deg);
		animation-delay: 1.7s;
	}

	.enterprise-signal-line-c {
		top: 72%;
		left: 31%;
		width: 22%;
		transform: rotate(-36deg);
		animation-delay: 3.1s;
	}

	.enterprise-signal-node {
		position: absolute;
		width: 0.85rem;
		height: 0.85rem;
		border-radius: 999px;
		background: rgb(34 211 238 / 0.9);
		box-shadow: 0 0 20px rgb(34 211 238 / 0.65);
		animation: enterpriseNodePulse 4.2s ease-in-out infinite;
	}

	.enterprise-signal-node-a {
		top: 20%;
		left: 30%;
	}

	.enterprise-signal-node-b {
		top: 30%;
		right: 28%;
		animation-delay: 0.9s;
	}

	.enterprise-signal-node-c {
		top: 57%;
		left: 22%;
		animation-delay: 1.8s;
	}

	.enterprise-signal-node-d {
		top: 66%;
		right: 24%;
		animation-delay: 2.4s;
	}

	.enterprise-signal-node-e {
		top: 80%;
		left: 46%;
		animation-delay: 3.2s;
	}

	.enterprise-logo-orbit {
		position: absolute;
		display: grid;
		place-items: center;
		width: 10.8rem;
		height: 10.8rem;
		border-radius: 999px;
		border: 1px solid rgb(34 211 238 / 0.26);
		background: rgb(10 13 18 / 0.42);
		box-shadow: 0 0 55px rgb(34 211 238 / 0.16);
		pointer-events: none;
		z-index: 0;
	}

	.enterprise-logo-orbit :global(svg) {
		opacity: 0.5;
	}

	.enterprise-logo-orbit::before,
	.enterprise-logo-orbit::after {
		content: '';
		position: absolute;
		inset: -0.55rem;
		border-radius: inherit;
		border: 1px dashed rgb(34 211 238 / 0.2);
	}

	.enterprise-logo-orbit::after {
		inset: -1.8rem;
		border-style: solid;
		border-color: rgb(16 185 129 / 0.2);
		opacity: 0.8;
	}

	.enterprise-logo-orbit-a {
		top: 3%;
		right: 1.5%;
		animation: enterpriseLogoFloatA 13s ease-in-out infinite;
	}

	.enterprise-logo-orbit-b {
		top: 28%;
		left: -3.8rem;
		animation: enterpriseLogoFloatB 15s ease-in-out infinite;
	}

	.enterprise-logo-orbit-c {
		bottom: 4%;
		right: -3.3rem;
		animation: enterpriseLogoFloatC 14s ease-in-out infinite;
	}

	.enterprise-shell > section {
		position: relative;
		z-index: 2;
	}

	.enterprise-kicker {
		font-family: 'Space Grotesk', 'Sora', var(--font-sans);
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--color-accent-400);
		margin: 0;
	}

	.enterprise-hero {
		padding: 2rem;
		background:
			linear-gradient(140deg, rgb(34 211 238 / 0.12), transparent 48%),
			linear-gradient(220deg, rgb(16 185 129 / 0.09), transparent 54%),
			rgba(15, 19, 24, 0.76);
	}

	.enterprise-hero h1 {
		margin: 0.6rem 0 0;
		font-family: 'Space Grotesk', 'Sora', var(--font-sans);
		font-size: clamp(1.75rem, 4vw, 2.55rem);
		line-height: 1.08;
		letter-spacing: -0.015em;
		max-width: 18ch;
		color: var(--color-ink-50);
	}

	.enterprise-hero-sub {
		margin: 0.9rem 0 0;
		max-width: 72ch;
		color: var(--color-ink-200);
		font-size: 1.02rem;
	}

	.enterprise-hero-cta {
		display: flex;
		flex-wrap: wrap;
		gap: 0.7rem;
		margin-top: 1.4rem;
	}

	.enterprise-metric-grid {
		margin-top: 1.4rem;
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 0.75rem;
	}

	.enterprise-cta-note {
		margin: 0.6rem 0 0;
		color: var(--color-ink-300);
		font-size: 0.88rem;
	}

	.enterprise-metric-card {
		border: 1px solid rgb(255 255 255 / 0.11);
		background: rgb(10 13 18 / 0.58);
		border-radius: 0.8rem;
		padding: 0.8rem 0.9rem;
	}

	.enterprise-metric-k {
		margin: 0;
		color: var(--color-ink-300);
		font-size: 0.72rem;
		letter-spacing: 0.08em;
		text-transform: uppercase;
	}

	.enterprise-metric-v {
		margin: 0.4rem 0 0;
		color: var(--color-ink-100);
		font-weight: 600;
		line-height: 1.35;
	}

	.enterprise-section {
		display: grid;
		gap: 1rem;
	}

	.enterprise-section-head h2 {
		margin: 0.45rem 0 0;
		font-family: 'Space Grotesk', 'Sora', var(--font-sans);
		font-size: clamp(1.3rem, 3vw, 1.9rem);
		color: var(--color-ink-50);
	}

	.enterprise-pillar-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.95rem;
	}

	.enterprise-pillar-card {
		padding: 1.2rem;
		background:
			linear-gradient(165deg, rgb(34 211 238 / 0.08), transparent 43%),
			rgb(15 19 24 / 0.76);
	}

	.enterprise-pillar-card h3 {
		margin: 0;
		font-family: 'Space Grotesk', 'Sora', var(--font-sans);
		font-size: 1.08rem;
		color: var(--color-ink-50);
	}

	.enterprise-pillar-card p {
		margin: 0.55rem 0 0;
		color: var(--color-ink-200);
		line-height: 1.55;
	}

	.enterprise-track-grid {
		grid-template-columns: repeat(2, minmax(0, 1fr));
	}

	.enterprise-track-card {
		display: grid;
		gap: 0.85rem;
		padding: 1.35rem;
	}

	.enterprise-track-card-featured {
		background:
			linear-gradient(145deg, rgb(34 211 238 / 0.14), transparent 48%),
			linear-gradient(230deg, rgb(16 185 129 / 0.1), transparent 50%),
			rgb(15 19 24 / 0.8);
		border-color: rgb(34 211 238 / 0.35);
	}

	.enterprise-track-card h3 {
		margin: 0;
		font-family: 'Space Grotesk', 'Sora', var(--font-sans);
		font-size: 1.2rem;
		color: var(--color-ink-50);
	}

	.enterprise-track-card ul {
		margin: 0;
		padding-left: 1rem;
		display: grid;
		gap: 0.45rem;
		color: var(--color-ink-200);
	}

	.enterprise-proof-card {
		padding: 1.4rem;
		display: grid;
		gap: 1rem;
		grid-template-columns: 1.4fr 1fr;
		background:
			linear-gradient(130deg, rgb(34 211 238 / 0.11), transparent 50%),
			rgba(15, 19, 24, 0.78);
	}

	.enterprise-proof-copy h2 {
		margin: 0.45rem 0 0;
		font-family: 'Space Grotesk', 'Sora', var(--font-sans);
		font-size: clamp(1.25rem, 2.8vw, 1.8rem);
		color: var(--color-ink-50);
	}

	.enterprise-proof-copy p {
		margin: 0.7rem 0 0;
		color: var(--color-ink-200);
		line-height: 1.55;
	}

	.enterprise-proof-actions {
		display: grid;
		align-content: start;
		gap: 0.6rem;
	}

	.enterprise-proof-actions .btn {
		width: 100%;
	}

	@media (max-width: 1024px) {
		.enterprise-signal-field {
			inset: -10% -12% auto -12%;
			height: 30rem;
		}

		.enterprise-signal-core {
			width: 12.5rem;
			height: 12.5rem;
		}

		.enterprise-proof-card {
			grid-template-columns: 1fr;
		}
	}

	@media (max-width: 860px) {
		.enterprise-signal-ring-c {
			display: none;
		}

		.enterprise-metric-grid,
		.enterprise-pillar-grid,
		.enterprise-track-grid {
			grid-template-columns: 1fr;
		}
	}

	@media (max-width: 640px) {
		.enterprise-shell {
			padding: 1.5rem 1rem 3rem;
		}

		.enterprise-signal-field {
			opacity: 0.56;
			inset: -10% -16% auto -16%;
			height: 24rem;
		}

		.enterprise-signal-line {
			display: none;
		}

		.enterprise-logo-orbit {
			display: none;
		}

		.enterprise-hero {
			padding: 1.15rem;
		}

		.enterprise-proof-card,
		.enterprise-track-card,
		.enterprise-pillar-card {
			padding: 1rem;
		}

		.enterprise-hero-sub {
			font-size: 0.96rem;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.enterprise-bg-grid,
		.enterprise-bg-aurora,
		.enterprise-logo-orbit,
		.enterprise-signal-core::before,
		.enterprise-signal-ring,
		.enterprise-signal-line,
		.enterprise-signal-node {
			animation: none !important;
		}
	}

	@keyframes enterpriseGridDrift {
		0% {
			background-position:
				0 0,
				0 0;
		}
		100% {
			background-position:
				56px 28px,
				28px 56px;
		}
	}

	@keyframes enterpriseAuroraShift {
		0% {
			transform: translate3d(-1%, 0, 0) scale(1);
			opacity: 0.7;
		}
		100% {
			transform: translate3d(2%, 1.5%, 0) scale(1.04);
			opacity: 0.86;
		}
	}

	@keyframes enterpriseLogoFloatA {
		0%,
		100% {
			transform: translate3d(0, 0, 0) rotate(0deg);
		}
		50% {
			transform: translate3d(-0.7rem, 1rem, 0) rotate(11deg);
		}
	}

	@keyframes enterpriseLogoFloatB {
		0%,
		100% {
			transform: translate3d(0, 0, 0) rotate(0deg);
		}
		50% {
			transform: translate3d(0.9rem, -0.8rem, 0) rotate(-10deg);
		}
	}

	@keyframes enterpriseLogoFloatC {
		0%,
		100% {
			transform: translate3d(0, 0, 0) rotate(0deg);
		}
		50% {
			transform: translate3d(-0.65rem, -0.85rem, 0) rotate(8deg);
		}
	}

	@keyframes enterpriseSignalRotate {
		from {
			transform: translate(-50%, -50%) rotate(0deg);
		}
		to {
			transform: translate(-50%, -50%) rotate(360deg);
		}
	}

	@keyframes enterpriseSignalRotateReverse {
		from {
			transform: translate(-50%, -50%) rotate(360deg);
		}
		to {
			transform: translate(-50%, -50%) rotate(0deg);
		}
	}

	@keyframes enterpriseSignalPulse {
		0%,
		100% {
			opacity: 0.42;
			filter: drop-shadow(0 0 7px rgb(34 211 238 / 0.22));
		}
		50% {
			opacity: 0.9;
			filter: drop-shadow(0 0 14px rgb(34 211 238 / 0.46));
		}
	}

	@keyframes enterpriseNodePulse {
		0%,
		100% {
			transform: scale(0.8);
			opacity: 0.65;
		}
		45% {
			transform: scale(1.2);
			opacity: 1;
		}
	}
</style>
