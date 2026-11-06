import { test, expect } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { handle } from '../mock/engine';

// Piece 7: Arya About Doctors and Dr. Sandeep's card.
const sent: ChatRequest[] = [];

test.beforeEach(async ({ page }) => {
  sent.length = 0;
  await page.route('**/v1/chat/message', async (route) => {
    const req = route.request().postDataJSON() as ChatRequest;
    sent.push(req);
    await route.fulfill({ json: handle(req) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-NFHT .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await panel.getByRole('button', { name: 'About Doctors' }).click();
  await panel.getByRole('button', { name: 'Dr. Sandeep Mahapatra' }).click();
});

test('card shows name, role, qualifications and 6 stats in 3 columns', async ({ page }) => {
  const card = page.getByRole('dialog').locator('.nb-doc');
  await expect(card).toContainText('Dr. Sandeep Mahapatra');
  await expect(card).toContainText('Founder and Director, Neo Follicle');
  await expect(card.locator('.nb-q')).toHaveText(
    'MBBS, MD (Dermatology), ISHRS Gold Member, Certified DHI Specialist',
  );
  await expect(card.locator('.nb-stats b')).toHaveText([
    '20+',
    '10,000+',
    '60 lakh+',
    '500+',
    '1 lakh+',
    'Gold',
  ]);
  await expect(card.locator('.nb-stats span')).toHaveText([
    'Years experience',
    'Transplants',
    'Follicles placed',
    'International patients',
    'PRP sessions',
    'Medalist, MD',
  ]);
  await expect(card.locator('.nb-stats b').first()).toHaveCSS('color', 'rgb(62, 116, 217)'); // clinic blue
  await expect(card.locator('.nb-stats')).toHaveCSS('grid-template-columns', /^(\S+ ){2}\S+$/); // 3 columns
});

test('buttons: Book is filled and sends start book; profile and videos open the website', async ({
  page,
}) => {
  const panel = page.getByRole('dialog');
  const book = panel.getByRole('button', { name: 'Book with Dr. Sandeep' });
  await expect(book).toHaveClass(/\bsel\b/);
  await expect(panel.getByRole('link', { name: 'Read full profile' })).toHaveAttribute(
    'href',
    'https://neofollicletransplant.com/dr-sandeep-mahapatra-hair-transplant-surgeon/',
  );
  await expect(panel.getByRole('link', { name: 'Patient videos' })).toHaveAttribute(
    'href',
    'https://neofollicletransplant.com/video-gallery/',
  );
  await book.click();
  await expect.poll(() => sent.length).toBe(4);
  expect(sent[3].payload).toEqual({ action: 'start', value: 'book' });
});

test('Back returns to the doctor list', async ({ page }) => {
  const panel = page.getByRole('dialog');
  await panel.locator('.nb-ghost', { hasText: 'Back' }).click();
  await expect.poll(() => sent.length).toBe(4);
  expect(sent[3].payload).toEqual({ action: 'go', value: 'about' });
  await expect(panel.locator('.nb-msg.bot').last()).toHaveText('Which doctor would you like to know about?');
});
