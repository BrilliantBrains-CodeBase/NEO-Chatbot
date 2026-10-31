// The clinic onboarding questionnaire (user, 2026-10-31): what every clinic answers, new ones included, before
// the chatbot goes live. Each answer is stored ONCE as a Knowledge base fact (its key), so Q&A answers can link
// it as {key} and one change updates every answer. Grouped into 10 onboarding steps; a section with a gate is
// asked only when the gate is answered Yes; repeat sections are answered once per doctor, service, etc.

export type QType = "text" | "yes_no" | "choice" | "number";
export type Question = {
  key: string; // the fact key: same question text → same key (asked once)
  text: string;
  type: QType;
  options?: string[];
  default?: string; // a safe default, e.g. "No" for "Should the bot provide diagnoses?"
};
export type Section = {
  n: number; // as in the questionnaire
  title: string;
  step: number; // 1..10
  repeat?: "doctor" | "service" | "condition" | "procedure" | "branch";
  gate?: Question; // asked first; the rest only when the answer is Yes
  note?: string;
  questions: Question[];
};

export const STEPS = [
  "Clinic details",
  "Specialty",
  "Doctors",
  "Services & conditions",
  "Appointments & fees",
  "Timings & branches",
  "Policies & facilities",
  "Patient FAQs",
  "Chatbot behaviour",
  "Review & publish",
];

export const SPECIALTIES = [
  "Orthopaedics",
  "Gynaecology",
  "Cardiology",
  "Dermatology",
  "Dental",
  "Fertility / IVF",
  "Paediatrics",
  "Neurology",
  "ENT",
  "Ophthalmology",
  "Gastroenterology",
  "Urology",
  "Pulmonology",
  "Endocrinology",
  "General Medicine",
  "Physiotherapy",
  "Psychiatry",
  "Oncology",
  "Nephrology",
  "Rheumatology",
  "Other",
];

/** Topics asked after the specialty is known (section 33). */
export const SPECIALTY_TOPICS: Record<string, string[]> = {
  Orthopaedics: [
    "Knee",
    "Hip",
    "Shoulder",
    "Spine",
    "Arthritis",
    "Fractures",
    "Sports injuries",
    "ACL",
    "Arthroscopy",
    "Joint replacement",
    "Physiotherapy",
  ],
  Gynaecology: [
    "Periods",
    "PCOS",
    "Pregnancy",
    "Menopause",
    "Fibroids",
    "Endometriosis",
    "Contraception",
    "Women's screening",
  ],
  Cardiology: [
    "Blood pressure",
    "Chest pain",
    "Palpitations",
    "Cholesterol",
    "ECG",
    "2D Echo",
    "TMT",
    "Angiography",
    "Angioplasty",
    "Heart failure",
  ],
};

// Words left out of a key, so "What is your clinic name?" is clinic_name.
const STOP = new Set(
  (
    "what is are your the a an of do does you can should how which who when where will be there any to for " +
    "in on at it this that with by from per or and as patients patient"
  ).split(" "),
);

/** A stable key from the question text (same text → same key). */
export function keyOf(text: string): string {
  const words = text
    .toLowerCase()
    .replace(/[^a-z0-9 ]/g, " ")
    .split(/\s+/)
    .filter((w) => w && !STOP.has(w));
  const key = (words.join("_") || "answer")
    .replace(/^(\d)/, "q_$1")
    .slice(0, 50)
    .replace(/_+$/, "");
  return /^[a-z]/.test(key) ? key : `q_${key}`.slice(0, 50);
}

const YES = /^(is|are|do|does|can|should|will|has|have)\b/i;

