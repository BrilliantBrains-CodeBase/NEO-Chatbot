import { test, expect, type Page } from '@playwright/test';
import type { ChatRequest, ChatResponse } from '../core/types';
import { handle } from '../mock/engine';

// Piece 4: the typing bar.
const sent: ChatRequest[] = [];

async function open(page: Page, reply: (req: ChatRequest) => ChatResponse = handle) {
  sent.length = 0;
  await page.route('**/v1/chat/message', async (route) => {
    const req = route.request().postDataJSON() as ChatRequest;
    sent.push(req);
    await route.fulfill({ json: reply(req) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-NFHT .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await expect(panel.locator('.nb-msg.bot:not(.nb-typing)')).toHaveCount(1);
  return panel;
}

test('4a: typed text shows as a patient bubble, is sent as event text, and gets a reply', async ({
  page,
}) => {
  const panel = await open(page);
  // Found by class: its label follows the placeholder, which changes after the reply.
  const input = panel.locator('.nb-in');
  await expect(input).toHaveAccessibleName('Type your question');
  const send = panel.getByRole('button', { name: 'Send' });

  await expect(send).toBeDisabled();
  await input.fill('   ');
  await expect(send).toBeDisabled(); // spaces only

  await input.fill('  Do you have parking?  ');
  await input.press('Enter');
  await expect(panel.locator('.nb-msg.me')).toHaveText(['Do you have parking?']);
  await expect(input).toHaveValue('');
  // No answer for it: the bot says so and offers a call back (piece 8c).
  await expect(panel.locator('.nb-msg.bot:not(.nb-typing)').last()).toContainText(
    "I don't have a confirmed answer for that yet.",
  );
  expect(sent[1].event).toBe('text');
  expect(sent[1].payload).toEqual({ text: 'Do you have parking?' });
});

test('4a: input text is 16px on mobile (no iPhone zoom) and 14px on desktop', async ({ page }, info) => {
  const panel = await open(page);
  const input = panel.getByRole('textbox', { name: 'Type your question' });
  await expect(input).toHaveCSS('font-size', info.project.name === 'desktop' ? '14px' : '16px');
});

test('4a: placeholder follows the backend reply', async ({ page }) => {
  const panel = await open(page, (req) => ({
    ...handle(req),
    input: { mode: 'text', placeholder: req.event === 'text' ? 'Your full name' : 'Type your question' },
  }));
  await panel.getByRole('textbox', { name: 'Type your question' }).fill('Book');
  await panel.getByRole('button', { name: 'Send' }).click();
  await expect(panel.getByRole('textbox', { name: 'Your full name' })).toBeVisible();
});

// A reply that asks for a phone number, then an email, like the booking steps.
const steps = (req: ChatRequest): ChatResponse => {
  if (req.event !== 'text') return handle(req);
  return req.payload.cc
    ? {
        messages: [{ type: 'text', text: 'What is your email address?' }],
        input: { mode: 'email', placeholder: 'name@example.com' },
      }
    : {
        messages: [{ type: 'text', text: 'What is your contact number?' }],
        input: { mode: 'phone', placeholder: 'Mobile number' },
      };
};

test('4b: phone mode shows the country code (IN +91 default), sends it with the number', async ({ page }) => {
  const panel = await open(page, steps);
  await panel.getByRole('textbox', { name: 'Type your question' }).fill('Priya Sharma');
  await panel.getByRole('button', { name: 'Send' }).click();

  const cc = panel.getByRole('combobox', { name: 'Country code' });
  await expect(cc).toBeVisible();
  await expect(cc.locator('option:checked')).toHaveText('IN +91');
  await expect(cc.locator('option')).toHaveCount(15);
  const phone = panel.locator('input[type="tel"]');
  await expect(phone).toHaveAttribute('placeholder', 'Mobile number');
  await expect(phone).toHaveAttribute('inputmode', 'tel');

  await cc.selectOption({ label: 'AE +971' });
  await phone.fill('501234567');
  await phone.press('Enter');
  await expect(panel.locator('.nb-msg.me').last()).toHaveText('+971 501234567');
  // The bubble shows before the request arrives, so wait for it.
  await expect.poll(() => sent[sent.length - 1].payload).toEqual({ text: '501234567', cc: '+971' });

  // Email step: the selector is gone and the email keyboard is used.
  const email = panel.locator('input[type="email"]');
  await expect(email).toHaveAttribute('placeholder', 'name@example.com');
  await expect(email).toHaveAttribute('autocomplete', 'email');
  await expect(cc).toBeHidden();
  await email.fill('priya@example.com');
  await email.press('Enter');
  // The bubble shows before the request arrives, so wait for it.
  await expect.poll(() => sent[sent.length - 1].payload).toEqual({ text: 'priya@example.com' });
});

test('4a: Enter while the bot is still typing is held and sent when it finishes', async ({ page }) => {
  // A slow reply to the first message, so the second Enter happens while the bot is typing.
  let first = true;
  const panel = await open(page, (req) => handle(req));
  await page.unrouteAll();
  await page.route('**/v1/chat/message', async (route) => {
    const req = route.request().postDataJSON() as ChatRequest;
    sent.push(req);
    if (first) {
      first = false;
      await new Promise((r) => setTimeout(r, 800));
    }
    await route.fulfill({ json: handle(req) });
  });
  const input = panel.locator('.nb-in');
  await input.fill('Do you have parking?');
  await input.press('Enter');
  await expect(panel.locator('.nb-typing')).toBeVisible();
  await input.fill('yes');
  await input.press('Enter'); // bot still typing: held, then sent as the answer to the call back offer
  await expect(panel.locator('.nb-msg.me')).toHaveText(['Do you have parking?', 'yes']);
  await expect(panel.locator('.nb-msg.bot').last()).toHaveText('May I know your full name?');
});
