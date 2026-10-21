import { test, expect } from '@playwright/test';
import { settled } from './helpers';

// Piece 2: panel layout (header, footer, closing). Runs on desktop and mobile projects.
test.beforeEach(async ({ page }) => {
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-CL01 .nb-launch').click();
  // The full widget loads on first open; wait for it and for the opening animation to finish.
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await expect(panel).toBeVisible();
  await settled(panel);
});

test('header shows avatar, bot name and subtitle; footer shows disclaimer and link', async ({ page }) => {
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await expect(panel.locator('.nb-ava')).toHaveText('N');
  await expect(panel.locator('.nb-title b')).toHaveText('Arya AI');
  await expect(panel.locator('.nb-title span')).toHaveText('Instant Reply Assistant');
  await expect(panel.locator('.nb-legal')).toContainText('AI Generated Responses, Not For Medical Advice');
  const link = panel.getByRole('link', { name: 'Brilliant Brains' });
  await expect(link).toHaveAttribute('href', 'https://brilliantbrains.ai/');
  await expect(link).toHaveAttribute('target', '_blank');
  // Clinic colour on the header despite the host page's aggressive CSS.
  await expect(panel.locator('.nb-head')).toHaveCSS('background-color', 'rgb(62, 116, 217)');
});

test('Escape closes the panel', async ({ page }) => {
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toBeHidden();
});

test('desktop panel is 380 x 580; mobile sheet is full width with a backdrop that closes it', async ({
  page,
}, info) => {
  const panel = page.getByRole('dialog');
  const box = (await panel.boundingBox())!;
  const vp = page.viewportSize()!;
  if (info.project.name === 'desktop') {
    expect(Math.round(box.width)).toBe(380);
    expect(Math.round(box.height)).toBe(580);
    await expect(page.locator('#neo-widget-CL01 .nb-backdrop')).toBeHidden();
  } else {
    expect(Math.round(box.width)).toBe(vp.width);
    expect(Math.round(box.y + box.height)).toBe(vp.height);
    await page.mouse.click(vp.width / 2, 20); // backdrop area above the sheet
    await expect(panel).toBeHidden();
    await expect(page.locator('#neo-widget-CL01 .nb-launch')).toBeVisible();
  }
});
