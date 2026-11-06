import { test, expect, type Locator, type Page } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { handle } from '../mock/engine';

// Piece 8c: Call Back and the typed-question lead, word for word from frontend.md and the Arya guide.
async function open(page: Page) {
  await page.route('**/v1/chat/message', async (route) => {
    await route.fulfill({ json: handle(route.request().postDataJSON() as ChatRequest) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-NFHT .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await expect(panel.locator('.nb-menu')).toBeVisible();
  return panel;
}

const bots = (panel: Locator) => panel.locator('.nb-msg.bot:not(.nb-typing)');
const bot = (panel: Locator) => bots(panel).last();

async function say(panel: Locator, text: string, expected: string) {
  await panel.locator('.nb-in').fill(text);
  await panel.locator('.nb-in').press('Enter');
  await expect(bot(panel)).toHaveText(expected);
}

test('Call Back: name, number, reason, confirmation', async ({ page }) => {
  const panel = await open(page);
  await panel.getByRole('button', { name: 'Call Back', exact: true }).click();
  await expect(bot(panel)).toHaveText('Sure, I can arrange a callback. May I know your full name?');
  await say(panel, 'Rahul Verma', 'Thanks, Rahul. What is your contact number?');
  await say(panel, '9123456780', 'What would you like to discuss on the call?');
  await expect(panel.locator('.nb-in')).toHaveAttribute('placeholder', 'Reason for the call');
  await say(panel, 'ok', 'Please add a few more words.');
  await say(
    panel,
    'Want to know the cost',
    'Thanks, Rahul. Our team will call you on +91 9123456780 about Want to know the cost during clinic hours.',
  );
  await expect(panel.locator('.nb-chips').last().locator('.nb-chip')).toHaveText(['Main menu', 'Talk to us']);
  // The flow has ended: the typing bar is back to questions.
  await expect(panel.locator('.nb-in')).toHaveAttribute('placeholder', 'Type your question');
});

test('typed question with no answer: offers a call back, then takes name, number and email', async ({
  page,
}) => {
  const panel = await open(page);
  await panel.locator('.nb-in').fill('Do you have parking near the clinic?');
  await panel.locator('.nb-in').press('Enter');
  await expect(bot(panel)).toHaveText(
    "I don't have a confirmed answer for that yet. Would you like our team to call you back with the right information?",
  );
  await panel.getByRole('button', { name: 'Yes, call me back' }).click();
  await expect(bot(panel)).toHaveText('May I know your full name?');
  await say(panel, 'Priya Sharma', 'Thanks, Priya. What is your contact number?');
  await say(panel, '9876543210', 'What is your email address?');
  await say(panel, 'priya@example.com', 'Thanks, Priya. Our team will contact you on +91 9876543210.');
});

test('international number in a callback keeps its country code', async ({ page }) => {
  const panel = await open(page);
  await panel.getByRole('button', { name: 'Call Back', exact: true }).click();
  // Wait for the question: Enter is ignored while the bot is still typing.
  await expect(bot(panel)).toHaveText('Sure, I can arrange a callback. May I know your full name?');
  await say(panel, 'Omar Khan', 'Thanks, Omar. What is your contact number?');
  await panel.getByRole('combobox', { name: 'Country code' }).selectOption({ label: 'AE +971' });
  await say(panel, '501234567', 'What would you like to discuss on the call?');
  await say(
    panel,
    'Hair transplant from Dubai',
    'Thanks, Omar. Our team will call you on +971 501234567 about Hair transplant from Dubai during clinic hours.',
  );
});
