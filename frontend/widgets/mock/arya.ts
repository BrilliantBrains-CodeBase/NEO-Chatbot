// Arya (Neo Follicle, CL01) content for the mock backend. Wording from frontend.md and the approved mockup.
import type { ChatResponse, Choice, MenuBlock } from '../core/types';

export const TYPE: ChatResponse['input'] = { mode: 'text', placeholder: 'Type your question' };

export const ARYA = {
  greeting: "Hi, I'm Arya, Neo Follicle's AI assistant. How can I help you today?",
  // Wednesday to Monday, 10 AM to 7 PM; 15-minute slots, the last one 30 minutes before closing.
  firstSlot: 10 * 60,
  lastSlot: 18 * 60 + 30,
  slotMinutes: 15,
  closedWeekdays: [2], // Tuesday
  bookingWindowDays: 14,
  bookedDateBackDays: 60,
  treatments: [
    'Hair Transplant for Men',
    'Female Hair Transplant',
    'Beard Transplant',
    'Eyebrow Restoration',
    'Failed Hair Transplant Repair',
    'Unshaven & Body Hair Transplant',
    'Non-Surgical Treatment (GFC, PRP, QR678)',
    'Not sure yet',
    'Other',
  ],
};

const SITE = 'https://neofollicletransplant.com/';
const WA =
  'https://wa.me/919731207940?text=' +
  encodeURIComponent('Hi, I would like to know about hair treatment at Neo Follicle.');
const CALL: Choice = { label: 'Call +91 97312 07940', href: 'tel:+919731207940' };

// Main menu (approved mockup): 3-column cards, Emergency across the full row.
export const MENU: MenuBlock = {
  type: 'menu',
  layout: 'cards3',
  items: [
    { label: 'Book Consultation', icon: 'cal', action: 'go', value: 'book' },
    { label: 'Explore Treatments', icon: 'search', action: 'go', value: 'treat' },
    { label: 'About Doctors', icon: 'steth', action: 'go', value: 'about' },
    { label: 'International Patients', icon: 'globe', action: 'go', value: 'intl' },
    { label: 'Call Back', icon: 'phone', action: 'start', value: 'callback' },
    { label: 'WhatsApp', icon: 'chat', href: WA, variant: 'wa' },
    { label: 'Emergency', icon: 'sos', action: 'go', value: 'emergency', variant: 'sos' },
  ],
};

// Fixed replies, opened by { action: 'go', value: <key> }.
export const NODES: Record<string, ChatResponse> = {
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
        { label: 'Read full profile', href: SITE + 'dr-sandeep-mahapatra-hair-transplant-surgeon/' },
        { label: 'Patient videos', href: SITE + 'video-gallery/' },
      ],
      back: { label: 'Back', action: 'go', value: 'about' },
      main: true,
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
      options: [{ label: 'Call 108', href: 'tel:108', primary: true }, CALL],
    },
    input: TYPE,
  },
};
