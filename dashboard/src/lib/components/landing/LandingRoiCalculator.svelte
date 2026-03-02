<script lang="ts">
	import type { LandingRoiInputs, LandingRoiResult } from '$lib/landing/roiCalculator';

	let {
		roiInputs,
		roiResult,
		roiMonthlySpendUsd,
		roiExpectedReductionPct,
		roiRolloutDays,
		roiTeamMembers,
		roiBlendedHourlyUsd,
		buildRoiCtaHref,
		formatUsd,
		onRoiControlInput,
		onRoiMonthlySpendChange,
		onRoiExpectedReductionChange,
		onRoiRolloutDaysChange,
		onRoiTeamMembersChange,
		onRoiBlendedHourlyChange,
		onRoiCta,
		sectionId = 'roi',
		heading = 'See your 12-month control ROI before you commit',
		subtitle = 'Adjust spend and rollout assumptions to estimate savings velocity, payback timing, and net economic impact.',
		ctaLabel = 'Run This In Your Environment',
		ctaNote = 'Model output is directional and intended for planning alignment across engineering, finance, and leadership.'
	}: {
		roiInputs: LandingRoiInputs;
		roiResult: LandingRoiResult;
		roiMonthlySpendUsd: number;
		roiExpectedReductionPct: number;
		roiRolloutDays: number;
		roiTeamMembers: number;
		roiBlendedHourlyUsd: number;
		buildRoiCtaHref: string;
		formatUsd: (amount: number) => string;
		onRoiControlInput: () => void;
		onRoiMonthlySpendChange: (value: number) => void;
		onRoiExpectedReductionChange: (value: number) => void;
		onRoiRolloutDaysChange: (value: number) => void;
		onRoiTeamMembersChange: (value: number) => void;
		onRoiBlendedHourlyChange: (value: number) => void;
		onRoiCta: () => void;
		sectionId?: string;
		heading?: string;
		subtitle?: string;
		ctaLabel?: string;
		ctaNote?: string;
	} = $props();

	function updateRoiMonthlySpend(event: Event): void {
		onRoiMonthlySpendChange(Number((event.currentTarget as HTMLInputElement).value));
		onRoiControlInput();
	}

	function updateRoiReduction(event: Event): void {
		onRoiExpectedReductionChange(Number((event.currentTarget as HTMLInputElement).value));
		onRoiControlInput();
	}

	function updateRoiRollout(event: Event): void {
		onRoiRolloutDaysChange(Number((event.currentTarget as HTMLInputElement).value));
		onRoiControlInput();
	}

	function updateRoiTeam(event: Event): void {
		onRoiTeamMembersChange(Number((event.currentTarget as HTMLInputElement).value));
		onRoiControlInput();
	}

	function updateRoiHourly(event: Event): void {
		onRoiBlendedHourlyChange(Number((event.currentTarget as HTMLInputElement).value));
		onRoiControlInput();
	}
</script>

<section
	id={sectionId}
	class="container mx-auto px-6 pb-16 landing-section-lazy"
	data-landing-section={sectionId}
>
	<div class="landing-section-head">
		<h2 class="landing-h2">{heading}</h2>
		<p class="landing-section-sub">{subtitle}</p>
	</div>

	<div class="landing-roi-grid">
		<div class="glass-panel landing-roi-controls">
			<div class="landing-roi-control">
				<label for="roi-monthly-spend" class="landing-roi-label">Cloud + software monthly spend</label>
				<div class="landing-roi-meta">
					<span>{formatUsd(roiInputs.monthlySpendUsd)}</span>
				</div>
				<input
					id="roi-monthly-spend"
					type="range"
					min="5000"
					max="500000"
					step="5000"
					value={roiMonthlySpendUsd}
					oninput={updateRoiMonthlySpend}
				/>
			</div>

			<div class="landing-roi-control">
				<label for="roi-reduction" class="landing-roi-label">Expected reduction (%)</label>
				<div class="landing-roi-meta">
					<span>{roiInputs.expectedReductionPct}%</span>
				</div>
				<input
					id="roi-reduction"
					type="range"
					min="1"
					max="30"
					step="1"
					value={roiExpectedReductionPct}
					oninput={updateRoiReduction}
				/>
			</div>

			<div class="landing-roi-control">
				<label for="roi-rollout" class="landing-roi-label">Rollout duration (days)</label>
				<div class="landing-roi-meta">
					<span>{roiInputs.rolloutDays} days</span>
				</div>
				<input
					id="roi-rollout"
					type="range"
					min="7"
					max="120"
					step="1"
					value={roiRolloutDays}
					oninput={updateRoiRollout}
				/>
			</div>

			<div class="landing-roi-control landing-roi-grid-2">
				<div>
					<label for="roi-team" class="landing-roi-label">Team members</label>
					<input
						id="roi-team"
						type="number"
						min="1"
						max="12"
						step="1"
						class="input mt-2"
						value={roiTeamMembers}
						oninput={updateRoiTeam}
					/>
				</div>
				<div>
					<label for="roi-hourly" class="landing-roi-label">Blended hourly rate</label>
					<input
						id="roi-hourly"
						type="number"
						min="50"
						max="400"
						step="5"
						class="input mt-2"
						value={roiBlendedHourlyUsd}
						oninput={updateRoiHourly}
					/>
				</div>
			</div>
		</div>

		<div class="glass-panel landing-roi-results">
			<p class="landing-proof-k">Projected 12-Month Impact</p>
			<div class="landing-roi-metrics">
				<div class="landing-roi-metric">
					<p>Monthly savings potential</p>
					<strong>{formatUsd(roiResult.monthlySavingsUsd)}</strong>
				</div>
				<div class="landing-roi-metric">
					<p>Annual gross savings</p>
					<strong>{formatUsd(roiResult.annualGrossSavingsUsd)}</strong>
				</div>
				<div class="landing-roi-metric">
					<p>Implementation + platform cost</p>
					<strong>{formatUsd(roiResult.implementationCostUsd)}</strong>
				</div>
				<div class="landing-roi-metric">
					<p>Annual net economic value</p>
					<strong class={roiResult.annualNetSavingsUsd >= 0 ? 'is-positive' : 'is-negative'}>
						{formatUsd(roiResult.annualNetSavingsUsd)}
					</strong>
				</div>
				<div class="landing-roi-metric">
					<p>Estimated payback window</p>
					<strong>{roiResult.paybackDays ? `${roiResult.paybackDays} days` : 'N/A'}</strong>
				</div>
				<div class="landing-roi-metric">
					<p>Gross ROI multiple</p>
					<strong>{roiResult.roiMultiple.toFixed(2)}x</strong>
				</div>
			</div>
			<div class="landing-roi-cta">
				<a href={buildRoiCtaHref} class="btn btn-primary" onclick={onRoiCta}>
					{ctaLabel}
				</a>
				<p class="landing-roi-note">{ctaNote}</p>
			</div>
		</div>
	</div>
</section>
