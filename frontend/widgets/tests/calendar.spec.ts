import { test, expect, type Page } from '@playwright/test';
import type { CalendarBlock, ChatRequest } from '../core/types';

// Piece 6a: month calendar. Fixed dates: today is Wednesday 21 Oct 2026; Arya is closed on Tuesdays.
const sent: ChatRequest[] = [];

async function open(page: Page, block: Omit<CalendarBlock, 'type' | 'action' | 'closed_weekdays'>) {
  sent.length = 0;
  await page.route('**/v1/chat/message', async (route) => {
    sent.push(route.request().postDataJSON() as ChatRequest);
    await route.fulfill({
      json: {
        messages: [{ type: 'text', text: 'Which date works for you?' }],
        ui: { type: 'month_calendar', action: 'pick_date', closed_weekdays: [2], ...block },
        input: { mode: 'text', placeholder: 'Type your question' },
      },
    });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-NFHT .nb-launch').click();
  const cal = page.getByRole('dialog', { name: 'Arya AI chat' }).locator('.nb-cal').first();
  await expect(cal).toBeVisible();
  return cal;
}

const day = (cal: ReturnType<Page['locator']>, label: string) =>
  cal.getByRole('button', { name: label, exact: true });

test('new booking: past days, Tuesdays and days after the 2-week window are disabled', async ({ page }) => {
  const cal = await open(page, { today: '2026-10-21', min: '2026-10-21', max: '2026-11-04' });
  await expect(cal.locator('.nb-cal-h b')).toHaveText('October 2026');
  await expect(cal.locator('.nb-cal-g i')).toHaveCount(4); // 1 Oct 2026 is a Thursday
  await expect(cal.getByRole('button', { name: 'Previous month' })).toBeDisabled();

  await expect(day(cal, '20 Oct 2026')).toBeDisabled(); // past
  await expect(day(cal, '27 Oct 2026')).toBeDisabled(); // Tuesday
  await expect(day(cal, '21 Oct 2026')).toBeEnabled();
  await expect(day(cal, '21 Oct 2026')).toHaveClass(/\btoday\b/);
  await expect(day(cal, '28 Oct 2026')).toBeEnabled();

  await cal.getByRole('button', { name: 'Next month' }).click();
  await expect(cal.locator('.nb-cal-h b')).toHaveText('November 2026');
  await expect(day(cal, '4 Nov 2026')).toBeEnabled(); // last day of the window
  await expect(day(cal, '5 Nov 2026')).toBeDisabled();
  await expect(cal.getByRole('button', { name: 'Next month' })).toBeDisabled();
});

test('picking a day marks it, shows the date as the patient bubble and sends it', async ({ page }) => {
  const cal = await open(page, { today: '2026-10-21', min: '2026-10-21', max: '2026-11-04' });
  await day(cal, '28 Oct 2026').click();
  await expect(day(cal, '28 Oct 2026')).toHaveAttribute('aria-pressed', 'true');
  await expect(day(cal, '28 Oct 2026')).toHaveClass(/\bsel\b/);
  const panel = page.getByRole('dialog');
  await expect(panel.locator('.nb-msg.me')).toHaveText(['28 Oct 2026']);
  await expect.poll(() => sent.length).toBe(2);
  expect(sent[1].payload).toEqual({ action: 'pick_date', value: '2026-10-28' });
});

test('booked-date picker (cancel, reschedule): previous dates up to 2 months back are allowed', async ({
  page,
}) => {
  const cal = await open(page, { today: '2026-10-21', min: '2026-08-22', max: '2026-11-04' });
  await expect(cal.locator('.nb-cal-h b')).toHaveText('October 2026'); // opens on the current month
  await expect(day(cal, '2 Oct 2026')).toBeEnabled();
  await expect(day(cal, '6 Oct 2026')).toBeDisabled(); // still a Tuesday
  await cal.getByRole('button', { name: 'Previous month' }).click();
  await cal.getByRole('button', { name: 'Previous month' }).click();
  await expect(cal.locator('.nb-cal-h b')).toHaveText('August 2026');
  await expect(day(cal, '21 Aug 2026')).toBeDisabled();
  await expect(day(cal, '22 Aug 2026')).toBeEnabled();
  await expect(cal.getByRole('button', { name: 'Previous month' })).toBeDisabled();
});
