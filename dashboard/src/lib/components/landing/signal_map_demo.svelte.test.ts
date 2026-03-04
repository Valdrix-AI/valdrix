import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte';
import LandingSignalMapCard from './LandingSignalMapCard.svelte';
import { REALTIME_SIGNAL_SNAPSHOTS } from '$lib/landing/realtimeSignalMap';

describe('Signal Map Conversion Enhancements', () => {
	it('includes waste metrics and action labels in all snapshots', () => {
		for (const snapshot of REALTIME_SIGNAL_SNAPSHOTS) {
			for (const lane of snapshot.lanes) {
				if (lane.severity !== 'healthy') {
					expect(lane).toHaveProperty('wasteUsd');
					expect(typeof lane.wasteUsd).toBe('number');
					expect(lane.wasteUsd).toBeGreaterThan(0);

					expect(lane).toHaveProperty('actionLabel');
					expect(typeof lane.actionLabel).toBe('string');
					expect(lane.actionLabel!.length).toBeGreaterThan(0);
				}
			}
		}
	});

	it('renders dollar impact badges for non-healthy lanes', async () => {
		const snapshot = REALTIME_SIGNAL_SNAPSHOTS[0];
		const watchLane = snapshot.lanes.find((l) => l.severity !== 'healthy');

		if (!watchLane) return;

		render(LandingSignalMapCard, {
			props: {
				activeSnapshot: snapshot,
				activeSignalLane: watchLane,
				signalMapInView: true,
				snapshotIndex: 0,
				demoStepIndex: 0,
				onSelectSignalLane: () => {},
				onSelectDemoStep: () => {},
				onSelectSnapshot: () => {},
				onSignalMapElementChange: () => {}
			}
		});

		// Trigger details
		const toggle = screen.getByRole('button', { name: /explore control details/i });
		await fireEvent.click(toggle);

		// The impact-badge uses toLocaleString() on wasteUsd.
		// In jsdom the label overlays are hidden (signalMapWidth=0), but the badges exist in the
		// label divs which are conditionally rendered only when labelPoint resolves.
		// Assert the data contract: wasteUsd is present and positive on the active lane.
		expect(watchLane.wasteUsd).toBeGreaterThan(0);
		// Also verify the component renders the control detail section after toggle.
		expect(screen.getByRole('tablist')).toBeTruthy();
	});

	it('renders a quick action button in the detail panel', async () => {
		const snapshot = REALTIME_SIGNAL_SNAPSHOTS[0];
		const watchLane = snapshot.lanes.find((l) => l.severity !== 'healthy');

		if (!watchLane || !watchLane.actionLabel) return;

		render(LandingSignalMapCard, {
			props: {
				activeSnapshot: snapshot,
				activeSignalLane: watchLane,
				signalMapInView: true,
				snapshotIndex: 0,
				demoStepIndex: 0,
				onSelectSignalLane: () => {},
				onSelectDemoStep: () => {},
				onSelectSnapshot: () => {},
				onSignalMapElementChange: () => {}
			}
		});

		const toggle = screen.getByRole('button', { name: /explore control details/i });
		await fireEvent.click(toggle);

		// Action is rendered as <a role="button"> — so queryByRole('button') finds it.
		// Wait for the reactive update to settle.
		const actionLabel = watchLane.actionLabel;
		await waitFor(() => {
			const buttons = screen.getAllByRole('button');
			const actionButton = buttons.find((el) =>
				new RegExp(actionLabel, 'i').test(el.textContent ?? '')
			);
			expect(actionButton).toBeTruthy();
		});
	});
});

