<script lang="ts">
	let {
		normalizedScenarioWasteWithoutPct,
		normalizedScenarioWasteWithPct,
		normalizedScenarioWindowMonths,
		scenarioWithoutBarPct,
		scenarioWithBarPct,
		scenarioWasteWithoutUsd,
		scenarioWasteWithUsd,
		scenarioWasteRecoveryMonthlyUsd,
		scenarioWasteRecoveryWindowUsd,
		monthlySpendUsd,
		scenarioWasteWithoutPct,
		scenarioWasteWithPct,
		scenarioWindowMonths,
		formatUsd,
		onTrackScenarioAdjust,
		onScenarioWasteWithoutChange,
		onScenarioWasteWithChange,
		onScenarioWindowChange
	}: {
		normalizedScenarioWasteWithoutPct: number;
		normalizedScenarioWasteWithPct: number;
		normalizedScenarioWindowMonths: number;
		scenarioWithoutBarPct: number;
		scenarioWithBarPct: number;
		scenarioWasteWithoutUsd: number;
		scenarioWasteWithUsd: number;
		scenarioWasteRecoveryMonthlyUsd: number;
		scenarioWasteRecoveryWindowUsd: number;
		monthlySpendUsd: number;
		scenarioWasteWithoutPct: number;
		scenarioWasteWithPct: number;
		scenarioWindowMonths: number;
		formatUsd: (amount: number) => string;
		onTrackScenarioAdjust: (control: string) => void;
		onScenarioWasteWithoutChange: (value: number) => void;
		onScenarioWasteWithChange: (value: number) => void;
		onScenarioWindowChange: (value: number) => void;
	} = $props();

	function updateWasteWithout(event: Event): void {
		const value = Number((event.currentTarget as HTMLInputElement).value);
		onScenarioWasteWithoutChange(value);
		onTrackScenarioAdjust('reactive_waste_rate');
	}

	function updateWasteWith(event: Event): void {
		const value = Number((event.currentTarget as HTMLInputElement).value);
		onScenarioWasteWithChange(value);
		onTrackScenarioAdjust('governed_waste_rate');
	}

	function updateWindow(event: Event): void {
		const value = Number((event.currentTarget as HTMLInputElement).value);
		onScenarioWindowChange(value);
		onTrackScenarioAdjust('decision_window');
	}
</script>

<section id="simulator" class="container mx-auto px-6 pb-20 landing-section-lazy" data-landing-section="simulator">
	<div class="landing-section-head">
		<h2 class="landing-h2">Realtime spend scenario simulator</h2>
		<p class="landing-section-sub">
			Compare reactive spend behavior versus owner-led execution and see the economic delta instantly.
		</p>
	</div>

	<div class="landing-sim-grid">
		<div class="glass-panel landing-sim-controls">
			<div class="landing-roi-control">
				<label for="sim-waste-without" class="landing-roi-label">Reactive waste rate (%)</label>
				<div class="landing-roi-meta">
					<span>{normalizedScenarioWasteWithoutPct}%</span>
				</div>
				<input
					id="sim-waste-without"
					type="range"
					min="4"
					max="35"
					step="1"
					value={scenarioWasteWithoutPct}
					oninput={updateWasteWithout}
				/>
			</div>
			<div class="landing-roi-control">
				<label for="sim-waste-with" class="landing-roi-label">Managed waste rate (%)</label>
				<div class="landing-roi-meta">
					<span>{normalizedScenarioWasteWithPct}%</span>
				</div>
				<input
					id="sim-waste-with"
					type="range"
					min="1"
					max={Math.max(1, normalizedScenarioWasteWithoutPct - 1)}
					step="1"
					value={scenarioWasteWithPct}
					oninput={updateWasteWith}
				/>
			</div>
			<div class="landing-roi-control">
				<label for="sim-window" class="landing-roi-label">Decision window (months)</label>
				<div class="landing-roi-meta">
					<span>{normalizedScenarioWindowMonths} months</span>
				</div>
				<input
					id="sim-window"
					type="range"
					min="3"
					max="24"
					step="1"
					value={scenarioWindowMonths}
					oninput={updateWindow}
				/>
			</div>
		</div>

		<div class="glass-panel landing-sim-results">
			<p class="landing-proof-k">Scenario Delta</p>
			<div class="landing-sim-chart" role="img" aria-label="Reactive versus governed waste comparison">
				<div class="landing-sim-bar-row">
					<div class="landing-sim-bar-label">Reactive spend</div>
					<div class="landing-sim-bar-track">
						<span class="landing-sim-bar is-reactive" style={`width:${scenarioWithoutBarPct}%;`}></span>
					</div>
					<div class="landing-sim-bar-value">{formatUsd(scenarioWasteWithoutUsd)}</div>
				</div>
				<div class="landing-sim-bar-row">
					<div class="landing-sim-bar-label">Governed spend</div>
					<div class="landing-sim-bar-track">
						<span class="landing-sim-bar is-governed" style={`width:${scenarioWithBarPct}%;`}></span>
					</div>
					<div class="landing-sim-bar-value">{formatUsd(scenarioWasteWithUsd)}</div>
				</div>
			</div>

			<div class="landing-sim-metrics">
				<div class="landing-sim-metric">
					<p>Recoverable waste / month</p>
					<strong>{formatUsd(scenarioWasteRecoveryMonthlyUsd)}</strong>
				</div>
				<div class="landing-sim-metric">
					<p>Recoverable waste / {normalizedScenarioWindowMonths} months</p>
					<strong>{formatUsd(scenarioWasteRecoveryWindowUsd)}</strong>
				</div>
				<div class="landing-sim-metric">
					<p>Spend context used</p>
					<strong>{formatUsd(monthlySpendUsd)} / month</strong>
				</div>
			</div>
			<p class="landing-roi-note">
				This simulator is directional and designed to accelerate finance + engineering decision alignment.
			</p>
		</div>
	</div>
</section>
