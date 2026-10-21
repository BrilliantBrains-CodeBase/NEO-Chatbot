import { test, expect, type Page } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { settled } from './helpers';

// Piece 6b: time grid. Arya day: 15-minute slots from 10:00, last slot 18:30.
const SLOTS: string[] = [];
for (let m = 10 * 60; m <= 18 * 60 + 30; m += 15) {
  SLOTS.push(`${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`);
}
const sent: ChatRequest[] = [];

async function open(page: Page, slots = SLOTS, anyTime = true) {
  sent.length = 0;
  await page.route('**/v1/chat/message', async (route) => {
    const req = route.request().postDataJSON() as ChatRequest;
    sent.push(req);
    await route.fulfill({
      json: {
        messages: [{ type: 'text', text: 'What time would you prefer?' }],
        ui:
          sent.length === 1
            ? { type: 'time_grid', action: 'pick_time', slots, first: 4, any_time: anyTime }
            : null,
        input: { mode: 'text', placeholder: 'Type your question' },
      },
    });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-CL01 .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  const grid = panel.locator('.nb-times');
  await expect(grid).toBeVisible();
  return { panel, grid };
}

test('shows the first 4 slots in 12-hour time, then Any time and More times', async ({ page }) => {
  expect(SLOTS).toHaveLength(35);
  const { panel, grid } = await open(page);
  await expect(grid.locator('.nb-chip')).toHaveText([
    '10:00 AM',
    '10:15 AM',
    '10:30 AM',
    '10:45 AM',
    'Any time',
    'More times',
  ]);
  await settled(panel);
  const slot = (await grid.locator('.nb-chip').nth(0).boundingBox())!;
  const any = (await grid.getByRole('button', { name: 'Any time' }).boundingBox())!;
  const more = (await grid.getByRole('button', { name: 'More times' }).boundingBox())!;
  expect(Math.round(any.width)).toBeGreaterThan(Math.round(slot.width * 2)); // spans 2 columns
  expect(Math.round(more.y)).toBe(Math.round(any.y)); // same row
  await expect(grid.getByRole('button', { name: 'More times' })).toHaveCSS('border-top-style', 'dashed');
});

test('More times shows every slot up to 6:30 PM and goes away; Any time stays last', async ({ page }) => {
  const { grid } = await open(page);
  await grid.getByRole('button', { name: 'More times' }).click();
  const chips = grid.locator('.nb-chip');
  await expect(chips).toHaveCount(36); // 35 slots + Any time
  await expect(chips.nth(34)).toHaveText('6:30 PM');
  await expect(chips.last()).toHaveText('Any time');
  await expect(grid.getByRole('button', { name: 'More times' })).toHaveCount(0);
  expect(sent).toHaveLength(1); // expanding sends nothing
});

test('picking a time marks it, shows it as the patient bubble and sends HH:MM', async ({ page }) => {
  const { panel, grid } = await open(page);
  const slot = grid.getByRole('button', { name: '10:30 AM' });
  await slot.click();
  await expect(slot).toHaveClass(/\bsel\b/);
  await expect(panel.locator('.nb-msg.me')).toHaveText(['10:30 AM']);
  await expect.poll(() => sent.length).toBe(2);
  expect(sent[1].payload).toEqual({ action: 'pick_time', value: '10:30' });

  await grid.getByRole('button', { name: 'Any time' }).click();
  await expect(panel.locator('.nb-msg.me').last()).toHaveText('Any time');
  await expect.poll(() => sent.length).toBe(3);
  expect(sent[2].payload).toEqual({ action: 'pick_time', value: 'any' });
});

test('few slots left today: no More times button', async ({ page }) => {
  const { grid } = await open(page, ['17:45', '18:00', '18:15'], true);
  await expect(grid.locator('.nb-chip')).toHaveText(['5:45 PM', '6:00 PM', '6:15 PM', 'Any time']);
});
