import { test, expect, type Locator, type Page } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { clock, handle } from '../mock/engine';

// Piece 8b: Arya cancel and reschedule, word for word from frontend.md.
// India time 09:00 on Wednesday 21 Oct 2026.
async function open(page: Page) {
  clock.now = () => new Date('2026-10-21T03:30:00Z');
  await page.route('**/v1/chat/message', async (route) => {
    await route.fulfill({ json: handle(route.request().postDataJSON() as ChatRequest) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-NFHT .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await expect(panel.locator('.nb-menu')).toBeVisible();
  return panel;
}

const bot = (panel: Locator) => panel.locator('.nb-msg.bot:not(.nb-typing)').last();
const tap = (panel: Locator, name: string) => panel.getByRole('button', { name, exact: true }).last().click();
const day = (panel: Locator, name: string) =>
  panel.locator('.nb-cal').last().getByRole('button', { name, exact: true });

async function say(panel: Locator, text: string, expected: string) {
  await panel.locator('.nb-in').fill(text);
  await panel.locator('.nb-in').press('Enter');
  await expect(bot(panel)).toHaveText(expected);
}

async function nameAndNumber(panel: Locator, start: string, intro: string) {
  await tap(panel, 'Book Consultation');
  await tap(panel, start);
  await expect(bot(panel)).toHaveText(intro);
  await say(panel, 'Priya Sharma', 'Thanks, Priya. What is your contact number?');
  // No email step for cancel and reschedule.
  await say(panel, '9876543210', 'Which date is your appointment booked for?');
}

test('cancel: booked date can be in the past (up to 2 months back); confirmation message', async ({
  page,
}) => {
  const panel = await open(page);
  await nameAndNumber(
    panel,
    'Cancel appointment',
    'Sure, I can help you cancel your appointment. May I know your full name?',
  );

  await expect(day(panel, '6 Oct 2026')).toBeDisabled(); // Tuesday
  await expect(day(panel, '2 Oct 2026')).toBeEnabled(); // past date allowed here
  await panel.locator('.nb-cal').last().getByRole('button', { name: 'Previous month' }).click();
  await panel.locator('.nb-cal').last().getByRole('button', { name: 'Previous month' }).click();
  await expect(day(panel, '21 Aug 2026')).toBeDisabled(); // more than 2 months back
  await expect(day(panel, '22 Aug 2026')).toBeEnabled();
  await panel.locator('.nb-cal').last().getByRole('button', { name: 'Next month' }).click();
  await panel.locator('.nb-cal').last().getByRole('button', { name: 'Next month' }).click();

  await day(panel, '2 Oct 2026').click();
  await expect(bot(panel)).toHaveText(
    'Thanks, Priya. Your request to cancel the appointment on 2 Oct 2026 is received. Our team will contact you on +91 9876543210 to confirm the cancellation.',
  );
  await expect(panel.locator('.nb-chips').last().locator('.nb-chip')).toHaveText(['Main menu', 'Talk to us']);
});

test('reschedule: booked date, new date (future only), new time, confirmation message', async ({ page }) => {
  const panel = await open(page);
  await nameAndNumber(
    panel,
    'Reschedule appointment',
    'Sure, I can help you reschedule your appointment. May I know your full name?',
  );
  await day(panel, '2 Oct 2026').click();

  await expect(bot(panel)).toHaveText('Which new date would you prefer?');
  await expect(day(panel, '20 Oct 2026')).toBeDisabled(); // new date: no past dates
  await expect(day(panel, '27 Oct 2026')).toBeDisabled(); // Tuesday
  await day(panel, '28 Oct 2026').click();

  await expect(bot(panel)).toHaveText('And what new time would you prefer?');
  await tap(panel, '10:00 AM');
  await expect(bot(panel)).toHaveText(
    'Thanks, Priya. Your request to move your appointment from 2 Oct 2026 to 28 Oct 2026 at 10:00 AM is received. Our team will contact you on +91 9876543210 to confirm the new slot.',
  );
  await expect(panel.locator('.nb-chips').last().locator('.nb-chip')).toHaveText(['Main menu', 'Talk to us']);
});

test('reschedule: the new date can still be changed while the times show', async ({ page }) => {
  const panel = await open(page);
  await nameAndNumber(
    panel,
    'Reschedule appointment',
    'Sure, I can help you reschedule your appointment. May I know your full name?',
  );
  await day(panel, '2 Oct 2026').click();
  await day(panel, '28 Oct 2026').click();
  await expect(bot(panel)).toHaveText('And what new time would you prefer?');
  await day(panel, '29 Oct 2026').click(); // same calendar, a different day
  await expect(bot(panel)).toHaveText('And what new time would you prefer?');
  await tap(panel, 'Any time');
  await expect(bot(panel)).toContainText('to 29 Oct 2026 (any time) is received');
  // Saved: scrolling up to the calendars and the times never moves the appointment again.
  await expect(day(panel, '30 Oct 2026')).toBeDisabled();
  await expect(panel.locator('.nb-cal.nb-locked')).toHaveCount(2);
  await expect(panel.locator('.nb-times.nb-locked button').first()).toBeDisabled();
});