// Questions answered LIVE from the Dashboard / CRM (backend app/chat/live_facts.py): the same keys there.
const FIXED_KEY: Record<string, string> = {
  "Do you have an emergency contact number?": "emergency_contact_number",
  "What should it do outside working hours?": "outside_working_hours",
  "What time does the clinic open?": "clinic_open_time",
  "What time does the clinic close?": "clinic_close_time",
  "What is the last appointment time?": "last_appointment_time",
  "What is the last patient entry time?": "last_appointment_time",
  "How long is a typical consultation?": "consultation_length",
  "How early can patients book an appointment?": "booking_window",
  "What treatments do you provide?": "services_provided",
  "What services do you NOT provide?": "services_not_provided",
  "Which doctors provide online consultations?": "online_doctors",
  "What are the online consultation timings?": "online_timings",
  "Which platform do you use?": "online_platform",
  "What should the chatbot call your clinic?": "chatbot_clinic_name",
  "Is parking available?": "parking_available",
};

function q(text: string, more: Partial<Question> = {}): Question {
  return {
    key: more.key ?? FIXED_KEY[text] ?? keyOf(text),
    text,
    type: more.type ?? (YES.test(text) ? "yes_no" : "text"),
    ...more,
  };
}
const qs = (...texts: string[]) => texts.map((t) => q(t));
const no = (text: string) => q(text, { default: "No" });

