import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import SignalMap from '$lib/components/landing/SignalMap.svelte';
import PersonaSwitcher from '$lib/components/landing/PersonaSwitcher.svelte';
import ValuePropSection from '$lib/components/landing/ValuePropSection.svelte';
import landingContent from '$lib/landing/landingContent.json';

describe('Landing Page Components Hardening', () => {
	const mockSnapshot = {
		id: 'snapshot_a',
		label: 'SNAPSHOT A',
		headline: 'Stable Operations',
		decisionSummary: 'Everything is fine',
		lanes: [
			{ id: 'lane_1', x: 100, y: 100, title: 'Lane 1', status: 'STABLE', severity: 'healthy', detail: 'Detail', metric: '100%' }
		]
	};

	describe('SignalMap', () => {
		it('renders SVG grid and nodes', () => {
			render(SignalMap, { 
				activeSnapshot: mockSnapshot, 
				activeSignalLane: mockSnapshot.lanes[0], 
				signalMapInView: true,
				onLaneSelect: () => {} 
			});
			expect(screen.getByRole('img')).toBeInTheDocument();
			expect(screen.getByText('Valdrics')).toBeInTheDocument();
		});

		it('triggers lane selection on hotspot click', async () => {
			const onSelect = vi.fn();
			render(SignalMap, { 
				activeSnapshot: mockSnapshot, 
				activeSignalLane: null, 
				signalMapInView: true,
				onLaneSelect: onSelect 
			});
			const hotspot = screen.getByLabelText(/Open Lane 1 lane detail/);
			await fireEvent.click(hotspot);
			expect(onSelect).toHaveBeenCalledWith('lane_1');
		});
	});

	describe('PersonaSwitcher', () => {
		const buyerRoles = [
			{ id: 'cto', label: 'CTO', headline: 'CTO Headline', detail: 'Detail', signals: ['Signal 1'] },
			{ id: 'finops', label: 'FinOps', headline: 'FinOps Headline', detail: 'Detail', signals: ['Signal 2'] }
		];

		it('injects content from JSON and switches roles', async () => {
			const onSelect = vi.fn();
			render(PersonaSwitcher, {
				buyerRoles,
				activeRoleIndex: 0,
				content: landingContent.personas,
				onRoleSelect: onSelect
			});

			expect(screen.getByText(landingContent.personas.headline)).toBeInTheDocument();
			expect(screen.getByText('CTO Headline')).toBeInTheDocument();

			const finopsTab = screen.getByRole('tab', { name: 'FinOps' });
			await fireEvent.click(finopsTab);
			expect(onSelect).toHaveBeenCalledWith(1);
		});
	});

	describe('ValuePropSection', () => {
		it('renders all benefit cards from content', () => {
			render(ValuePropSection, { content: landingContent.benefits });
			expect(screen.getByText(landingContent.benefits.headline)).toBeInTheDocument();
			landingContent.benefits.cards.forEach(card => {
				expect(screen.getByText(card.title)).toBeInTheDocument();
			});
		});
	});
});
