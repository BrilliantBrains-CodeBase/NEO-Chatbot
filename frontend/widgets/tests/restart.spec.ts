import { test, expect } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { handle } from '../mock/engine';

// Piece 3c: the header restart button.
const GREETING = "Hi, I'm Arya, Neo Follicle's AI assistant. How can I help you today?";

test('restart clears the chat, starts a new session and greets again', async ({ page }) => {
  const sent: ChatRequest[] = [];
  await page.route('**/v1/chat/message', async (route) => {
    const req = route.request().postDataJSON() as ChatRequest;
    sent.push(req);
    await route.fulfill({ json: handle(req) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-NFHT .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  const bot = panel.locator('.nb-msg.bot:not(.nb-typing)');
  await expect(bot).toHaveText([GREETING]);

  await panel.getByRole('button', { name: 'Restart chat' }).click();
  await expect(bot).toHaveText([GREETING]); // one greeting, not two
  expect(sent.map((r) => r.event)).toEqual(['start', 'restart']);
  expect(sent[1].session_id).toMatch(/^s_[0-9a-f]{32}$/);
  expect(sent[1].session_id).not.toBe(sent[0].session_id);
  const stored = await page.evaluate(() => localStorage.getItem('neo_sid_NFHT'));
  expect(JSON.parse(stored!).id).toBe(sent[1].session_id);
});

test('a reply that arrives after restart is dropped', async ({ page }) => {
  let first = true;
  await page.route('**/v1/chat/message', async (route) => {
    const req = route.request().postDataJSON() as ChatRequest;
    if (first) {
      first = false;
      await new Promise((r) => setTimeout(r, 1500)); // slow reply for the old conversation
      return route.fulfill({ json: { ...handle(req), messages: [{ type: 'text', text: 'OLD REPLY' }] } });
    }
    await route.fulfill({ json: handle(req) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-NFHT .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await panel.getByRole('button', { name: 'Restart chat' }).click();

  const bot = panel.locator('.nb-msg.bot:not(.nb-typing)');
  await expect(bot).toHaveText([GREETING]);
  await page.waitForTimeout(1800); // the old reply has now arrived
  await expect(bot).toHaveText([GREETING]);
});
