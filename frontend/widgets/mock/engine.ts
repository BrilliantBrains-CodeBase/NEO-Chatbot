// Mock backend: answers like the real FastAPI backend will, using the contract in core/types.ts.
// Used by the dev playground and the Playwright tests only; it is never part of a clinic's widget file.
// The full Arya flows (frontend.md) are added in piece 8.
import type { ChatRequest, ChatResponse, Choice, MenuBlock } from '../core/types';

const GREETING: Record<string, string> = {
  CL01: "Hi, I'm Arya, Neo Follicle's AI assistant. How can I help you today?",
  CL02: "Hi, I'm Navya, Neo Fertility's AI assistant. How can I help you today?",
  CL03: "Hi, I'm Diya, Derma Solutions' AI assistant. How can I help you today?",
};

// Arya main menu (approved mockup and Arya guide): 3-column cards, Emergency across the full row.
const ARYA_WA =
  'https://wa.me/919731207940?text=' +
  encodeURIComponent('Hi, I would like to know about hair treatment at Neo Follicle.');
const MENU: Record<string, MenuBlock> = {
  CL01: {
    type: 'menu',
    layout: 'cards3',
    items: [
      { label: 'Book Consultation', icon: 'cal', action: 'go', value: 'book' },
      { label: 'Explore Treatments', icon: 'search', action: 'go', value: 'treat' },
      { label: 'About Doctors', icon: 'steth', action: 'go', value: 'about' },
      { label: 'International Patients', icon: 'globe', action: 'go', value: 'intl' },
      { label: 'Call Back', icon: 'phone', action: 'start', value: 'callback' },
      { label: 'WhatsApp', icon: 'chat', href: ARYA_WA, variant: 'wa' },
      { label: 'Emergency', icon: 'sos', action: 'go', value: 'emergency', variant: 'sos' },
    ],
  },
};

const TYPE: ChatResponse['input'] = { mode: 'text', placeholder: 'Type your question' };
const ARYA_CALL: Choice = { label: 'Call +91 97312 07940', href: 'tel:+919731207940' };

// Small Arya replies to show the chips; the full flows come in piece 8.
const ARYA_SITE = 'https://neofollicletransplant.com/';

const NODES: Record<string, ChatResponse> = {
  about: {
    messages: [{ type: 'text', text: 'Which doctor would you like to know about?' }],
    ui: {
      type: 'chips',
      main: true,
      options: [{ label: 'Dr. Sandeep Mahapatra', action: 'go', value: 'doc_sandeep' }],
    },
    input: TYPE,
  },
  doc_sandeep: {
    messages: [],
    ui: {
      type: 'doctor_card',
      name: 'Dr. Sandeep Mahapatra',
      title: 'Founder and Director, Neo Follicle',
      quals: 'MBBS, MD (Dermatology), ISHRS Gold Member, Certified DHI Specialist',
      stats: [
        { value: '20+', label: 'Years experience' },
        { value: '10,000+', label: 'Transplants' },
        { value: '60 lakh+', label: 'Follicles placed' },
        { value: '500+', label: 'International patients' },
        { value: '1 lakh+', label: 'PRP sessions' },
        { value: 'Gold', label: 'Medalist, MD' },
      ],
      options: [
        { label: 'Book with Dr. Sandeep', action: 'start', value: 'book', primary: true },
        { label: 'Read full profile', href: ARYA_SITE + 'dr-sandeep-mahapatra-hair-transplant-surgeon/' },
        { label: 'Patient videos', href: ARYA_SITE + 'video-gallery/' },
      ],
      back: { label: 'Back', action: 'go', value: 'about' },
      main: true,
    },
    input: TYPE,
  },
  book: {
    messages: [{ type: 'text', text: 'What would you like to do?' }],
    ui: {
      type: 'chips',
      main: true,
      options: [
        { label: 'Book appointment (in-clinic)', action: 'start', value: 'book' },
        { label: 'Online consultation', action: 'start', value: 'online' },
        { label: 'Cancel appointment', action: 'start', value: 'cancel' },
        { label: 'Reschedule appointment', action: 'start', value: 'reschedule' },
      ],
    },
    input: TYPE,
  },
  emergency: {
    messages: [
      {
        type: 'text',
        text: 'If you have heavy bleeding, severe swelling, fever or signs of infection, or a reaction after a procedure, get help now. For a medical emergency, call **108** or go to the nearest hospital. The clinic is open Wednesday to Monday, 10 AM to 7 PM.',
      },
    ],
    ui: {
      type: 'chips',
      main: true,
      options: [{ label: 'Call 108', href: 'tel:108', primary: true }, ARYA_CALL],
    },
    input: TYPE,
  },
};

const NO_ANSWER =
  "I don't have a confirmed answer for that yet. Share your number and our team will call you back with the right information.";

export function handle(req: ChatRequest): ChatResponse {
  if (req.event === 'button' && req.payload.action === 'go' && req.client_id === 'CL01') {
    const node = NODES[req.payload.value ?? ''];
    if (node) return node;
  }
  if (req.event === 'button' && req.payload.action === 'menu') {
    return {
      messages: [{ type: 'text', text: 'How can I help you today?' }],
      ui: MENU[req.client_id] ?? null,
      input: TYPE,
    };
  }
  if (req.event === 'text' || req.event === 'button') {
    return {
      messages: [{ type: 'text', text: NO_ANSWER }],
      input: { mode: 'text', placeholder: 'Type your question' },
    };
  }
  const greeting = GREETING[req.client_id] ?? 'Hi, how can I help you today?';
  return {
    messages: [{ type: 'text', text: greeting }],
    ui: MENU[req.client_id] ?? null,
    input: { mode: 'text', placeholder: 'Type your question' },
  };
}
