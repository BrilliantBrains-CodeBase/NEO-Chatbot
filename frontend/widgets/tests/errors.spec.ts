import { test, expect } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { handle } from '../mock/engine';

// Piece 3b: what the patient sees when the backend cannot be reached, and "Try again".
const GREETING = "Hi, I'm Arya, Neo Follicle's AI assistant. How can I help you today?";

test('server error: widget retries twice by itself, then shows the message; Try again recovers', async ({
  page,
}) => {
  let calls = 0;
  let healthy = false;
  await page.route('**/v1/chat/message', async (route) => {
    calls++;
    if (!healthy) return route.fulfill({ status: 500, json: { detail: 'boom' } });
    return route.fulfill({ json: handle(route.request().postDataJSON() as ChatRequest) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-NFHT .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });

  const error = panel.locator('.nb-msg.bot', { hasText: 'Something went wrong. Please try again.' });
  await expect(error).toBeVisible();
  expect(calls).toBe(3); // first try plus two automatic retries

  healthy = true;
  await error.getByRole('button', { name: 'Try again' }).click();
  await expect(panel.locator('.nb-msg.bot:not(.nb-typing)')).toHaveText([GREETING]);
  expect(calls).toBe(4);
});

test('connection lost: shows the offline message with Try again', async ({ page }) => {
  await page.route('**/v1/chat/message', (route) => route.abort('internetdisconnected'));
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-NFHT .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  const error = panel.locator('.nb-msg.bot', {
    hasText: 'You seem to be offline. Please check your connection and try again.',
  });
  await expect(error).toBeVisible();
  await expect(error.getByRole('button', { name: 'Try again' })).toBeEnabled();
});
