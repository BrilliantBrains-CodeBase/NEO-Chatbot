import { test, expect, type Page } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { handle } from '../mock/engine';

// Piece 9b: the whole chat works with the keyboard only (Tab, Enter, Escape), with a visible focus ring.

// The focused element inside the widget's Shadow DOM.
const focused = (page: Page) =>
  page.evaluate(() => {
    const el = document.querySelector('#neo-widget-CL01')!.shadowRoot!.activeElement as HTMLElement | null;
    return {
      text: el?.innerText.trim() ?? '',
      label: el?.getAttribute('aria-label') ?? '',
      cls: el?.className ?? '',
      outline: el ? getComputedStyle(el).outlineStyle : '',
    };
  });

async function tabTo(page: Page, match: (f: Awaited<ReturnType<typeof focused>>) => boolean) {
  for (let i = 0; i < 25; i++) {
    await page.keyboard.press('Tab');
    if (match(await focused(page))) return;
  }
  throw new Error('focus never reached the target; last focused: ' + JSON.stringify(await focused(page)));
}

test('keyboard only: open, choose a card and a chip, type, close; focus returns to the launcher', async ({
  page,
}) => {
  test.skip(test.info().project.name !== 'desktop', 'keyboard use is a desktop check');
  await page.route('**/v1/chat/message', async (route) => {
    await route.fulfill({ json: handle(route.request().postDataJSON() as ChatRequest) });
  });
  await page.goto('/host.html?clinic=neo-follicle');

  await tabTo(page, (f) => f.label === 'Open chat');
  await page.keyboard.press('Enter');
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await expect(panel.locator('.nb-menu')).toBeVisible();

  await tabTo(page, (f) => f.text === 'Book Consultation');
  expect((await focused(page)).outline).toBe('solid'); // visible focus ring
  await page.keyboard.press('Enter');
  await expect(panel.locator('.nb-msg.me')).toHaveText(['Book Consultation']);

  await tabTo(page, (f) => f.text === 'Online consultation');
  await page.keyboard.press('Enter');
  await expect(panel.locator('.nb-msg.bot').last()).toHaveText(
    "Sure, let's book your online video consultation. May I know your full name?",
  );

  await tabTo(page, (f) => f.cls.includes('nb-in'));
  await page.keyboard.type('Priya Sharma');
  await page.keyboard.press('Enter');
  await expect(panel.locator('.nb-msg.bot').last()).toHaveText('Thanks, Priya. What is your contact number?');

  await page.keyboard.press('Escape');
  await expect(panel).toBeHidden();
  expect((await focused(page)).label).toBe('Open chat');
});
