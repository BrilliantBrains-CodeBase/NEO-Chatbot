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

const MAPS = 'https://maps.app.goo.gl/jKaWhcfQuKZXRvE48';
const HAIR_ANALYSIS: Choice = { label: 'Try AI Hair Analysis', href: SITE + 'hair-assessment/' };
const WHATSAPP_US: Choice = { label: 'WhatsApp us', href: WA, variant: 'wa' };
const OPEN_HOURS = 'Wednesday to Monday, 10 AM to 7 PM. Tuesday closed.';

// Explore Treatments: short answer, website page and the list it belongs to (approved mockup).
export const TREATMENT_INFO: Record<string, { text: string; path: string; list: 'ht' | 'hf' | 'treat' }> = {
  'Direct Hair Transplant (DHI / FUE)': {
    text: 'Follicles are extracted one by one and implanted directly, for a natural hairline and quicker healing.',
    path: 'best-hair-transplant-in-bangalore/',
    list: 'ht',
  },
  'Hair Transplant for Men': {
    text: 'For a receding hairline, frontal baldness and crown thinning, planned around your baldness grade and donor strength.',
    path: 'hair-transplant-for-men-in-bangalore/',
    list: 'ht',
  },
  'Female Hair Transplant': {
    text: 'For thinning, a widening parting and female pattern hair loss, planned only after the cause is diagnosed.',
    path: 'female-hair-transplant-in-bangalore/',
    list: 'ht',
  },
  'Failed Hair Transplant Repair': {
    text: 'Corrects unnatural hairlines, low density, wrong growth direction and scars from an earlier transplant.',
    path: 'failed-hair-transplant-repair-in-bangalore/',
    list: 'ht',
  },
  'Unshaven Hair Transplant': {
    text: 'A discreet transplant without shaving your head, so it stays unnoticeable.',
    path: 'unshaven-hair-transplant/',
    list: 'ht',
  },
  'Body Hair Transplant': {
    text: 'Hair from the body, such as the chest or beard, is moved to the scalp when scalp donor hair is limited.',
    path: 'body-hair-transplant/',
    list: 'ht',
  },
  'Stem Cell Therapy': {
    text: 'Regenerative therapy to strengthen weak follicles and improve hair density.',
    path: 'stem-cell-therapy-for-hair-loss-in-bangalore/',
    list: 'hf',
  },
  'PRP Treatment': {
    text: 'Platelet rich plasma from your own blood is injected into the scalp to strengthen roots and reduce hair fall.',
    path: 'best-prp-hair-treatment-in-bangalore/',
    list: 'hf',
  },
  'GFC Treatment': {
    text: 'Concentrated growth factors from your own blood to boost thinning hair.',
    path: 'gfc-hair-treatment-in-bangalore/',
    list: 'hf',
  },
  'QR678 Treatment': {
    text: 'A non-surgical scalp injection treatment for hair fall and thinning.',
    path: 'qr678-hair-treatment-in-bangalore/',
    list: 'hf',
  },
  'Exosome Therapy': {
    text: 'Advanced cell-based therapy to support healthier, fuller hair growth.',
    path: 'exosome-hair-treatment-in-bangalore/',
    list: 'hf',
  },
  'Dutexome Treatment': {
    text: 'A targeted scalp therapy for pattern hair loss.',
    path: 'dutexome-hair-treatment-in-bangalore/',
    list: 'hf',
  },
  'Laser Hair Therapy': {
    text: 'Painless low level laser light to stimulate follicles and support regrowth.',
    path: 'low-level-laser-therapy/',
    list: 'hf',
  },
  'Scalp Micropigmentation': {
    text: 'Fine pigment dots that create the look of fuller hair or a closely shaved head.',
    path: 'scalp-micropigmentation-in-bangalore/',
    list: 'hf',
  },
  'Alopecia Treatment': {
    text: 'Diagnosis and treatment for patchy hair loss such as alopecia areata.',
    path: 'alopecia-areata-treatment-in-bangalore/',
    list: 'hf',
  },
  'Dandruff Treatment': {
    text: 'Treats dandruff and scalp conditions that can trigger hair fall.',
    path: 'dandruff-treatment-in-bangalore/',
    list: 'hf',
  },
  'Beard Transplant': {
    text: 'Fills a patchy beard, moustache, goatee and sideburns, matching natural growth direction.',
    path: 'beard-transplant-in-bangalore/',
    list: 'treat',
  },
  'Eyebrow Restoration': {
    text: 'Rebuilds thin, over-plucked or scarred brows with single hair precision and a natural angle.',
    path: 'eyebrow-restoration-in-bangalore/',
    list: 'treat',
  },
};

