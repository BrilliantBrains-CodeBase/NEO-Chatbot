import { test, expect } from '@playwright/test';

const CLINICS = [
  { id: 'neo-fertility', cl: 'CL02', bot: 'Navya AI', rose: 'rgb(61, 32, 63)' },
  { id: 'neo-follicle', cl: 'CL01', bot: 'Arya AI', rose: 'rgb(62, 116, 217)' },
  { id: 'derma-solutions', cl: 'CL03', bot: 'Diya AI', rose: 'rgb(72, 30, 11)' },
];

for (const c of CLINICS) {
  test(`${c.id}: loader shows launcher, loads the full widget only on first open`, async ({ page }) => {
    const appRequests: string[] = [];
    page.on('request', (r) => r.url().endsWith('.app.js') && appRequests.push(r.url()));

    await page.goto(`/host.html?clinic=${c.id}`);
    const launcher = page.locator(`#neo-widget-${c.cl} .nb-launch`);
    await expect(launcher).toBeVisible();
    await expect(launcher).toHaveAttribute('aria-expanded', 'false');

    // Clinic colour applies and the site's aggressive CSS does not leak in.
    await expect(launcher.locator('.orb')).toHaveCSS('background-color', c.rose);
    expect(appRequests).toHaveLength(0);

    await launcher.click();
    const panel = page.getByRole('dialog', { name: `${c.bot} chat` });
    await expect(panel).toBeVisible();
    expect(appRequests).toEqual([expect.stringContaining(`/${c.id}.app.js`)]);
    await expect(launcher).toHaveAttribute('aria-expanded', 'true');

    // Desktop: launcher toggles the panel closed again. Mobile hides the launcher while open, so close from the panel.
    if (await launcher.isVisible()) {
      await launcher.click();
    } else {
      await panel.getByRole('button', { name: 'Close chat' }).click();
    }
    await expect(panel).toBeHidden();
    await expect(launcher).toBeVisible();
    await expect(launcher).toHaveAttribute('aria-expanded', 'false');
  });
}

test('visitor and session ids are stored, no personal data', async ({ page }) => {
  await page.goto('/host.html');
  await page.locator('#neo-widget-CL02 .nb-launch').click();
  await expect(page.getByRole('dialog')).toBeVisible();
  const stored = await page.evaluate(() => ({ ...localStorage }));
  expect(stored.neo_vid).toMatch(/^v_[0-9a-f]{32}$/);
  expect(JSON.parse(stored.neo_sid_CL02).id).toMatch(/^s_[0-9a-f]{32}$/);
  expect(Object.keys(stored).sort()).toEqual(['neo_sid_CL02', 'neo_vid']);
});
