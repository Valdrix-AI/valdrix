import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/svelte';
import LandingHeroCopy from '$lib/components/landing/LandingHeroCopy.svelte';
import LandingSignalMapCard from '$lib/components/landing/LandingSignalMapCard.svelte';
import LandingRoiSimulator from '$lib/components/landing/LandingRoiSimulator.svelte';
import LandingRoiCalculator from '$lib/components/landing/LandingRoiCalculator.svelte';
import { REALTIME_SIGNAL_SNAPSHOTS } from '$lib/landing/realtimeSignalMap';
import { calculateLandingRoi, normalizeLandingRoiInputs } from '$lib/landing/roiCalculator';

describe('Landing component decomposition', () => {
	it('renders hero copy and keeps CTA tracking callbacks wired', async () => {
		const onPrimaryCta = vi.fn();
		const onSecondaryCta = vi.fn();
		const onSimulatorCta = vi.fn();

		render(LandingHeroCopy, {
			props: {
				heroTitle: 'Control every dollar in your cloud and software stack.',
				heroSubtitle: 'From signal to owner and approved action in one loop.',
				heroQuantPromise: 'Target 10-18% controllable spend opportunity.',
				primaryCtaLabel: 'Start Free',
				secondaryCtaLabel: 'See Plans',
				secondaryCtaHref: '#plans',
				primaryCtaHref: '/auth/login',
				onPrimaryCta,
				onSecondaryCta,
				onSimulatorCta
			}
		});

		expect(screen.getByRole('heading', { level: 1 })).toBeTruthy();
		await fireEvent.click(screen.getByRole('link', { name: /start free/i }));
		await fireEvent.click(screen.getByRole('link', { name: /see plans/i }));
		await fireEvent.click(screen.getByRole('link', { name: /run the spend scenario simulator/i }));
		expect(onPrimaryCta).toHaveBeenCalledTimes(1);
		expect(onSecondaryCta).toHaveBeenCalledTimes(1);
		expect(onSimulatorCta).toHaveBeenCalledTimes(1);
	});

	it('renders signal map card and propagates interactions', async () => {
		const onSelectSignalLane = vi.fn();
		const onSelectDemoStep = vi.fn();
		const onSelectSnapshot = vi.fn();
		const onSignalMapElementChange = vi.fn();

		const snapshot = REALTIME_SIGNAL_SNAPSHOTS[0];
		const activeLane = snapshot?.lanes[0];
		expect(snapshot).toBeTruthy();
		expect(activeLane).toBeTruthy();
		if (!snapshot || !activeLane) {
			return;
		}

		render(LandingSignalMapCard, {
			props: {
				activeSnapshot: snapshot,
				activeSignalLane: activeLane,
				signalMapInView: true,
				snapshotIndex: 0,
				demoStepIndex: 0,
				onSelectSignalLane,
				onSelectDemoStep,
				onSelectSnapshot,
				onSignalMapElementChange
			}
		});

		expect(screen.getByText(/realtime signal map/i)).toBeTruthy();
		const firstLaneTab = screen.getByRole('tab', { name: /economic visibility/i });
		await fireEvent.click(firstLaneTab);
		expect(onSelectSignalLane).toHaveBeenCalled();

		const demoButton = screen.getByRole('button', { name: /^assess$/i });
		await fireEvent.click(demoButton);
		expect(onSelectDemoStep).toHaveBeenCalled();

		const snapshotButton = screen.getByRole('button', { name: /snapshot b/i });
		await fireEvent.click(snapshotButton);
		expect(onSelectSnapshot).toHaveBeenCalled();
		expect(onSignalMapElementChange).toHaveBeenCalled();
	});

	it('updates simulator controls through typed callbacks', async () => {
		const onTrackScenarioAdjust = vi.fn();
		const onScenarioWasteWithoutChange = vi.fn();
		const onScenarioWasteWithChange = vi.fn();
		const onScenarioWindowChange = vi.fn();

		render(LandingRoiSimulator, {
			props: {
				normalizedScenarioWasteWithoutPct: 18,
				normalizedScenarioWasteWithPct: 7,
				normalizedScenarioWindowMonths: 12,
				scenarioWithoutBarPct: 100,
				scenarioWithBarPct: 40,
				scenarioWasteWithoutUsd: 21600,
				scenarioWasteWithUsd: 8400,
				scenarioWasteRecoveryMonthlyUsd: 13200,
				scenarioWasteRecoveryWindowUsd: 158400,
				monthlySpendUsd: 120000,
				scenarioWasteWithoutPct: 18,
				scenarioWasteWithPct: 7,
				scenarioWindowMonths: 12,
				formatUsd: (amount: number) => `$${amount}`,
				onTrackScenarioAdjust,
				onScenarioWasteWithoutChange,
				onScenarioWasteWithChange,
				onScenarioWindowChange
			}
		});

		await fireEvent.input(screen.getByLabelText(/reactive waste rate/i), {
			target: { value: '19' }
		});
		await fireEvent.input(screen.getByLabelText(/managed waste rate/i), {
			target: { value: '8' }
		});
		await fireEvent.input(screen.getByLabelText(/decision window \(months\)/i), {
			target: { value: '11' }
		});

		expect(onScenarioWasteWithoutChange).toHaveBeenCalledWith(19);
		expect(onScenarioWasteWithChange).toHaveBeenCalledWith(8);
		expect(onScenarioWindowChange).toHaveBeenCalledWith(11);
		expect(onTrackScenarioAdjust).toHaveBeenCalledTimes(3);
	});

	it('updates ROI controls and CTA callback from calculator component', async () => {
		const onRoiControlInput = vi.fn();
		const onRoiMonthlySpendChange = vi.fn();
		const onRoiExpectedReductionChange = vi.fn();
		const onRoiRolloutDaysChange = vi.fn();
		const onRoiTeamMembersChange = vi.fn();
		const onRoiBlendedHourlyChange = vi.fn();
		const onRoiCta = vi.fn();

		const roiInputs = normalizeLandingRoiInputs({
			monthlySpendUsd: 120000,
			expectedReductionPct: 12,
			rolloutDays: 30,
			teamMembers: 2,
			blendedHourlyUsd: 145,
			platformAnnualCostUsd: 9600
		});
		const roiResult = calculateLandingRoi(roiInputs);

		render(LandingRoiCalculator, {
			props: {
				roiInputs,
				roiResult,
				roiMonthlySpendUsd: 120000,
				roiExpectedReductionPct: 12,
				roiRolloutDays: 30,
				roiTeamMembers: 2,
				roiBlendedHourlyUsd: 145,
				buildRoiCtaHref: '/auth/login?intent=roi_assessment',
				formatUsd: (amount: number) => `$${amount}`,
				onRoiControlInput,
				onRoiMonthlySpendChange,
				onRoiExpectedReductionChange,
				onRoiRolloutDaysChange,
				onRoiTeamMembersChange,
				onRoiBlendedHourlyChange,
				onRoiCta
			}
		});

		await fireEvent.input(screen.getByLabelText(/cloud \+ software monthly spend/i), {
			target: { value: '130000' }
		});
		await fireEvent.input(screen.getByLabelText(/expected reduction/i), { target: { value: '13' } });
		await fireEvent.input(screen.getByLabelText(/rollout duration/i), { target: { value: '35' } });
		await fireEvent.input(screen.getByLabelText(/team members/i), { target: { value: '3' } });
		await fireEvent.input(screen.getByLabelText(/blended hourly rate/i), { target: { value: '150' } });
		await fireEvent.click(screen.getByRole('link', { name: /run this in your environment/i }));

		expect(onRoiMonthlySpendChange).toHaveBeenCalledWith(130000);
		expect(onRoiExpectedReductionChange).toHaveBeenCalledWith(13);
		expect(onRoiRolloutDaysChange).toHaveBeenCalledWith(35);
		expect(onRoiTeamMembersChange).toHaveBeenCalledWith(3);
		expect(onRoiBlendedHourlyChange).toHaveBeenCalledWith(150);
		expect(onRoiControlInput).toHaveBeenCalledTimes(5);
		expect(onRoiCta).toHaveBeenCalledTimes(1);
	});
});