// Short forms patients type, mapped to a treatment card. Keys are regular expressions (whole words).
export const TREATMENT_ALIASES: Record<string, string> = {
  dhi: 'Direct Hair Transplant (DHI / FUE)',
  fue: 'Direct Hair Transplant (DHI / FUE)',
  prp: 'PRP Treatment',
  gfc: 'GFC Treatment',
  qr678: 'QR678 Treatment',
  'exosomes?': 'Exosome Therapy',
  dutexome: 'Dutexome Treatment',
  'stem cells?': 'Stem Cell Therapy',
  'laser therapy': 'Laser Hair Therapy',
  smp: 'Scalp Micropigmentation',
  micropigmentation: 'Scalp Micropigmentation',
  alopecia: 'Alopecia Treatment',
  dandruff: 'Dandruff Treatment',
  beard: 'Beard Transplant',
  moustache: 'Beard Transplant',
  'eyebrows?': 'Eyebrow Restoration',
  'failed transplant': 'Failed Hair Transplant Repair',
  unshaven: 'Unshaven Hair Transplant',
  'body hair': 'Body Hair Transplant',
  'female hair': 'Female Hair Transplant',
  'hair transplant': 'Hair Transplant for Men',
};

// "Book for <treatment>" preselects the matching booking option; treatments without one ask as usual.
// Short answers given in the middle of a booking, before the same step is asked again.
export const BRIEF: Record<string, string> = {
  cost: 'Hair transplant cost is graft based, Rs 60 to Rs 100 per graft. The final count is confirmed after a scalp evaluation.',
  clinic:
    'We are at 1st floor, Scorpio House, near Marathahalli Bridge, Munnekolala, Bengaluru 560037. Open Wednesday to Monday, 10 AM to 7 PM. Tuesday closed.',
};

export const BOOKING_OPTION: Record<string, string> = {
  'Unshaven Hair Transplant': 'Unshaven & Body Hair Transplant',
  'Body Hair Transplant': 'Unshaven & Body Hair Transplant',
  'PRP Treatment': 'Non-Surgical Treatment (GFC, PRP, QR678)',
  'GFC Treatment': 'Non-Surgical Treatment (GFC, PRP, QR678)',
  'QR678 Treatment': 'Non-Surgical Treatment (GFC, PRP, QR678)',
};

const NOT_SURE: Choice = { label: 'Not sure, help me choose', action: 'go', value: 'notsure' };
const treatmentChoices = (list: 'ht' | 'hf'): Choice[] => [
  ...Object.keys(TREATMENT_INFO)
    .filter((name) => TREATMENT_INFO[name].list === list)
    .map((name) => ({ label: name, action: 'treat', value: name })),
  NOT_SURE,
];

// The treatment card: name and short answer, then Book for and Read more.
export function treatmentCard(name: string): ChatResponse | null {
  const info = TREATMENT_INFO[name];
  if (!info) return null;
  return {
    messages: [{ type: 'text', text: `**${name}**\n${info.text}` }],
    ui: {
      type: 'chips',
      options: [
        { label: `Book for ${name}`, action: 'book_for', value: name, primary: true },
        { label: 'Read more on our website', href: SITE + info.path },
      ],
      back: { label: 'Back', action: 'go', value: info.list },
      main: true,
    },
    input: TYPE,
  };
}

const getQuote = (topic: string): Choice => ({ label: 'Get exact quote', action: 'callback', value: topic });

