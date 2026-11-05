import { test, expect } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { handle } from '../mock/engine';
import { settled } from './helpers';

// Piece 5a: Arya main menu cards.
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

test('greeting above 7 cards in 3 columns; Emergency spans the full row', async ({ page }) => {
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  const tiles = panel.locator('.nb-menu.cards3 .nb-tile');
  await expect(tiles).toHaveText([
    'Book Consultation',
    'Explore Treatments',
    'About Doctors',
    'International Patients',
    'Call Back',
    'WhatsApp',
    'Emergency',
  ]);
  // Greeting first, menu under it.
  const order = await panel
    .locator('.nb-body > *')
    .evaluateAll((els) => els.map((el) => el.className.split(' ')[0]));
  expect(order.slice(0, 2)).toEqual(['nb-msg', 'nb-menu']);

  await settled(panel);
  const first = (await tiles.nth(0).boundingBox())!;
  const third = (await tiles.nth(2).boundingBox())!;
  const fourth = (await tiles.nth(3).boundingBox())!;
  const sos = (await tiles.nth(6).boundingBox())!;
  expect(Math.round(third.y)).toBe(Math.round(first.y)); // 3 per row
  expect(fourth.y).toBeGreaterThan(first.y);
  expect(sos.width).toBeGreaterThan(third.x + third.width - first.x - 2); // full row
  // Same label style on button cards and link cards (WhatsApp).
  for (const i of [0, 5]) {
    await expect(tiles.nth(i)).toHaveCSS('font-size', '11px');
    await expect(tiles.nth(i)).toHaveCSS('font-weight', '600');
  }
  // Alternating fills: odd cards blue, even cards gold.
  await expect(tiles.nth(0)).toHaveCSS('background-image', /241, 245, 253/);
  await expect(tiles.nth(1)).toHaveCSS('background-image', /255, 246, 227/);
});

test('a card sends its action, shows its label as the patient bubble, and stays clickable', async ({
  page,
}) => {
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  const book = panel.getByRole('button', { name: 'Book Consultation' });
  await book.click();
  await expect(panel.locator('.nb-msg.me')).toHaveText(['Book Consultation']);
  await expect.poll(() => sent.length).toBe(2);
  expect(sent[1].event).toBe('button');
  expect(sent[1].payload).toEqual({ action: 'go', value: 'book' });

  await expect(panel.locator('.nb-typing')).toBeHidden();
  await panel.getByRole('button', { name: 'Explore Treatments' }).click();
  await expect(panel.locator('.nb-msg.me')).toHaveText(['Book Consultation', 'Explore Treatments']);
});

test('WhatsApp opens wa.me with the prefilled message in a new tab', async ({ page }) => {
  const wa = page.getByRole('dialog').getByRole('link', { name: 'WhatsApp' });
  await expect(wa).toHaveAttribute(
    'href',
    'https://wa.me/919731207940?text=Hi%2C%20I%20would%20like%20to%20know%20about%20hair%20treatment%20at%20Neo%20Follicle.',
  );
  await expect(wa).toHaveAttribute('target', '_blank');
  await expect(wa).toHaveAttribute('rel', 'noopener noreferrer');
});
