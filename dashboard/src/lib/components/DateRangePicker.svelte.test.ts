import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/svelte';
import DateRangePicker from './DateRangePicker.svelte';

describe('DateRangePicker Component', () => {
	afterEach(() => {
		cleanup();
	});

	it('mounts with default preset', () => {
		render(DateRangePicker, { value: '30d' });
		const activeBtn = screen.getByText('30 Days');
		expect(activeBtn).toBeTruthy();
		expect(activeBtn.className).toContain('active');
	});

	it('changes selection when clicking another preset', async () => {
		render(DateRangePicker, { value: '30d' });
		const sevenDaysBtn = screen.getByText('7 Days');
		await fireEvent.click(sevenDaysBtn);

		// Wait for Svelte 5 reactivity if necessary, though fireEvent should trigger it.
		expect(sevenDaysBtn.className).toContain('active');
	});

	it('toggles custom date range picker', async () => {
		render(DateRangePicker, { value: '30d' });
		const customBtn = screen.getByText(/Custom/);
		await fireEvent.click(customBtn);

		expect(screen.getByLabelText('From')).toBeTruthy();
		expect(screen.getByLabelText('To')).toBeTruthy();
	});
});