// Cost guide (approved mockup): graft based, by hair loss pattern.
function costAnswer(text: string, then: Choice[]): ChatResponse {
  return {
    messages: [{ type: 'text', text }],
    ui: { type: 'chips', options: then, back: { label: 'Back', action: 'go', value: 'cost' }, main: true },
    input: TYPE,
  };
}
const costRange = (grafts: string, rupees: string) =>
  costAnswer(
    `Typical need: **${grafts} grafts**.\nAt Rs 60 to Rs 100 per graft, that is about **${rupees}**.\nEMI available, no hidden charges. The final count is confirmed after a scalp evaluation.`,
    [
      getQuote('Hair transplant cost'),
      HAIR_ANALYSIS,
      { label: 'Book consultation', action: 'go', value: 'book' },
    ],
  );

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
  treat: {
    messages: [{ type: 'text', text: 'What would you like to explore?' }],
    ui: {
      type: 'chips',
      main: true,
      options: [
        { label: 'Hair Transplant', action: 'go', value: 'ht' },
        { label: 'Hair Fall & Scalp Treatments', action: 'go', value: 'hf' },
        { label: 'Beard Transplant', action: 'treat', value: 'Beard Transplant' },
        { label: 'Eyebrow Restoration', action: 'treat', value: 'Eyebrow Restoration' },
        NOT_SURE,
      ],
    },
    input: TYPE,
  },
  ht: {
    messages: [{ type: 'text', text: 'Pick a hair transplant option.' }],
    ui: {
      type: 'chips',
      options: treatmentChoices('ht'),
      back: { label: 'Back', action: 'go', value: 'treat' },
      main: true,
    },
    input: TYPE,
  },
  hf: {
    messages: [{ type: 'text', text: 'Pick a treatment to learn more.' }],
    ui: {
      type: 'chips',
      options: treatmentChoices('hf'),
      back: { label: 'Back', action: 'go', value: 'treat' },
      main: true,
    },
    input: TYPE,
  },
  notsure: {
    messages: [
      {
        type: 'text',
        text: 'No problem, most patients are not sure at first. The right treatment depends on the cause of your hair loss, which the doctor confirms after a scalp evaluation. You can get a quick estimate from your photos, or let our team guide you.',
      },
    ],
    ui: {
      type: 'chips',
      options: [
        HAIR_ANALYSIS,
        { label: 'Book a consultation', action: 'book_for', value: 'Not sure yet', primary: true },
        { label: 'Get a callback', action: 'callback', value: 'Help choosing a treatment' },
        WHATSAPP_US,
      ],
      back: { label: 'Back', action: 'go', value: 'treat' },
      main: true,
    },
    input: TYPE,
  },
  intl: {
    messages: [
      {
        type: 'text',
        text: 'Every international case is planned before you fly. Scalp assessment, graft count and donor mapping are confirmed on a video call first, and the procedure fits in one trip with follow-up after you return home.',
      },
    ],
    ui: {
      type: 'chips',
      main: true,
      options: [
        { label: 'Plan my treatment', action: 'callback', value: 'International patient' },
        { label: 'Share photos on WhatsApp', href: WA, variant: 'wa' },
        { label: 'Read more', href: SITE + 'hair-transplant-medical-tourism-in-bangalore/' },
      ],
    },
    input: TYPE,
  },
  talk: {
    messages: [{ type: 'text', text: `Choose how you would like to reach us. We are open ${OPEN_HOURS}` }],
    ui: {
      type: 'chips',
      main: true,
      options: [
        CALL,
        WHATSAPP_US,
        { label: 'Request a callback', action: 'callback', value: 'General enquiry' },
      ],
    },
    input: TYPE,
  },
  clinic: {
    messages: [
      {
        type: 'text',
        text: `**Neo Follicle Hair Transplant Clinic**\n1st floor, Scorpio House, near Marathahalli Bridge, Munnekolala, Bengaluru 560037.\nOpen ${OPEN_HOURS}`,
      },
    ],
    ui: { type: 'chips', main: true, options: [{ label: 'Open in Google Maps', href: MAPS }, CALL] },
    input: TYPE,
  },
  results: {
    messages: [{ type: 'text', text: 'See real results from Neo Follicle patients.' }],
    ui: {
      type: 'chips',
      main: true,
      options: [
        { label: 'Hair transplant', href: SITE + 'image-gallery/#hair-transplant-results' },
        { label: 'Beard', href: SITE + 'image-gallery/#beard-transplant-results' },
        { label: 'Eyebrow', href: SITE + 'image-gallery/#eyebrow-transplant-results' },
        { label: 'Female hair', href: SITE + 'image-gallery/#female-hair-restoration' },
        { label: 'Failed transplant repair', href: SITE + 'image-gallery/#failed-hair-transplant-repair' },
        { label: 'GFC and PRP', href: SITE + 'image-gallery/#gfc-prp-therapy-results' },
        { label: 'Patient videos', href: SITE + 'video-gallery/' },
        { label: 'Celebrity patients', href: SITE + 'celebrity-hair-transplant/' },
      ],
    },
    input: TYPE,
  },
  cost: {
    messages: [
      {
        type: 'text',
        text: 'Hair transplant cost is graft based, Rs 60 to Rs 100 per graft. Which best describes your hair loss?',
      },
    ],
    ui: {
      type: 'chips',
      main: true,
      options: [
        { label: 'Receding hairline', action: 'go', value: 'cost_receding' },
        { label: 'Crown thinning', action: 'go', value: 'cost_crown' },
        { label: 'Front and crown', action: 'go', value: 'cost_front_crown' },
        { label: 'Advanced baldness', action: 'go', value: 'cost_advanced' },
        { label: 'Beard or eyebrows', action: 'go', value: 'cost_beard' },
        { label: 'Not sure', action: 'go', value: 'cost_unsure' },
      ],
    },
    input: TYPE,
  },
  cost_receding: costRange('1,000 to 1,800', 'Rs 60,000 to Rs 1,80,000'),
  cost_crown: costRange('1,200 to 2,000', 'Rs 72,000 to Rs 2,00,000'),
  cost_front_crown: costRange('2,000 to 3,000', 'Rs 1,20,000 to Rs 3,00,000'),
  cost_advanced: costRange('3,000+', 'Rs 1,80,000 and above'),
  cost_beard: costAnswer(
    'Cost depends on the area and graft count. Share a photo or get a callback for an exact quote.',
    [getQuote('Beard or eyebrow cost'), WHATSAPP_US],
  ),
  cost_unsure: costAnswer(
    'The AI Hair Analysis gives an estimate from your photos, or the team can guide you on a call.',
    [HAIR_ANALYSIS, { label: 'Get a callback', action: 'callback', value: 'Cost guidance' }],
  ),
};

