import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/svelte';
import LandingHeroCopy from '$lib/components/landing/LandingHeroCopy.svelte';
import LandingSignalMapCard from '$lib/components/landing/LandingSignalMapCard.svelte';
import LandingRoiSimulator from '$lib/components/landing/LandingRoiSimulator.svelte';
import LandingRoiCalculator from '$lib/components/landing/LandingRoiCalculator.svelte';
import LandingRoiPlannerCta from '$lib/components/landing/LandingRoiPlannerCta.svelte';
import LandingTrustSection from '$lib/components/landing/LandingTrustSection.svelte';
import { REALTIME_SIGNAL_SNAPSHOTS } from '$lib/landing/realtimeSignalMap';
import { calculateLandingRoi, normalizeLandingRoiInputs } from '$lib/landing/roiCalculator';
import './landing_decomposition.lead_exit.svelte.test';

vi.mock('$app/paths', () => ({
	assets: '',
	base: ''
}));

describe('Landing component decomposition', () => {
	it('renders hero copy and keeps CTA tracking callbacks wired', async () => {
		const onPrimaryCta = vi.fn();
		const onSecondaryCta = vi.fn();

		render(LandingHeroCopy, {
			props: {
				heroTitle: 'Control every dollar in your cloud and software stack.',
				heroSubtitle: 'From signal to owner and approved action in one loop.',
				quantPromise: 'Target 10-18% controllable spend recovery opportunity in the first 90 days.',
				primaryCtaLabel: 'Start Free',
				secondaryCtaLabel: 'See it in action',
				secondaryCtaHref: '#signal-map',
				primaryCtaHref: '/auth/login',
				onPrimaryCta,
				onSecondaryCta
			}
		});

		expect(screen.getByRole('heading', { level: 1 })).toBeTruthy();
		await fireEvent.click(screen.getByRole('link', { name: /start free/i }));
		await fireEvent.click(screen.getByRole('link', { name: /see it in action/i }));
		expect(onPrimaryCta).toHaveBeenCalledTimes(1);
		expect(onSecondaryCta).toHaveBeenCalledTimes(1);
		expect(screen.getByText(/what you can verify now/i)).toBeTruthy();
		expect(screen.getByText(/safe access model/i)).toBeTruthy();
		expect(screen.getByText(/first production workflow typically goes live in 3-10 business days/i)).toBeTruthy();
		expect(
			screen.getByRole('link', { name: /technical validation/i }).getAttribute('href')
		).toBe('/docs/technical-validation');
		expect(
			screen.getByRole('link', { name: /access checklist/i }).getAttribute('href')
		).toBe('/resources/global-finops-compliance-workbook.md');
		expect(screen.getByRole('link', { name: /review methodology/i }).getAttribute('href')).toBe(
			'/docs/technical-validation'
		);
		expect(screen.getByRole('link', { name: /live signal map/i }).getAttribute('href')).toBe(
			'#signal-map'
		);
		expect(screen.queryByText(/evidence snapshot · february 28, 2026/i)).toBeNull();

		// Check for GreenOps Global Flip additions
		expect(screen.getByText(/Decision operating layer for spend control/i)).toBeTruthy();
		expect(screen.getByText(/Route the right owner\. Apply checks\. Record the outcome\./i)).toBeTruthy();
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

		expect(screen.getByText(/live decision loop/i)).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: /^open approval chain$/i }));
		const firstLaneTab = screen.getByRole('tab', { name: /signal scoped/i });
		await fireEvent.click(firstLaneTab);
		expect(onSelectSignalLane).toHaveBeenCalled();

		await fireEvent.click(screen.getByRole('button', { name: /open approval chain walkthrough/i }));
		const demoButton = screen.getByRole('button', { name: /^routed$/i });
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
		const onTrackPlannerCta = vi.fn();

		const view = render(LandingRoiSimulator, {
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
				currencyCode: 'USD',
				plannerHref: '/auth/login?intent=roi_assessment',
				onTrackScenarioAdjust,
				onScenarioWasteWithoutChange,
				onScenarioWasteWithChange,
				onScenarioWindowChange,
				onTrackPlannerCta
			}
		});
		const simulatorView = within(view.container);

		await fireEvent.input(simulatorView.getByLabelText(/reactive waste rate/i), {
			target: { value: '19' }
		});
		await fireEvent.input(simulatorView.getByLabelText(/managed waste rate/i), {
			target: { value: '8' }
		});
		await fireEvent.input(simulatorView.getByLabelText(/decision window \(months\)/i), {
			target: { value: '11' }
		});

		expect(onScenarioWasteWithoutChange).toHaveBeenCalledWith(19);
		expect(onScenarioWasteWithChange).toHaveBeenCalledWith(8);
		expect(onScenarioWindowChange).toHaveBeenCalledWith(11);
		expect(onTrackScenarioAdjust).toHaveBeenCalledTimes(3);
		expect(simulatorView.getByRole('link', { name: /review methodology/i }).getAttribute('href')).toBe(
			'/docs/technical-validation'
		);
		expect(simulatorView.getByRole('link', { name: /open assumptions csv/i }).getAttribute('href')).toBe(
			'/resources/valdrics-roi-assumptions.csv'
		);
		await fireEvent.click(simulatorView.getByRole('link', { name: /open full roi planner/i }));
		expect(onTrackPlannerCta).toHaveBeenCalledTimes(1);
	});

	it('renders static ROI snapshot preview and tracks planner CTA', async () => {
		const onTrackCta = vi.fn();
		const view = render(LandingRoiPlannerCta, {
			props: {
				href: '/auth/login?intent=roi_assessment',
				onTrackCta
			}
		});

		const ctaView = within(view.container);
		expect(ctaView.getByText(/example 12-month model snapshot/i)).toBeTruthy();
		expect(ctaView.getByText(/projected annual spend/i)).toBeTruthy();
		expect(ctaView.getAllByText(/controllable waste opportunity/i).length).toBeGreaterThan(0);
		await fireEvent.click(ctaView.getByRole('link', { name: /open full roi planner/i }));
		expect(onTrackCta).toHaveBeenCalledTimes(1);
	});

	it('renders global trust compliance badges and regional resilience signals', async () => {
		const onTrackCta = vi.fn();
		const view = render(LandingTrustSection, {
			props: {
				requestValidationBriefingHref: '/auth/login?intent=executive_briefing',
				onePagerHref: '/resources/valdrics-enterprise-one-pager.md',
				globalComplianceWorkbookHref: '/resources/global-finops-compliance-workbook.md',
				onTrackCta
			}
		});

		// Check for specific global compliance badges (ISO 27001 and DORA)
		expect(view.getAllByText(/ISO 27001 readiness alignment/i).length).toBeGreaterThan(0);
		expect(view.getAllByText(/DORA operational resilience/i).length).toBeGreaterThan(0);

		// Check for the Global FinOps Compliance Workbook CTA
		const ctaBlock = within(view.container).getByRole('generic', {
			name: 'Security and Readiness'
		});
		expect(ctaBlock).toBeTruthy();
		if (ctaBlock) {
			const ctaView = within(ctaBlock);
			expect(ctaView.getByText(/Access Control & Compliance Checklist/i)).toBeTruthy();
			expect(ctaView.getByText(/need formal review/i)).toBeTruthy();
			await fireEvent.click(
				ctaView.getByRole('link', { name: /Access Control & Compliance Checklist/i })
			);
			expect(onTrackCta).toHaveBeenCalledWith('download_global_compliance_workbook');
		}
	});

	it('renders trust validation and one-pager collateral CTAs', async () => {
		const onTrackCta = vi.fn();
		const view = render(LandingTrustSection, {
			props: {
				requestValidationBriefingHref: '/auth/login?intent=executive_briefing',
				onePagerHref: '/resources/valdrics-enterprise-one-pager.md',
				globalComplianceWorkbookHref: '/resources/global-finops-compliance-workbook.md',
				onTrackCta
			}
		});

		const ctaBlock = within(view.container).getByRole('generic', {
			name: 'Security and Readiness'
		});
		expect(ctaBlock).toBeTruthy();
		if (ctaBlock) {
			const ctaView = within(ctaBlock);
			await fireEvent.click(ctaView.getByRole('link', { name: /^talk to sales$/i }));
			expect(onTrackCta).toHaveBeenCalledWith('request_validation_briefing');

			await fireEvent.click(
				ctaView.getByRole('link', { name: /download executive one-pager/i })
			);
			expect(onTrackCta).toHaveBeenCalledWith('download_executive_one_pager');
		}
	});

	it('rotates customer comments with navigation controls', async () => {
		const trust = render(LandingTrustSection, {
			props: {
				requestValidationBriefingHref: '/auth/login?intent=executive_briefing',
				onePagerHref: '/resources/valdrics-enterprise-one-pager.md',
				globalComplianceWorkbookHref: '/resources/global-finops-compliance-workbook.md',
				onTrackCta: vi.fn()
			}
		});
		const trustView = within(trust.container);

		expect(
			trustView.getByText(/we stopped debating whose queue a cost issue belongs to/i)
		).toBeTruthy();
		await fireEvent.click(trustView.getByRole('button', { name: /next comment/i }));
		expect(
			trustView.getByText(
				/the value is not another dashboard\. it is moving from signal to controlled action/i
			)
		).toBeTruthy();
		expect(trustView.queryByText(/current proof reflects design-partner feedback/i)).toBeNull();
		await fireEvent.click(trustView.getByRole('button', { name: /show comment 3/i }));
		expect(trustView.getByText(/leadership reviews got shorter/i)).toBeTruthy();
	});

	it('refreshes customer comments periodically from the feed', async () => {
		vi.useFakeTimers();
		const fetchMock = vi
			.spyOn(globalThis, 'fetch')
			.mockResolvedValueOnce(
				new Response(
					JSON.stringify({
						items: [
							{
								quote: 'Initial streamed quote for trust section.',
								attribution: 'First source'
							}
						]
					}),
					{ status: 200, headers: { 'content-type': 'application/json' } }
				)
			)
			.mockResolvedValueOnce(
				new Response(
					JSON.stringify({
						items: [
							{
								quote: 'Updated streamed quote after polling refresh.',
								attribution: 'Second source'
							}
						]
					}),
					{ status: 200, headers: { 'content-type': 'application/json' } }
				)
			);

		try {
			const trust = render(LandingTrustSection, {
				props: {
					requestValidationBriefingHref: '/auth/login?intent=executive_briefing',
					onePagerHref: '/resources/valdrics-enterprise-one-pager.md',
					globalComplianceWorkbookHref: '/resources/global-finops-compliance-workbook.md',
					onTrackCta: vi.fn()
				}
			});
			const trustView = within(trust.container);

			expect(await trustView.findByText(/initial streamed quote for trust section/i)).toBeTruthy();
			await vi.advanceTimersByTimeAsync(20_500);
			expect(
				await trustView.findByText(/updated streamed quote after polling refresh/i)
			).toBeTruthy();
			expect(fetchMock).toHaveBeenCalledTimes(2);
		} finally {
			fetchMock.mockRestore();
			vi.useRealTimers();
		}
	});

	it('keeps fallback trust quotes when the customer comments feed is unavailable', async () => {
		const fetchMock = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network down'));

		try {
			const trust = render(LandingTrustSection, {
				props: {
					requestValidationBriefingHref: '/auth/login?intent=executive_briefing',
					onePagerHref: '/resources/valdrics-enterprise-one-pager.md',
					globalComplianceWorkbookHref: '/resources/global-finops-compliance-workbook.md',
					onTrackCta: vi.fn()
				}
			});
			const trustView = within(trust.container);

			expect(
				trustView.getByText(/we stopped debating whose queue a cost issue belongs to/i)
			).toBeTruthy();
			await fireEvent.click(trustView.getByRole('button', { name: /next comment/i }));
			expect(
				trustView.getByText(
					/the value is not another dashboard\. it is moving from signal to controlled action/i
				)
			).toBeTruthy();
			expect(fetchMock).toHaveBeenCalled();
		} finally {
			fetchMock.mockRestore();
		}
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
				formatUsd: (amount: number, currency: string = 'USD') => {
					if (currency === 'EUR') return `€${amount}`;
					if (currency === 'GBP') return `£${amount}`;
					return `$${amount}`;
				},
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
		await fireEvent.input(screen.getByLabelText(/expected reduction/i), {
			target: { value: '13' }
		});
		await fireEvent.input(screen.getByLabelText(/rollout duration/i), { target: { value: '35' } });
		await fireEvent.input(screen.getByLabelText(/team members/i), { target: { value: '3' } });
		await fireEvent.input(screen.getByLabelText(/blended hourly rate/i), {
			target: { value: '150' }
		});

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
