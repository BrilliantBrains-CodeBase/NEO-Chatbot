import { test, expect } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { handle } from '../mock/engine';
import { settled } from './helpers';

// Piece 5b: chips, link chips, Back and Main menu.
const sent: ChatRequest[] = [];

test.beforeEach(async ({ page }) => {
  sent.length = 0;
  await page.route('**/v1/chat/message', async (route) => {
    const req = route.request().postDataJSON() as ChatRequest;
    sent.push(req);
    await route.fulfill({ json: handle(req) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-CL01 .nb-launch').click();
});

test('Book Consultation shows 4 pills and Main menu; a tapped pill turns solid and sends its action', async ({
  page,
}, info) => {
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await panel.getByRole('button', { name: 'Book Consultation' }).click();
  const chips = panel.locator('.nb-chips .nb-chip');
  await expect(chips).toHaveText([
    'Book appointment (in-clinic)',
    'Online consultation',
    'Cancel appointment',
    'Reschedule appointment',
  ]);
  await settled(panel);
  const height = (await chips.first().boundingBox())!.height;
  expect(Math.round(height)).toBeGreaterThanOrEqual(info.project.name === 'desktop' ? 40 : 44);
  await expect(panel.locator('.nb-chips .nb-ghost')).toHaveText(['Main menu']);

  const online = chips.nth(1);
  await online.click();
  await expect(online).toHaveClass(/\bsel\b/);
  await expect(online).toHaveCSS('background-color', 'rgb(62, 116, 217)');
  await expect.poll(() => sent.length).toBe(3);
  expect(sent[2].payload).toEqual({ action: 'start', value: 'online' });
  await expect(panel.locator('.nb-msg.me').last()).toHaveText('Online consultation');
});

test('Main menu link sends action menu and shows the menu again', async ({ page }) => {
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await panel.getByRole('button', { name: 'Book Consultation' }).click();
  await panel.locator('.nb-ghost', { hasText: 'Main menu' }).click();
  await expect(panel.locator('.nb-msg.me').last()).toHaveText('Main menu');
  await expect(panel.locator('.nb-menu')).toHaveCount(2);
  expect(sent[sent.length - 1].payload).toEqual({ action: 'menu' });
});

test('Emergency: bold 108, Call 108 is a filled phone link, clinic number link', async ({ page }) => {
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await panel.getByRole('button', { name: 'Emergency' }).click();
  await expect(panel.locator('.nb-msg.bot b', { hasText: '108' })).toBeVisible();
  const call108 = panel.getByRole('link', { name: 'Call 108' });
  await expect(call108).toHaveAttribute('href', 'tel:108');
  await expect(call108).toHaveClass(/\bsel\b/);
  await expect(call108).not.toHaveAttribute('target', '_blank');
  await expect(panel.getByRole('link', { name: 'Call +91 97312 07940' })).toHaveAttribute(
    'href',
    'tel:+919731207940',
  );
});
