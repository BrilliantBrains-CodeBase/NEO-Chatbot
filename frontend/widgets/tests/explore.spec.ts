import { test, expect, type Locator, type Page } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { clock, handle } from '../mock/engine';

// Piece 8d1: Explore Treatments, treatment cards, Not sure, International Patients, Talk to us.
async function open(page: Page) {
  clock.now = () => new Date('2026-10-21T03:30:00Z'); // 09:00 India time, Wednesday
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
const chips = (panel: Locator) => panel.locator('.nb-chips').last().locator('.nb-chip');
const tap = (panel: Locator, name: string) => panel.getByRole('button', { name, exact: true }).last().click();

async function say(panel: Locator, text: string, expected: string) {
  await panel.locator('.nb-in').fill(text);
  await panel.locator('.nb-in').press('Enter');
  await expect(bot(panel)).toHaveText(expected);
}

test('Explore: areas, hair transplant list, treatment card with Read more and Back', async ({ page }) => {
  const panel = await open(page);
  await tap(panel, 'Explore Treatments');
  await expect(bot(panel)).toHaveText('What would you like to explore?');
  await expect(chips(panel)).toHaveText([
    'Hair Transplant',
    'Hair Fall & Scalp Treatments',
    'Beard Transplant',
    'Eyebrow Restoration',
    'Not sure, help me choose',
  ]);

  await tap(panel, 'Hair Transplant');
  await expect(bot(panel)).toHaveText('Pick a hair transplant option.');
  await expect(chips(panel)).toHaveText([
    'Direct Hair Transplant (DHI / FUE)',
    'Hair Transplant for Men',
    'Female Hair Transplant',
    'Failed Hair Transplant Repair',
    'Unshaven Hair Transplant',
    'Body Hair Transplant',
    'Not sure, help me choose',
  ]);

  await tap(panel, 'Hair Transplant for Men');
  await expect(bot(panel)).toHaveText(
    'Hair Transplant for MenFor a receding hairline, frontal baldness and crown thinning, planned around your baldness grade and donor strength.',
  );
  await expect(bot(panel).locator('b')).toHaveText('Hair Transplant for Men');
  await expect(panel.getByRole('link', { name: 'Read more on our website' }).last()).toHaveAttribute(
    'href',
    'https://neofollicletransplant.com/hair-transplant-for-men-in-bangalore/',
  );
  await panel.locator('.nb-chips').last().locator('.nb-ghost', { hasText: 'Back' }).click();
  await expect(bot(panel)).toHaveText('Pick a hair transplant option.');
});

test('Hair fall list has 10 treatments; Book for PRP preselects the booking option', async ({ page }) => {
  const panel = await open(page);
  await tap(panel, 'Explore Treatments');
  await tap(panel, 'Hair Fall & Scalp Treatments');
  await expect(bot(panel)).toHaveText('Pick a treatment to learn more.');
  await expect(chips(panel)).toHaveCount(11); // 10 treatments + Not sure
  await tap(panel, 'PRP Treatment');
  await tap(panel, 'Book for PRP Treatment');

  await expect(bot(panel)).toHaveText("Sure, let's book your appointment. May I know your full name?");
  await say(panel, 'Priya Sharma', 'Thanks, Priya. What is your contact number?');
  // No email step, and the treatment step is skipped.
  await say(panel, '9876543210', 'Which date works for you?');
  await panel.locator('.nb-cal').last().getByRole('button', { name: '23 Oct 2026', exact: true }).click();
  await tap(panel, '10:00 AM');
  await expect(bot(panel)).toContainText('Non-Surgical Treatment (GFC, PRP, QR678)');
});

test('Beard Transplant opens its card directly; Not sure offers 4 next steps', async ({ page }) => {
  const panel = await open(page);
  await tap(panel, 'Explore Treatments');
  await tap(panel, 'Beard Transplant');
  await expect(bot(panel)).toContainText(
    'Fills a patchy beard, moustache, goatee and sideburns, matching natural growth direction.',
  );
  await tap(panel, 'Explore Treatments');
  await tap(panel, 'Not sure, help me choose');
  await expect(bot(panel)).toHaveText(
    'No problem, most patients are not sure at first. The right treatment depends on the cause of your hair loss, which the doctor confirms after a scalp evaluation. You can get a quick estimate from your photos, or let our team guide you.',
  );
  await expect(chips(panel)).toHaveText([
    'Try AI Hair Analysis',
    'Book a consultation',
    'Get a callback',
    'WhatsApp us',
  ]);
  await expect(panel.getByRole('link', { name: 'Try AI Hair Analysis' }).last()).toHaveAttribute(
    'href',
    'https://neofollicletransplant.com/hair-assessment/',
  );

  // Get a callback: the topic is the reason, so no reason step.
  await tap(panel, 'Get a callback');
  await expect(bot(panel)).toHaveText('Sure, I can arrange a callback. May I know your full name?');
  await say(panel, 'Rahul Verma', 'Thanks, Rahul. What is your contact number?');
  await say(
    panel,
    '9123456780',
    'Thanks, Rahul. Our team will call you on +91 9123456780 about Help choosing a treatment during clinic hours.',
  );
});

test('International Patients and Talk to us', async ({ page }) => {
  const panel = await open(page);
  await tap(panel, 'International Patients');
  await expect(bot(panel)).toHaveText(
    'Every international case is planned before you fly. Scalp assessment, graft count and donor mapping are confirmed on a video call first, and the procedure fits in one trip with follow-up after you return home.',
  );
  await expect(chips(panel)).toHaveText(['Plan my treatment', 'Share photos on WhatsApp', 'Read more']);
  await expect(panel.getByRole('link', { name: 'Share photos on WhatsApp' })).toHaveClass(/\bwa\b/);

  await tap(panel, 'Plan my treatment');
  await say(panel, 'Omar Khan', 'Thanks, Omar. What is your contact number?');
  await say(
    panel,
    '9123456780',
    'Thanks, Omar. Our team will call you on +91 9123456780 about International patient during clinic hours.',
  );

  await tap(panel, 'Talk to us');
  await expect(bot(panel)).toHaveText(
    'Choose how you would like to reach us. We are open Wednesday to Monday, 10 AM to 7 PM. Tuesday closed.',
  );
  await expect(chips(panel)).toHaveText(['Call +91 97312 07940', 'WhatsApp us', 'Request a callback']);
});
