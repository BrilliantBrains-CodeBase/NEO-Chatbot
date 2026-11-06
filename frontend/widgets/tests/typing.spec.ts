import { test, expect, type Locator } from '@playwright/test';
import type { ChatRequest, ChatResponse } from '../core/types';
import { clock, handle } from '../mock/engine';
import { parseDate, parseTime } from '../mock/typing';

// Typing works like tapping: dates, times, yes, main menu and button labels (with typos).
// India time 09:00 on Wednesday 21 Oct 2026.
const TODAY = '2026-10-21';
let n = 0;

function chat() {
  clock.now = () => new Date('2026-10-21T03:30:00Z');
  const session_id = 's_' + String(++n).padStart(32, '0');
  const base = { client_id: 'NFHT', session_id, visitor_id: 'v_' + '0'.repeat(32), payload: {} };
  const ctx = { page_url: 'https://neofollicletransplant.com/', device: 'desktop', lang: 'en' } as const;
  handle({ ...base, event: 'start', context: ctx } as ChatRequest);
  const text = (t: string, cc?: string): ChatResponse =>
    handle({ ...base, event: 'text', payload: { text: t, cc }, context: ctx } as ChatRequest);
  const say = (r: ChatResponse) => r.messages.map((m) => m.text).join(' | ');
  return { text, say };
}

test.describe('parsing', () => {
  const dates: [string, string | null][] = [
    ['today', '2026-10-21'],
    ['tomorrow', '2026-10-22'],
    ['Friday', '2026-10-23'],
    ['wed', '2026-10-21'],
    ['28 Oct', '2026-10-28'],
    ['28th October', '2026-10-28'],
    ['Oct 28', '2026-10-28'],
    ['28/10', '2026-10-28'],
    ['28-10-2026', '2026-10-28'],
    ['2026-10-28', '2026-10-28'],
    ['2 Jan', '2027-01-02'], // next January, not last
    ['31/2', null], // no such day
    ['hello', null],
  ];
  for (const [text, want] of dates) test(`date "${text}"`, () => expect(parseDate(text, TODAY)).toBe(want));

  const times: [string, string | null][] = [
    ['10:30', '10:30'],
    ['10.30 am', '10:30'],
    ['2 pm', '14:00'],
    ['2:15pm', '14:15'],
    ['14:15', '14:15'],
    ['3', '15:00'], // no am/pm: afternoon (the clinic is closed at 3 AM)
    ['noon', '12:00'],
    ['any time', 'any'],
    ['25:00', null],
    ['13 pm', null],
  ];
  for (const [text, want] of times) test(`time "${text}"`, () => expect(parseTime(text)).toBe(want));
});

test('a whole booking typed, with typos and short labels', () => {
  const { text, say } = chat();
  expect(say(text('Book Consultation'))).toBe('What would you like to do?');
  expect(say(text('in clinic'))).toContain("let's book your appointment");
  text('Priya Sharma');
  expect(say(text('9876543210'))).toBe('Which treatment are you looking for?');
  expect(say(text('hair transplant for man'))).toBe('Which date works for you?'); // one-letter typo
  expect(say(text('Tuesday'))).toContain('That date is not available'); // closed
  expect(say(text('tomorrow'))).toBe('What time would you prefer?');
  expect(say(text('8 pm'))).toContain('That time is not available'); // after the last slot
  const summary = say(text('10:30'));
  expect(summary).toContain('22 Oct 2026 at 10:30 AM');
  expect(summary).toContain('Hair Transplant for Men');
  expect(say(text('change date'))).toBe('Which date works for you?'); // part of "Change date and time"
  text('Friday');
  expect(say(text('any time'))).toContain('23 Oct 2026, any time');
  expect(say(text('yes'))).toBe(
    'Your appointment request for **Hair Transplant for Men** on 23 Oct 2026 (any time) is received.',
  );
});

test('cancel with a typed past date; main menu and back typed', () => {
  const { text, say } = chat();
  text('Book Consultation');
  text('cancel appointment');
  text('Priya Sharma');
  expect(say(text('9876543210'))).toBe('Which date is your appointment booked for?');
  expect(say(text('2 Oct'))).toContain('Your request to cancel the appointment on **2 Oct 2026**');

  expect(say(text('main menu'))).toBe('How can I help you today?');
  text('Explore Treatments');
  text('hair transplant');
  expect(say(text('Back'))).toBe('What would you like to explore?');
});

test('emergency words are never taken as a tap, even at a date step', () => {
  const { text, say } = chat();
  text('Book Consultation');
  text('in clinic');
  text('Priya Sharma');
  text('9876543210');
  text('Beard Transplant');
  expect(say(text('I am bleeding'))).toContain('call **108**');
});

test('in the widget: a booking made by typing only', async ({ page }) => {
  clock.now = () => new Date('2026-10-21T03:30:00Z');
  await page.route('**/v1/chat/message', async (r) => {
    await r.fulfill({ json: handle(r.request().postDataJSON() as ChatRequest) });
  });
  await page.goto('/host.html?clinic=neo-follicle');
  await page.locator('#neo-widget-NFHT .nb-launch').click();
  const panel = page.getByRole('dialog', { name: 'Arya AI chat' });
  const bot = (p: Locator) => p.locator('.nb-msg.bot:not(.nb-typing)').last();
  const type = async (t: string, expected: string | RegExp) => {
    await panel.locator('.nb-in').fill(t);
    await panel.locator('.nb-in').press('Enter');
    await expect(bot(panel)).toHaveText(expected);
  };
  await expect(panel.locator('.nb-menu')).toBeVisible();
  await type('book consultation', 'What would you like to do?');
  await type('online', "Sure, let's book your online video consultation. May I know your full name?");
  await type('Priya Sharma', 'Thanks, Priya. What is your contact number?');
  await type('9876543210', 'What is your email address? We will send the Google Meet link there.');
  await type('priya@example.com', /Is this email correct/);
  await type('yes', 'Which treatment are you looking for?');
  await type('beard transplant', 'Which date works for you?');
  await type('28 Oct', 'What time would you prefer?');
  await type('11 am', /Please check your details/);
  await type('confirm', /Your online consultation request for Beard Transplant on 28 Oct 2026 at 11:00 AM/);
});
