import { test, expect } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { handle } from '../mock/engine';

// Piece 3a: messages. The built widget calls /v1/chat/message; the mock backend answers it here.
const sent: ChatRequest[] = [];

test.beforeEach(async ({ page }) => {
  sent.length = 0;
  await page.route('**/v1/chat/message', async (route) => {
    const req = route.request().postDataJSON() as ChatRequest;
    sent.push(req);
    await new Promise((r) => setTimeout(r, 300)); // long enough to see the typing dots
    await route.fulfill({ json: handle(req) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
});

test('first open shows typing dots, then the greeting; the request is the JSON contract', async ({
  page,
}) => {
  await page.locator('#neo-widget-CL01 .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await expect(panel.locator('.nb-typing')).toBeVisible();
  const bot = panel.locator('.nb-msg.bot:not(.nb-typing)');
  await expect(bot).toHaveText(["Hi, I'm Arya, Neo Follicle's AI assistant. How can I help you today?"]);
  await expect(panel.locator('.nb-typing')).toBeHidden();

  expect(sent).toHaveLength(1);
  const req = sent[0];
  expect(req.client_id).toBe('CL01');
  expect(req.event).toBe('start');
  expect(req.session_id).toMatch(/^s_[0-9a-f]{32}$/);
  expect(req.visitor_id).toMatch(/^v_[0-9a-f]{32}$/);
  expect(req.context.lang).toBe('en');
  expect(['mobile', 'desktop']).toContain(req.context.device);
  expect(req.context.page_url).toContain('/host.html');
});

test('closing and reopening keeps the conversation and does not start again', async ({ page }) => {
  const launcher = page.locator('#neo-widget-CL01 .nb-launch');
  await launcher.click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await expect(panel.locator('.nb-msg.bot:not(.nb-typing)')).toHaveCount(1);

  await panel.getByRole('button', { name: 'Close chat' }).click();
  await expect(panel).toBeHidden();
  await launcher.click();
  await expect(panel.locator('.nb-msg.bot:not(.nb-typing)')).toHaveCount(1);
  expect(sent).toHaveLength(1);
});

test('a web address in bot text is a link that opens in a new tab; text around it stays plain', async ({
  page,
}) => {
  await page.unroute('**/v1/chat/message');
  await page.route('**/v1/chat/message', (route) =>
    route.fulfill({
      json: {
        messages: [
          { type: 'text', text: '**Address**\nMap: https://maps.app.goo.gl/jKaWhcfQuKZXRvE48. See you!' },
        ],
        ui: { type: 'chips', options: [], main: true },
        input: { mode: 'text', placeholder: 'Type your question' },
      },
    }),
  );
  await page.locator('#neo-widget-CL01 .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  const link = panel.locator('.nb-msg.bot a.nb-link');
  await expect(link).toHaveText('https://maps.app.goo.gl/jKaWhcfQuKZXRvE48');
  await expect(link).toHaveAttribute('href', 'https://maps.app.goo.gl/jKaWhcfQuKZXRvE48');
  await expect(link).toHaveAttribute('target', '_blank');
  await expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  await expect(panel.locator('.nb-msg.bot')).toContainText('. See you!');
  await expect(panel.locator('.nb-menu')).toHaveCount(0); // under an answer: only the Main menu link
  await expect(panel.getByRole('button', { name: 'Main menu' })).toBeVisible();
});