export const SECTIONS: Section[] = [
  {
    n: 1,
    title: "Basic clinic information",
    step: 1,
    questions: [
      q("What is your clinic name?", { key: "clinic_name" }),
      q("What is your clinic type?", { key: "clinic_type" }),
      q("What is your primary specialty?", {
        key: "primary_specialty",
        type: "choice",
        options: SPECIALTIES,
      }),
      q("Do you have any secondary specialties?", {
        key: "secondary_specialties",
        type: "text",
      }),
      q("Is this a single doctor clinic or multi doctor clinic?", {
        key: "clinic_doctors_kind",
        type: "choice",
        options: ["Single doctor", "Multi doctor"],
      }),
      q("How many doctors currently practice at your clinic?", {
        key: "doctors_count",
        type: "number",
      }),
      q("How many branches do you have?", {
        key: "branches_count",
        type: "number",
      }),
      q("What is your main clinic address?", { key: "clinic_address" }),
      q("What city are you located in?", { key: "clinic_city" }),
      q("What is your clinic contact number?", { key: "clinic_phone" }),
      q("What is your WhatsApp number?", { key: "clinic_whatsapp" }),
      q("What is your email address?", { key: "clinic_email" }),
      q("What is your website URL?", { key: "clinic_website" }),
      q("Do you have a Google Maps location link?", {
        key: "google_maps_link",
        type: "text",
      }),
      q("Do you have social media profiles?", {
        key: "social_media",
        type: "text",
      }),
      q("What languages does your clinic support?", { key: "languages" }),
    ],
  },
  {
    n: 2,
    title: "Clinic specialty",
    step: 2,
    questions: [
      ...qs(
        "What are your subspecialties?",
        "What conditions do you commonly treat?",
        "What treatments do you provide?",
        "What procedures do you perform?",
        "What surgeries do you perform?",
        "What services do you NOT provide?",
        "What conditions should patients contact another specialist for?",
      ),
    ],
  },
  {
    n: 33,
    title: "Specialty specific questions",
    step: 2,
    note: "Loaded after the primary specialty is chosen: which of these topics does the clinic treat?",
    questions: [
      q("Which specialty topics do you treat?", { key: "specialty_topics" }),
    ],
  },
  {
    n: 3,
    title: "Doctor information",
    step: 3,
    repeat: "doctor",
    note: "Repeat for every doctor (doctors, hours and fees are also in Dashboard → Doctors).",
    questions: qs(
      "What is the doctor's full name?",
      "What is the doctor's designation?",
      "What is the doctor's specialty?",
      "What is the doctor's subspecialty?",
      "What are the doctor's qualifications?",
      "How many years of experience does the doctor have?",
      "What are the doctor's areas of expertise?",
      "Which conditions does the doctor treat?",
      "Which procedures does the doctor perform?",
      "Which surgeries does the doctor perform?",
      "At which branch does the doctor consult?",
      "Which days is the doctor available?",
      "What are the doctor's consultation timings?",
      "Is the doctor available in the morning?",
      "Is the doctor available in the afternoon?",
      "Is the doctor available in the evening?",
      "Is the doctor available on Sunday?",
      "Does the doctor provide online consultations?",
      "What is the doctor's consultation fee?",
      "What is the follow up consultation fee?",
      "For how many days is follow up valid?",
      "Does the doctor accept walk in patients?",
      "Does the doctor require prior appointments?",
      "What languages does the doctor speak?",
      "Does the doctor consult children?",
      "Does the doctor consult adults?",
      "Does the doctor consult senior citizens?",
    ),
  },
  {
    n: 6,
    title: "Services",
    step: 4,
    repeat: "service",
    questions: qs(
      "What is the service name?",
      "Which specialty does this service belong to?",
      "Which doctor provides this service?",
      "Which branch provides this service?",
      "What is the service used for?",
      "Who is this service suitable for?",
      "Is consultation required before this service?",
      "What is the cost?",
      "How long does the service take?",
      "Is an appointment required?",
      "Is any preparation required?",
      "Are there any restrictions before the service?",
      "Is follow up required?",
      "How many sessions are usually required?",
      "Is this service available every day?",
      "Does this service have any age restrictions?",
    ),
  },
  {
    n: 7,
    title: "Conditions treated",
    step: 4,
    repeat: "condition",
    note: "From one condition record the chatbot answers: Do you treat X? Which doctor treats X? Can I book for X?",
    questions: qs(
      "What is the condition name?",
      "Do you treat this condition?",
      "Which doctor treats it?",
      "Which specialty handles it?",
      "What treatments are available for it?",
      "Are diagnostic tests required before treatment?",
      "Is surgery available if required?",
      "Can this condition be treated through online consultation?",
      "Does the clinic provide follow up care?",
      "Should patients book a consultation before discussing treatment options?",
    ),
  },
  {
    n: 8,
    title: "Procedures",
    step: 4,
    repeat: "procedure",
    questions: qs(
      "What is the procedure name?",
      "Which doctor performs it?",
      "Which branch offers it?",
      "What condition is it used for?",
      "Is consultation required first?",
      "Is any test required before the procedure?",
      "What preparation is required?",
      "How long does the procedure take?",
      "Is admission required?",
      "Is anaesthesia required?",
      "What is the approximate cost?",
      "How long is recovery?",
      "Is follow up required?",
      "Are there any restrictions after the procedure?",
    ),
  },
  {
    n: 9,
    title: "Surgery information",
    step: 4,
    gate: q("Does your clinic perform surgeries?", {
      key: "performs_surgeries",
    }),
    note: "The chatbot never promises exact surgery prices unless the clinic gives fixed prices.",
    questions: qs(
      "What surgeries do you perform?",
      "Which doctors perform them?",
      "At which hospital or clinic are surgeries performed?",
      "Is admission required?",
      "How many days of hospital stay are usually required?",
      "Is pre operative evaluation required?",
      "What tests are required before surgery?",
      "Is insurance accepted for surgery?",
      "Is cashless insurance available?",
      "Is an approximate surgery cost available?",
      "Does the cost vary by patient?",
      "Is post surgery follow up included?",
      "Does the clinic provide physiotherapy or rehabilitation after surgery?",
    ),
  },
  {
    n: 12,
    title: "Diagnostics",
    step: 4,
    gate: q("Do you provide diagnostic tests?", { key: "diagnostics" }),
    questions: [
      q("What preparation is required for tests?", { key: "test_preparation" }),
      ...qs(
        "Which tests are available?",
        "Are tests performed inside the clinic?",
        "Are tests performed through an external laboratory?",
        "Is blood testing available?",
        "Is X ray available?",
        "Is ultrasound available?",
        "Is ECG available?",
        "Is 2D Echo available?",
        "Is TMT available?",
        "Is MRI available?",
        "Is CT available?",
        "Are specialty specific diagnostic tests available?",
        "Is fasting required for any tests?",
        "What is the price of each test?",
        "When will reports be available?",
        "Can reports be sent on WhatsApp?",
        "Can reports be sent by email?",
        "Can reports be downloaded online?",
      ),
    ],
  },
  {
    n: 13,
    title: "Health packages",
    step: 4,
    gate: q("Do you offer health packages?", { key: "health_packages" }),
    questions: qs(
      "What packages are available?",
      "What tests are included in each package?",
      "What is the package price?",
      "Who is the package suitable for?",
      "Is fasting required?",
      "How long does the package take?",
      "Is consultation included?",
      "Is home sample collection available?",
      "Are there special packages for women?",
      "Are there packages for men?",
      "Are there senior citizen packages?",
      "Are there children's health packages?",
      "Do you have disease specific packages?",
    ),
  },
  {
    n: 14,
    title: "Home services",
    step: 4,
    gate: q("Do you provide home visits?", { key: "home_visits" }),
    questions: qs(
      "Do doctors provide home consultations?",
      "Do you provide home sample collection?",
      "Which locations are covered?",
      "What is the home visit fee?",
      "What is the home collection fee?",
      "What are the available timings?",
      "How can patients book home services?",
    ),
  },
  {
    n: 4,
    title: "Appointment information",
    step: 5,
    questions: qs(
      "How can patients book an appointment?",
      "Can appointments be booked through the website?",
      "Can appointments be booked through WhatsApp?",
      "Can appointments be booked by phone?",
      "Do you accept walk in appointments?",
      "Is prior appointment mandatory?",
      "What information is required to book an appointment?",
      "How early can patients book an appointment?",
      "Can patients book same day appointments?",
      "What is the last appointment time?",
      "How long is a typical consultation?",
      "What should patients bring for their first appointment?",
      "Do patients need to bring previous medical reports?",
      "Do patients need to carry ID proof?",
      "Do patients need to arrive early?",
      "How many minutes early should they arrive?",
      "Can patients reschedule appointments?",
      "How can patients reschedule?",
      "Can patients cancel appointments?",
      "What is your cancellation policy?",
      "Is there any cancellation charge?",
      "What happens if a patient is late?",
      "Do you send appointment reminders?",
    ),
  },
  {
    n: 10,
    title: "Consultation fees",
    step: 5,
    questions: [
      q("What is the first consultation fee?", { key: "consult_fee" }),
      q("What is the follow up fee?", { key: "follow_up_fee" }),
      q("How long is the follow up period valid?", {
        key: "follow_up_valid_days",
      }),
      ...qs(
        "Do different doctors have different consultation fees?",
        "Is online consultation priced differently?",
        "Are there separate emergency consultation charges?",
        "Are there any registration charges?",
        "Are there any additional clinic charges?",
      ),
    ],
  },
  {
    n: 11,
    title: "Online consultation",
    step: 5,
    gate: q("Do you offer online consultations?", {
      key: "online_consultations",
    }),
    questions: qs(
      "Which doctors provide online consultations?",
      "What are the online consultation timings?",
      "What is the fee?",
      "Which platform do you use?",
      "Can patients consult through WhatsApp video?",
      "Can patients consult through phone?",
      "Can prescriptions be shared digitally?",
      "Can patients upload reports before consultation?",
      "Which conditions are suitable for online consultation?",
      "Which conditions require physical consultation?",
    ),
  },
  {
    n: 15,
    title: "Insurance",
    step: 5,
    gate: q("Do you accept health insurance?", { key: "health_insurance" }),
    questions: qs(
      "Which insurance providers do you accept?",
      "Do you provide cashless treatment?",
      "Is insurance available for consultation?",
      "Is insurance available for procedures?",
      "Is insurance available for surgeries?",
      "What documents are required?",
      "Does the patient need pre authorization?",
      "Who should patients contact regarding insurance?",
    ),
  },
  {
    n: 16,
    title: "Payment",
    step: 5,
    questions: qs(
      "Do you accept cash?",
      "Do you accept UPI?",
      "Do you accept debit cards?",
      "Do you accept credit cards?",
      "Do you accept Google Pay?",
      "Do you accept PhonePe?",
      "Do you accept Paytm?",
      "Can patients pay online?",
      "Do you offer EMI?",
      "Are refunds available?",
      "What is the refund policy?",
    ),
  },
  {
    n: 17,
    title: "Follow up policy",
    step: 5,
    questions: [
      q("Is follow up consultation available?"),
      q("How many days is follow up valid?", { key: "follow_up_valid_days" }),
      q("Is follow up free?"),
      q("What is the follow up charge?", { key: "follow_up_fee" }),
      ...qs(
        "Does follow up require an appointment?",
        "Can follow up be done online?",
        "Can reports be reviewed through WhatsApp?",
      ),
      q("Can patients call the doctor directly after consultation?", {
        key: "call_doctor_directly",
      }),
    ],
  },
  {
    n: 5,
    title: "Clinic timings",
    step: 6,
    questions: [
      ...[
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
      ].map((d) =>
        q(`What are your ${d} timings?`, { key: `timings_${d.toLowerCase()}` }),
      ),
      ...qs(
        "Are you open on public holidays?",
        "Do your timings change on holidays?",
        "Do you have different morning and evening timings?",
        "What time does the clinic open?",
        "What time does the clinic close?",
        "What is the last patient entry time?",
        "Do individual doctors have different timings?",
      ),
    ],
  },
  {
    n: 22,
    title: "Branch information",
    step: 6,
    repeat: "branch",
    gate: q("Do you have more than one branch?", { key: "multiple_branches" }),
    note: "The chatbot answers branch by branch.",
    questions: qs(
      "Branch name?",
      "Branch address?",
      "Branch contact number?",
      "Branch WhatsApp number?",
      "Branch timings?",
      "Doctors available at this branch?",
      "Services available at this branch?",
      "Procedures available at this branch?",
      "Tests available at this branch?",
      "Does this branch accept insurance?",
      "Does this branch have parking?",
      "Does this branch have emergency facilities?",
    ),
  },
  {
    n: 30,
    title: "Day to day operational updates",
    step: 6,
    note: "Each change can then be: Permanent update · Today only · Temporary update · Until a specific date.",
    questions: qs(
      "Do doctor timings change regularly?",
      "Do doctors take unplanned leave?",
      "Do consultation fees change?",
      "Do clinic timings change?",
      "Do holiday timings change?",
      "Do you run temporary offers?",
      "Do services become temporarily unavailable?",
      "Do appointment slots change regularly?",
      "Do branches temporarily close?",
      "Do you need to update walk in availability daily?",
    ),
  },
  {
    n: 31,
    title: "Notifications and temporary announcements",
    step: 6,
    questions: qs(
      "Do you want to show temporary clinic announcements?",
      "Should patients be informed when a doctor is on leave?",
      "Should patients be informed about holiday timings?",
      "Should special offers appear in chatbot responses?",
      "Should temporary service disruptions appear?",
      "Should branch closure notifications appear?",
      "Should the chatbot show notices before appointment booking?",
    ),
  },
  {
    n: 18,
    title: "Prescription policy",
    step: 7,
    questions: [
      ...qs(
        "Are prescriptions provided digitally?",
        "Can prescriptions be shared on WhatsApp?",
        "Can prescriptions be emailed?",
        "Can patients request an old prescription?",
        "How can they request it?",
        "Can prescriptions be reissued without consultation?",
      ),
      no("Can medication dosage be changed through chat?"),
      q("Should medication related questions always go to the doctor?", {
        default: "Yes",
      }),
    ],
  },
  {
    n: 19,
    title: "Reports and medical records",
    step: 7,
    questions: qs(
      "Can patients access previous reports?",
      "Can patients request medical records?",
      "How can they request records?",
      "Are reports stored online?",
      "For how long are records available?",
      "Can reports be shared digitally?",
      "Is patient verification required before sharing records?",
    ),
  },
  {
    n: 20,
    title: "Facilities",
    step: 7,
    questions: qs(
      "Is parking available?",
      "Is parking free?",
      "Is wheelchair access available?",
      "Is a wheelchair available at the clinic?",
      "Is an elevator available?",
      "Is there a pharmacy?",
      "Is there a laboratory?",
      "Is there a waiting area?",
      "Is drinking water available?",
      "Are washrooms available?",
      "Is the clinic child friendly?",
      "Is the clinic senior citizen friendly?",
    ),
  },
  {
    n: 21,
    title: "Location and directions",
    step: 1,
    questions: [
      q("What is your complete address?", { key: "clinic_address" }),
      q("What is the nearest landmark?", { key: "landmark" }),
      ...qs(
        "What is the nearest metro station?",
        "What is the nearest bus stop?",
        "What is the nearest railway station?",
        "What is the easiest way to reach your clinic?",
      ),
      q("Is parking available nearby?", { key: "parking_nearby" }),
      q("What is the Google Maps link?", { key: "google_maps_link" }),
    ],
  },
  {
    n: 23,
    title: "Emergency information",
    step: 7,
    note: "Emergency words (severe chest pain, difficulty breathing, unconsciousness, severe bleeding, stroke signs, serious injury, pregnancy emergencies) always override normal answers.",
    questions: qs(
      "Does your clinic provide emergency care?",
      "Is emergency care available 24/7?",
      "What emergency services are available?",
      "What emergency services are NOT available?",
      "What should patients do for medical emergencies?",
      "Do you have an emergency contact number?",
      "Should emergency patients visit a nearby hospital instead?",
      "Which symptoms should immediately be routed to emergency guidance?",
    ),
  },
  {
    n: 24,
    title: "Clinic policies",
    step: 7,
    questions: [
      q("What is your appointment policy?"),
      q("What is your cancellation policy?", { key: "cancellation_policy" }),
      q("What is your refund policy?", { key: "refund_policy" }),
      ...qs(
        "What is your late arrival policy?",
        "What is your follow up policy?",
        "What is your privacy policy?",
        "What is your medical records policy?",
        "Do you have age restrictions for any service?",
        "Do minors require a parent or guardian?",
        "Are attendants allowed with patients?",
        "Are there visitor restrictions?",
      ),
    ],
  },
  {
    n: 25,
    title: "Patient preparation",
    step: 7,
    note: "The chatbot gives no personal medication instructions unless the clinic approved them.",
    questions: qs(
      "What should a patient bring for consultation?",
      "Should they bring old prescriptions?",
      "Should they bring previous scans?",
      "Should they bring previous blood reports?",
      "Is fasting required for specific services?",
      "Should patients stop any medication before procedures?",
      "Are there clothing instructions?",
      "Are there pre procedure instructions?",
      "Are there post procedure instructions?",
    ),
  },
  {
    n: 32,
    title: "Information the bot must never claim",
    step: 7,
    note: "Safe defaults: diagnosis, prescription, dosage, stopping or changing medicines, guaranteed outcomes and emergency diagnosis are No.",
    questions: [
      q("Are there questions that must always be routed to the doctor?"),
      no("Should the bot provide diagnoses?"),
      no("Should the bot recommend prescription medicines?"),
      no("Should the bot recommend medicine dosages?"),
      no("Should it tell patients to stop medicines?"),
      no("Should it interpret test reports?"),
      no("Should it make claims about treatment success?"),
      no("Should it guarantee treatment results?"),
      no("Should it provide exact surgical cost without evaluation?"),
      no("Should it answer emergency medical questions?"),
    ],
  },
  {
    n: 26,
    title: "Frequently asked questions",
    step: 8,
    note: "The most valuable answers: each becomes Q&A for the chatbot.",
    questions: qs(
      "What are the top 10 questions patients ask your receptionist?",
      "What are the top questions patients ask on WhatsApp?",
      "What questions do patients repeatedly ask before booking?",
      "What questions do patients ask after booking?",
      "What questions do patients ask after consultation?",
      "What questions do patients ask about treatment costs?",
      "What questions do patients ask about your doctors?",
      "What questions do patients ask about procedures?",
      "What questions do patients ask that your team finds difficult to answer?",
      "What questions should the chatbot never answer automatically?",
    ),
  },
  {
    n: 27,
    title: "Leads and conversion",
    step: 9,
    questions: qs(
      "What should count as a lead?",
      "What patient details should the chatbot collect?",
      "Should the chatbot collect patient name?",
      "Should it collect mobile number?",
      "Should it collect email?",
      "Should it collect preferred appointment date?",
      "Should it collect preferred time?",
      "Should it collect doctor preference?",
      "Should it collect branch preference?",
      "Should it collect the patient's concern?",
      "Should leads be sent to WhatsApp?",
      "Should leads be sent by email?",
      "Should leads enter your CRM?",
      "Who should receive new lead notifications?",
      "Should the chatbot ask for a callback?",
      "During which hours should callbacks be offered?",
    ),
  },
  {
    n: 28,
    title: "Chatbot behaviour",
    step: 9,
    questions: [
      q("What should the chatbot call your clinic?"),
      q("Should the chatbot use a formal or friendly tone?", {
        type: "choice",
        options: ["Formal", "Friendly"],
      }),
      q("Which languages should the chatbot support?"),
      q("Should the chatbot use emojis?"),
      q("Should the chatbot keep answers short or detailed?", {
        type: "choice",
        options: ["Short", "Detailed"],
      }),
      ...qs(
        "Should it actively suggest appointments?",
        "Should it show a Book Appointment button after service questions?",
        "Should it show WhatsApp after unanswered questions?",
      ),
      q("When should it transfer to a human?", { key: "human_handover_when" }),
      ...qs(
        "What should it do outside working hours?",
        "Should it collect leads when the clinic is closed?",
        "What contact options should appear after a failed answer?",
      ),
    ],
  },
  {
    n: 29,
    title: "Human handover",
    step: 9,
    questions: [
      q("When should the chatbot transfer to a human?", {
        key: "human_handover_when",
      }),
      ...qs(
        "Who receives the conversation?",
        "Is live chat available?",
        "What are human support hours?",
        "What happens outside those hours?",
        "Should the bot collect phone number before transferring?",
        "Should the previous conversation be visible to staff?",
        "Should high priority enquiries trigger alerts?",
      ),
    ],
  },
  {
    n: 34,
    title: "Final verification before going live",
    step: 10,
    note: "The clinic owner confirms each, then the chatbot is published.",
    questions: qs(
      "Are all doctor names correct?",
      "Are consultation fees correct?",
      "Are clinic timings correct?",
      "Are doctor schedules correct?",
      "Are branch details correct?",
      "Are services correct?",
      "Are prices correct?",
      "Are insurance details correct?",
      "Are appointment details correct?",
      "Are all phone numbers correct?",
      "Are emergency instructions correct?",
      "Are there any questions the chatbot should not answer?",
      "Who is responsible for keeping this information updated?",
    ),
  },
];

/** Every question once (a key asked in two sections appears once, where first asked), in step order. */
export function allQuestions(): {
  section: Section;
  question: Question;
  gate: boolean;
}[] {
  const seen = new Set<string>();
  const out: { section: Section; question: Question; gate: boolean }[] = [];
  for (const s of [...SECTIONS].sort((a, b) => a.step - b.step || a.n - b.n)) {
    for (const [question, gate] of [
      ...(s.gate ? [[s.gate, true] as const] : []),
      ...s.questions.map((x) => [x, false] as const),
    ]) {
      if (s.repeat && !gate) {
        out.push({ section: s, question, gate }); // per doctor / branch …: kept, answered per item later
        continue;
      }
      if (seen.has(question.key)) continue;
      seen.add(question.key);
      out.push({ section: s, question, gate });
    }
  }
  return out;
}
