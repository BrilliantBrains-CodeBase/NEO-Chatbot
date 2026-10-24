import { test, expect, type Locator, type Page } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { clock, handle } from '../mock/engine';

// Piece 8a: Arya booking flows, word for word from frontend.md.
// India time 09:00 on Wednesday 21 Oct 2026 unless a test sets another time.
const at = (iso: string) => () => new Date(iso);

async function open(page: Page, now = '2026-10-21T03:30:00Z') {
  clock.now = at(now);
  await page.route('**/v1/chat/message', async (route) => {
    await route.fulfill({ json: handle(route.request().postDataJSON() as ChatRequest) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-CL01 .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await expect(panel.locator('.nb-menu')).toBeVisible();
  return panel;
}

const bot = (panel: Locator) => panel.locator('.nb-msg.bot:not(.nb-typing)').last();
const tap = (panel: Locator, name: string) => panel.getByRole('button', { name, exact: true }).last().click();

async function say(panel: Locator, text: string, expected: string) {
  const input = panel.locator('.nb-in');
  await input.fill(text);
  await input.press('Enter');
  await expect(bot(panel)).toHaveText(expected);
}

async function details(panel: Locator, start: string, intro: string) {
  await tap(panel, 'Book Consultation');
  await expect(bot(panel)).toHaveText('What would you like to do?');
  await tap(panel, start);
  await expect(bot(panel)).toHaveText(intro);
  await expect(panel.locator('.nb-in')).toHaveAttribute('placeholder', 'Your full name');
  await say(panel, 'P', 'Please enter your full name.');
  await say(panel, 'Priya Sharma', 'Thanks, Priya. What is your contact number?');
  await expect(panel.getByRole('combobox', { name: 'Country code' })).toBeVisible();
  await say(panel, '12345', 'That number does not look right. Please check and enter it again.');
  if (start !== 'Online consultation') {
    await say(panel, '9876543210', 'Which treatment are you looking for?'); // in-clinic asks no email
    return;
  }
  // Online: the email gets the Google Meet link, so it is checked before going on.
  await say(panel, '9876543210', 'What is your email address? We will send the Google Meet link there.');
  await say(panel, 'priya@', 'Please enter a valid email address.');
  await say(
    panel,
    'priya@example.co',
    'Is this email correct? We will send the live consultation link to priya@example.co.',
  );
  await tap(panel, 'Change email');
  await say(
    panel,
    'priya@example.com',
    'Is this email correct? We will send the live consultation link to priya@example.com.',
  );
  await tap(panel, 'Yes, correct');
  await expect(bot(panel)).toHaveText('Which treatment are you looking for?');
}

test('in-clinic booking from start to confirmation', async ({ page }) => {
  const panel = await open(page);
  await details(
    panel,
    'Book appointment (in-clinic)',
    "Sure, let's book your appointment. May I know your full name?",
  );
  await expect(panel.locator('.nb-chips').last().locator('.nb-chip')).toHaveText([
    'Hair Transplant for Men',
    'Female Hair Transplant',
    'Beard Transplant',
    'Eyebrow Restoration',
    'Failed Hair Transplant Repair',
    'Unshaven & Body Hair Transplant',
    'Non-Surgical Treatment (GFC, PRP, QR678)',
    'Not sure yet',
    'Other',
  ]);

  await tap(panel, 'Hair Transplant for Men');
  await expect(bot(panel)).toHaveText('Which date works for you?');
  const cal = panel.locator('.nb-cal').last();
  await expect(cal.getByRole('button', { name: '21 Oct 2026' })).toBeEnabled(); // today, before opening
  await expect(cal.getByRole('button', { name: '27 Oct 2026' })).toBeDisabled(); // Tuesday
  await cal.getByRole('button', { name: '23 Oct 2026' }).click();

  await expect(bot(panel)).toHaveText('What time would you prefer?');
  await expect(panel.locator('.nb-times').last().locator('.nb-chip').first()).toHaveText('10:00 AM');
  await tap(panel, '10:30 AM');

  await expect(bot(panel)).toHaveText(
    'Please check your details:Priya Sharma+91 9876543210Hair Transplant for MenIn-clinic visit23 Oct 2026 at 10:30 AMBy confirming, you agree to be contacted by phone, WhatsApp or email.',
  );
  await expect(panel.locator('.nb-chips').last().locator('.nb-chip')).toHaveText([
    'Confirm booking',
    'Change treatment',
    'Change date and time',
    'Start again',
  ]);
  await tap(panel, 'Confirm booking');
  await expect(bot(panel)).toHaveText(
    'Your appointment request for Hair Transplant for Men on 23 Oct 2026 at 10:30 AM is received.',
  );
  await expect(panel.locator('.nb-chips').last().locator('.nb-chip')).toHaveText(['Main menu', 'Talk to us']);
});

test('online consultation: Other with a reason, Any time, change treatment, switch to in-clinic', async ({
  page,
}) => {
  const panel = await open(page);
  await details(
    panel,
    'Online consultation',
    "Sure, let's book your online video consultation. May I know your full name?",
  );
  await tap(panel, 'Other');
  await expect(bot(panel)).toHaveText('Please tell us briefly what you are looking for.');
  await say(panel, 'Hi', 'Please add a few more words.');
  await say(panel, 'Hairline correction', 'Which date works for you?');
  await panel.locator('.nb-cal').last().getByRole('button', { name: '24 Oct 2026' }).click();
  await expect(bot(panel)).toHaveText('What time would you prefer?');
  await tap(panel, 'Any time');
  await expect(bot(panel)).toContainText('Hairline correction');
  await expect(bot(panel)).toContainText('Online video consultation (Google Meet)');
  await expect(bot(panel)).toContainText('24 Oct 2026, any time');
  await expect(panel.locator('.nb-chips').last().locator('.nb-chip')).toHaveText([
    'Confirm booking',
    'Change treatment',
    'Change date and time',
    'Switch to in-clinic visit',
    'Start again',
  ]);

  // Change treatment goes straight back to the summary, date and time kept.
  await tap(panel, 'Change treatment');
  await expect(bot(panel)).toHaveText('Which treatment are you looking for?');
  await tap(panel, 'Beard Transplant');
  await expect(bot(panel)).toContainText('Beard Transplant');
  await expect(bot(panel)).toContainText('24 Oct 2026, any time');

  await tap(panel, 'Confirm booking');
  await expect(bot(panel)).toHaveText(
    'Your online consultation request for Beard Transplant on 24 Oct 2026 (any time) is received. You will get the Google Meet link on WhatsApp and email once the clinic confirms.',
  );
});

test('switch to in-clinic and change date and time', async ({ page }) => {
  const panel = await open(page);
  await details(
    panel,
    'Online consultation',
    "Sure, let's book your online video consultation. May I know your full name?",
  );
  await tap(panel, 'Female Hair Transplant');
  await panel.locator('.nb-cal').last().getByRole('button', { name: '22 Oct 2026' }).click();
  await tap(panel, '10:45 AM'); // 4th slot; later ones sit behind More times
  await tap(panel, 'Switch to in-clinic visit');
  await expect(bot(panel)).toContainText('In-clinic visit');
  await tap(panel, 'Change date and time');
  await expect(bot(panel)).toHaveText('Which date works for you?');
  await panel.locator('.nb-cal').last().getByRole('button', { name: '29 Oct 2026' }).click();
  await tap(panel, 'More times');
  await tap(panel, '2:15 PM');
  await expect(bot(panel)).toContainText('29 Oct 2026 at 2:15 PM');
  await tap(panel, 'Confirm booking');
  await expect(bot(panel)).toHaveText(
    'Your appointment request for Female Hair Transplant on 29 Oct 2026 at 2:15 PM is received.',
  );
});

test('today: past times are hidden; after the last slot the calendar starts tomorrow', async ({ page }) => {
  // 11:05 AM India time: the first slot left today is 11:15 AM.
  let panel = await open(page, '2026-10-21T05:35:00Z');
  await details(
    panel,
    'Book appointment (in-clinic)',
    "Sure, let's book your appointment. May I know your full name?",
  );
  await tap(panel, 'Hair Transplant for Men');
  await panel.locator('.nb-cal').last().getByRole('button', { name: '21 Oct 2026' }).click();
  await expect(panel.locator('.nb-times').last().locator('.nb-chip').first()).toHaveText('11:15 AM');

  // 6:40 PM India time: no slot left today, so today is disabled.
  await page.unrouteAll();
  panel = await open(page, '2026-10-21T13:10:00Z');
  await details(
    panel,
    'Book appointment (in-clinic)',
    "Sure, let's book your appointment. May I know your full name?",
  );
  await tap(panel, 'Hair Transplant for Men');
  const cal = panel.locator('.nb-cal').last();
  await expect(cal.getByRole('button', { name: '21 Oct 2026' })).toBeDisabled();
  await expect(cal.getByRole('button', { name: '22 Oct 2026' })).toBeEnabled();
  await cal.getByRole('button', { name: 'Next month' }).click();
  await expect(cal.getByRole('button', { name: '4 Nov 2026', exact: true })).toBeEnabled(); // 14 days ahead
  await expect(cal.getByRole('button', { name: '5 Nov 2026', exact: true })).toBeDisabled();
});
