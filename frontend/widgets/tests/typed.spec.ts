import { test, expect, type Locator, type Page } from '@playwright/test';
import type { ChatRequest } from '../core/types';
import { clock, handle } from '../mock/engine';
import { route } from '../mock/router';

// Piece 8d2: typed questions. Rules first (no browser), then real conversations.
test.describe('rules', () => {
  const cases: [string, ReturnType<typeof route>][] = [
    ['I am bleeding after my procedure', { to: 'emergency' }],
    ['I fainted', { to: 'emergency' }],
    ['Is minoxidil safe for me?', { to: 'lead' }], // medical: never answered
    ['Will PRP be painful?', { to: 'lead' }], // medical beats the treatment name
    ['Can I take tablets for hair fall?', { to: 'lead' }],
    ['How much does it cost?', { to: 'node', key: 'cost' }],
    ['What is the price of a hair transplant?', { to: 'node', key: 'cost' }],
    ['What are your timings?', { to: 'node', key: 'clinic' }],
    ['Where is the clinic?', { to: 'node', key: 'clinic' }],
    ['I want to book an appointment', { to: 'node', key: 'book' }],
    ['Can I do a video call from Dubai?', { to: 'start', kind: 'online' }],
    ['I need to cancel', { to: 'start', kind: 'cancel' }],
    ['Please postpone my visit', { to: 'start', kind: 'reschedule' }],
    ['Show me before and after photos', { to: 'node', key: 'results' }],
    ['Can I talk to someone?', { to: 'node', key: 'talk' }],
    ['Who is the doctor?', { to: 'node', key: 'about' }],
    ['I live abroad', { to: 'node', key: 'intl' }],
    ['Tell me about PRP', { to: 'card', treatment: 'PRP Treatment' }],
    ['What is SMP?', { to: 'card', treatment: 'Scalp Micropigmentation' }],
    ['female hair transplant details', { to: 'card', treatment: 'Female Hair Transplant' }],
    ['what treatments do you have', { to: 'node', key: 'treat' }],
    ['Do you have parking?', { to: 'lead' }], // no answer known
  ];
  for (const [text, expected] of cases) {
    test(`"${text}"`, () => expect(route(text)).toEqual(expected));
  }
});

async function open(page: Page) {
  clock.now = () => new Date('2026-10-21T03:30:00Z'); // 09:00 India time, Wednesday
  await page.route('**/v1/chat/message', async (r) => {
    await r.fulfill({ json: handle(r.request().postDataJSON() as ChatRequest) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-CL01 .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  await expect(panel.locator('.nb-menu')).toBeVisible();
  return panel;
}

const bots = (panel: Locator) => panel.locator('.nb-msg.bot:not(.nb-typing)');
const bot = (panel: Locator) => bots(panel).last();

async function type(panel: Locator, text: string) {
  await panel.locator('.nb-in').fill(text);
  await panel.locator('.nb-in').press('Enter');
}

test('typed "cost" opens the cost guide with hair loss patterns', async ({ page }) => {
  const panel = await open(page);
  await type(panel, 'How much does it cost?');
  await expect(bot(panel)).toHaveText(
    'Hair transplant cost is graft based, Rs 60 to Rs 100 per graft. Which best describes your hair loss?',
  );
  await panel.getByRole('button', { name: 'Receding hairline' }).click();
  await expect(bot(panel)).toHaveText(
    'Typical need: 1,000 to 1,800 grafts.At Rs 60 to Rs 100 per graft, that is about Rs 60,000 to Rs 1,80,000.EMI available, no hidden charges. The final count is confirmed after a scalp evaluation.',
  );
  await expect(panel.locator('.nb-chips').last().locator('.nb-chip')).toHaveText([
    'Get exact quote',
    'Try AI Hair Analysis',
    'Book consultation',
  ]);
});

test('typed emergency words open Emergency', async ({ page }) => {
  const panel = await open(page);
  await type(panel, 'I am bleeding after my procedure');
  await expect(bot(panel)).toContainText('call 108 or go to the nearest hospital');
});

test('medical question is never answered: it becomes a lead', async ({ page }) => {
  const panel = await open(page);
  await type(panel, 'Is minoxidil safe for me?');
  await expect(bots(panel).nth(-2)).toContainText("I don't have a confirmed answer for that yet.");
  await expect(bot(panel)).toHaveText('May I know your full name?');
});

test('mid-booking question at the date step: short answer, then the date is asked again', async ({
  page,
}) => {
  const panel = await open(page);
  await panel.getByRole('button', { name: 'Book Consultation' }).click();
  await panel.getByRole('button', { name: 'Book appointment (in-clinic)' }).click();
  await type(panel, 'Priya Sharma');
  await type(panel, '9876543210');
  await type(panel, 'priya@example.com');
  await panel.getByRole('button', { name: 'Hair Transplant for Men', exact: true }).click();
  await expect(bot(panel)).toHaveText('Which date works for you?');

  await type(panel, 'what is the cost?');
  await expect(bots(panel).nth(-2)).toHaveText(
    'Hair transplant cost is graft based, Rs 60 to Rs 100 per graft. The final count is confirmed after a scalp evaluation.',
  );
  await expect(bot(panel)).toHaveText('Which date works for you?');
  // Nothing entered so far is lost: picking a date continues the same booking.
  await panel.locator('.nb-cal').last().getByRole('button', { name: '23 Oct 2026', exact: true }).click();
  await panel.getByRole('button', { name: '10:00 AM' }).last().click();
  await expect(bot(panel)).toContainText('Priya Sharma');
  await expect(bot(panel)).toContainText('Hair Transplant for Men');
});

test('mid-booking questions at typing steps: answered or noted, the step continues', async ({ page }) => {
  const panel = await open(page);
  await panel.getByRole('button', { name: 'Book Consultation' }).click();
  await panel.getByRole('button', { name: 'Book appointment (in-clinic)' }).click();

  await type(panel, 'where is the clinic?');
  await expect(bots(panel).nth(-2)).toContainText('Scorpio House, near Marathahalli Bridge');
  await expect(bot(panel)).toHaveText('May I know your full name?');
  await type(panel, 'Priya Sharma');
  await type(panel, '9876543210');
  await expect(bot(panel)).toHaveText('What is your email address?');

  await type(panel, 'Is PRP painful?'); // medical: not answered, noted for the team
  await expect(bots(panel).nth(-2)).toHaveText(
    "I don't have a confirmed answer for that yet. I have noted your question for our team.",
  );
  await expect(bot(panel)).toHaveText('What is your email address?');
  await expect(panel.locator('.nb-in')).toHaveAttribute('type', 'email');
});

test('emergency in the middle of a booking takes over', async ({ page }) => {
  const panel = await open(page);
  await panel.getByRole('button', { name: 'Book Consultation' }).click();
  await panel.getByRole('button', { name: 'Book appointment (in-clinic)' }).click();
  await type(panel, 'Priya Sharma');
  await type(panel, 'I fainted');
  await expect(bot(panel)).toContainText('call 108 or go to the nearest hospital');
});