// Google reviews (same data as backend/app/clinics/CL01.json "reviews", taken from the listing on 24 Oct 2026).
export const REVIEWS = {
  clinic: 'Neo Follicle',
  rating: '4.8',
  count: '1,040',
  link: 'https://www.google.com/maps/place/Neo+Follicle+Hair+Transplant/@12.9562256,77.7073554,17z/data=!4m8!3m7!1s0x3bae13439e1fc9e7:0x12fed4d549fb599a!8m2!3d12.9562256!4d77.7073554!9m1!1b1!16s%2Fg%2F11gjn959r3',
  videos: 'https://neofollicletransplant.com/video-gallery/#hair-transplant-testimonials',
  items: [
    {
      name: 'Venkat A.',
      topic: 'transplant',
      text: 'I underwent a hair transplant at Neo Follicle Transplant Clinic just 3 days ago. The entire process was very professional and smooth. Dr. Sandeep and his team were highly skilled, clear in their communication, and made sure I felt comfortable throughout the procedure. Highly recommended.',
    },
    {
      name: 'Satya R.',
      topic: 'gfc',
      text: 'I underwent GFC treatment here and saw excellent results in just four sessions. The team is professional, supportive, and maintains a friendly approach throughout the process. I would confidently recommend this clinic to anyone facing hair loss issues.',
    },
    {
      name: 'Azhar K.',
      topic: 'international',
      text: 'I came a long way from Mauritius to get my hair transplant done at Neo Follicle Clinic. Everything went smoothly and special thanks to Mrs. Chandra for her kindness and great care. Really happy with the results',
    },
    {
      name: 'Raghu R.',
      topic: 'transplant',
      text: 'After a year-long research, I found that Neo Hair Transplant met my criteria for undergoing a transplant. The team is highly professional and dedicated. It has been three months since my transplant, and I am quite happy with the results so far.',
    },
    {
      name: 'Devaraj N.',
      topic: 'gfc',
      text: 'I had a very good experience with Dr. Yogita during my GFC hair treatment. She explained the entire procedure clearly, addressed all my concerns patiently, and made me feel comfortable throughout the treatment.',
    },
    {
      name: 'Anand S.',
      topic: 'international',
      text: 'Neo have a great team, and I think a procedure that allows for quicker recovery. It’s been a good experience, I recommend. Will board my flight to US 5 days after the procedure.',
    },
    {
      name: 'Sumit P.',
      topic: 'transplant',
      text: 'Had recently done my hair transplant and the results are commendable. Dr mahapatra and his team has done a great job. Highly recommended. Thank you.',
    },
    {
      name: 'Saikrishna C.',
      topic: 'gfc',
      text: 'I recently visited Neo Follicle for GFC treatment and had a really good experience. The staff was professional, explained every step clearly, and made the sessions comfortable. I am already noticing improvements in hair quality and reduced hair fall.',
    },
    {
      name: 'Udit K.',
      topic: 'transplant',
      text: 'Overall it was a positive experience. From the initial consultation to the procedure and post-op care, the team was professional. They explained the process clearly, set realistic expectations, and made sure I was comfortable throughout.',
    },
    {
      name: 'Abhishek P.',
      topic: 'transplant',
      text: 'Had a good experience working with Dr Sandeep, Dr Sumedha and Ms Chandra. The overall process was made very smooth including post-procedure checkups. The staff was also very friendly and supportive at every step. I will recommend Neo Follicle Clinic.',
    },
    {
      name: 'Faizan S.',
      topic: 'transplant',
      text: 'The result is amazing and the doctor and staff are very experienced and my hair transplant procedure was very smooth.',
    },
    {
      name: 'Rupesh Y.',
      topic: 'transplant',
      text: 'I had a hair transplant done from here, few weeks ago, everything was great, everything was clearly said and the operation was also very smooth.',
    },
  ] as { name: string; topic: 'transplant' | 'gfc' | 'international'; text: string }[],
};

// The approved "celebrity clients" fact (the mock has no knowledge base; this one is asked for often).
export const CELEBRITIES =
  'Kannada actors Sri Murali, Prem, Rakshith Gowda and Sharan, and RJ Mayuraa Raghavendra (radio jockey) have chosen Neo Follicle for hair restoration. Every patient gets the same doctor-led, private approach.';
