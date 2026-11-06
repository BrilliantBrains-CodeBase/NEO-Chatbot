import { test, expect, type Page } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { handle } from '../mock/engine';

// Piece 9c: the chat survives a reload for 3 days after the last message.
const GREETING = "Hi, I'm Arya, Neo Follicle's AI assistant. How can I help you today?";
const DAY = 24 * 60 * 60 * 1000;
const sent: ChatRequest[] = [];

async function mock(page: Page) {
  sent.length = 0;
  await page.route('**/v1/chat/message', async (route) => {
    const req = route.request().postDataJSON() as ChatRequest;
    sent.push(req);
    await route.fulfill({ json: handle(req) });
  });
}

async function open(page: Page) {
  await page.locator('#neo-widget-NFHT .nb-launch').click();
  return page.getByRole('dialog', { name: 'Arya AI chat' });
}

// Seeds a saved chat (and optionally a session) before the page loads.
async function seed(page: Page, chatAgeMs: number, sessionAgeMs?: number) {
  await page.addInitScript(
    ([chatAge, sessionAge]) => {
      const entries = [{ id: 0, from: 'me', text: 'OLD QUESTION' }];
      localStorage.setItem('neo_chat_NFHT', JSON.stringify({ t: Date.now() - chatAge, entries }));
      if (sessionAge !== null)
        localStorage.setItem(
          'neo_sid_NFHT',
          JSON.stringify({ id: 's_' + 'a'.repeat(32), t: Date.now() - sessionAge }),
        );
    },
    [chatAgeMs, sessionAgeMs ?? null] as const,
  );
}

test('reload keeps the chat and carries on without greeting again; old buttons still work', async ({
  page,
}) => {
  await mock(page);
  await page.goto('/host.html?clinic=neo-follicle');
  let panel = await open(page);
  await panel.getByRole('button', { name: 'Book Consultation' }).click();
  await expect(panel.getByRole('button', { name: 'Online consultation' })).toBeVisible();

  await page.reload();
  sent.length = 0;
  panel = await open(page);
  await expect(panel.locator('.nb-msg.me')).toHaveText(['Book Consultation']);
  await expect(panel.locator('.nb-msg.bot', { hasText: GREETING })).toHaveCount(1);
  await panel.getByRole('button', { name: 'Online consultation' }).click();
  await expect(panel.locator('.nb-msg.bot').last()).toHaveText(
    "Sure, let's book your online video consultation. May I know your full name?",
  );
  expect(sent.map((r) => r.event)).toEqual(['button']); // no new start
});

test('a chat older than 3 days is dropped', async ({ page }) => {
  await mock(page);
  await seed(page, 3 * DAY + 60_000);
  await page.goto('/host.html?clinic=neo-follicle');
  const panel = await open(page);
  await expect(panel.locator('.nb-msg.bot', { hasText: GREETING })).toBeVisible();
  await expect(panel.getByText('OLD QUESTION')).toHaveCount(0);
});

test('within 3 days but the session expired: old chat shown, then a fresh greeting', async ({ page }) => {
  await mock(page);
  await seed(page, 2 * DAY, 31 * 60 * 1000);
  await page.goto('/host.html?clinic=neo-follicle');
  const panel = await open(page);
  await expect(panel.locator('.nb-msg.me')).toHaveText(['OLD QUESTION']);
  await expect(panel.locator('.nb-msg.bot', { hasText: GREETING })).toBeVisible();
  expect(sent.map((r) => r.event)).toEqual(['start']);
});

test('restart clears the saved chat', async ({ page }) => {
  await mock(page);
  await page.goto('/host.html?clinic=neo-follicle');
  const panel = await open(page);
  await panel.getByRole('button', { name: 'Book Consultation' }).click();
  await expect(panel.locator('.nb-msg.me')).toHaveText(['Book Consultation']);
  await panel.getByRole('button', { name: 'Restart chat' }).click();
  await expect(panel.locator('.nb-msg.me')).toHaveCount(0);
  await expect(panel.locator('.nb-msg.bot', { hasText: GREETING })).toBeVisible();
  // Only the new greeting and menu are kept: no patient messages from before the restart.
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem('neo_chat_NFHT') ?? '{}'));
  expect(saved.entries.filter((e: { from: string }) => e.from === 'me')).toEqual([]);
});
