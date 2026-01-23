<!--
  DateRangePicker Component
  
  Features:
  - Preset buttons (7d, 30d, 90d)
  - "Custom" option to show date inputs
  - Emits dateChange event with { startDate, endDate }
-->

<script lang="ts">
	let { value = $bindable('30d'), onDateChange } = $props<{
		value?: string;
		onDateChange?: (dates: { startDate: string; endDate: string }) => void;
	}>();

	let showCustom = $state(false);
	let customStartDate = $state('');
	let customEndDate = $state('');
	let initialized = $state(false);

	// Preset options
	const presets = [
		{ value: '7d', label: '7 Days' },
		{ value: '30d', label: '30 Days' },
		{ value: '90d', label: '90 Days' }
	];

	// Calculate dates from preset
	function getDatesFromPreset(preset: string): { startDate: string; endDate: string } {
		const end = new Date();
		const days = parseInt(preset.replace('d', ''));
		const start = new Date(Date.now() - days * 24 * 60 * 60 * 1000);
		return {
			startDate: start.toISOString().split('T')[0],
			endDate: end.toISOString().split('T')[0]
		};
	}

	function selectPreset(preset: string) {
		value = preset;
		showCustom = false;
		const dates = getDatesFromPreset(preset);
		onDateChange?.(dates);
	}

	function toggleCustom() {
		showCustom = !showCustom;
		if (showCustom) {
			if (!customStartDate || !customEndDate) {
				const dates = getDatesFromPreset('30d');
				customStartDate = dates.startDate;
				customEndDate = dates.endDate;
			}
			value = 'custom';
		}
	}

	function applyCustomRange() {
		if (customStartDate && customEndDate) {
			onDateChange?.({
				startDate: customStartDate,
				endDate: customEndDate
			});
		}
	}

	// Initialize with default dates
	$effect(() => {
		if (!initialized) {
			const dates = getDatesFromPreset(value);
			onDateChange?.(dates);
			initialized = true;
		}
	});
</script>

<div class="date-range-picker">
	<!-- Preset Buttons -->
	<div class="presets">
		{#each presets as preset (preset.value)}
			<button
				class="preset-btn"
				class:active={value === preset.value && !showCustom}
				onclick={() => selectPreset(preset.value)}
			>
				{preset.label}
			</button>
		{/each}
		<button class="preset-btn" class:active={showCustom} onclick={toggleCustom}> 📅 Custom </button>
	</div>

	<!-- Custom Date Range -->
	{#if showCustom}
		<div class="custom-range">
			<div class="date-inputs">
				<div class="date-field">
					<label for="start-date">From</label>
					<input type="date" id="start-date" bind:value={customStartDate} />
				</div>
				<span class="separator">→</span>
				<div class="date-field">
					<label for="end-date">To</label>
					<input type="date" id="end-date" bind:value={customEndDate} />
				</div>
				<button
					class="apply-btn"
					disabled={!customStartDate || !customEndDate}
					onclick={applyCustomRange}
				>
					Apply
				</button>
			</div>
		</div>
	{/if}
</div>

<style>
	.date-range-picker {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.presets {
		display: flex;
		gap: 0.5rem;
		flex-wrap: wrap;
	}

	.preset-btn {
		padding: 0.5rem 1rem;
		border: 1px solid var(--color-ink-700);
		border-radius: 0.5rem;
		background: var(--color-ink-900);
		color: var(--color-ink-300);
		cursor: pointer;
		font-size: 0.875rem;
		transition: all 0.2s;
	}

	.preset-btn:hover {
		border-color: var(--color-accent-500);
		color: white;
	}

	.preset-btn.active {
		background: var(--color-accent-500);
		border-color: var(--color-accent-500);
		color: white;
	}

	.custom-range {
		padding: 1rem;
		background: var(--color-ink-900);
		border: 1px solid var(--color-ink-700);
		border-radius: 0.5rem;
	}

	.date-inputs {
		display: flex;
		align-items: flex-end;
		gap: 1rem;
		flex-wrap: wrap;
	}

	.date-field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.date-field label {
		font-size: 0.75rem;
		color: var(--color-ink-400);
	}

	.date-field input {
		padding: 0.5rem;
		border: 1px solid var(--color-ink-700);
		border-radius: 0.5rem;
		background: var(--color-ink-800);
		color: white;
		font-size: 0.875rem;
	}

	.date-field input:focus {
		outline: none;
		border-color: var(--color-accent-500);
	}

	.separator {
		color: var(--color-ink-500);
		padding-bottom: 0.5rem;
	}

	.apply-btn {
		padding: 0.5rem 1rem;
		background: var(--color-accent-500);
		color: white;
		border: none;
		border-radius: 0.5rem;
		font-size: 0.875rem;
		cursor: pointer;
		transition: all 0.2s;
		align-self: flex-end;
	}

	.apply-btn:hover:not(:disabled) {
		background: var(--color-accent-600);
	}

	.apply-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Make date picker icon visible in dark mode */
	input[type='date']::-webkit-calendar-picker-indicator {
		filter: invert(1);
		cursor: pointer;
	}
</style>
