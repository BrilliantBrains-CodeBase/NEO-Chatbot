import type { IconName } from "@/components/crm/Icon";

// The Dashboard (the chatbot's console), from the approved design "Patient Assistant Console".
// Stage = the build stage marked in the design; bbOnly sections are for BB Admin.
export type Section = {
  id: string;
  icon: IconName;
  label: string;
  group: string;
  stage: number;
  desc: string;
  bbOnly?: boolean;
  /** Turned off: hidden from everyone, its page returns 404. */
  off?: boolean;
};

export const SECTIONS: Section[] = [
  {
    id: "overview",
    off: true,
    icon: "dash",
    label: "Overview",
    group: "",
    stage: 1,
    desc: "How the assistant is doing and what needs a decision.",
  },
  {
    id: "appearance",
    icon: "palette",
    label: "Appearance",
    group: "Widget",
    stage: 1,
    desc: "One place for the look: Look (name, Enabled / Disabled, logo), Colours, Widget style and Launcher, each a tab, with a live preview.",
  },
  {
    id: "templates",
    icon: "layout",
    label: "Templates",
    group: "Widget",
    stage: 1,
    desc: "Pick one of three widget templates for this clinic.",
  },
  {
    id: "menu",
    icon: "tiles",
    label: "Menu buttons",
    group: "Widget",
    stage: 1,
    desc: "The chat's opening: the welcome message and trust figures, then the main buttons, the sub-buttons inside them, where each one leads, and the typed phrases that work like each button (checked by the button test set before publishing).",
  },
  {
    id: "content",
    icon: "info",
    label: "Clinic info",
    group: "Widget",
    stage: 2,
    desc: "One place for what the chat says about the clinic: Lead questions, Services, Contact & hours, and Reviews (Google rating, patient quotes, celebrities), each a tab, with a live preview.",
  },
  {
    id: "ai",
    icon: "spark",
    label: "Knowledge base",
    group: "Widget",
    stage: 5,
    desc: "Typed questions answered from approved content only.",
  },
  {
    id: "legal",
    icon: "file",
    label: "Legal & consent",
    group: "Widget",
    stage: 5,
    desc: "Consent wording and policy links shown in the chat.",
  },
  {
    id: "unanswered",
    icon: "help",
    label: "Unanswered questions",
    group: "Bot quality",
    stage: 3,
    desc: "What patients asked that the bot could not answer. Staff write or approve an answer; nothing goes live by itself.",
  },
  {
    id: "chats",
    icon: "req",
    label: "Chat transcripts",
    group: "Bot quality",
    stage: 3,
    desc: "Every conversation, its patient and lead, and why the bot gave each reply.",
  },
  {
    id: "quality",
    off: true,
    icon: "check",
    label: "Test & quality",
    group: "Bot quality",
    stage: 3,
    desc: "Run the test sets and a test link before publishing, so every change keeps the scores at 100%.",
  },
  {
    id: "install",
    icon: "code",
    label: "Website install",
    group: "Connect",
    stage: 3,
    desc: "The code to paste on the clinic's website, and which pages the bot shows on.",
  },
  {
    id: "integrations",
    icon: "plug",
    label: "Integrations",
    group: "Connect",
    stage: 3,
    desc: "Outside services: Cal.com, WhatsApp, Google Sheet leads.",
  },
  {
    id: "security",
    icon: "lock",
    label: "Login & security",
    group: "Security",
    stage: 4,
    desc: "Sign-in, checks and limits that protect the console and the widget.",
  },
  {
    id: "privacy",
    off: true,
    icon: "shield",
    label: "Privacy & data",
    group: "Security",
    stage: 4,
    desc: "How patient data is collected, stored, masked and deleted.",
  },
  {
    id: "team",
    icon: "team",
    label: "Team & access",
    group: "Security",
    stage: 2,
    desc: "Who can sign in, which clinics they can open and what each role can change; invites and the allowed email domain.",
  },
  {
    id: "activity",
    off: true,
    icon: "clock",
    label: "Activity log",
    group: "Security",
    stage: 4,
    desc: "Every change, with who made it and when.",
  },
  {
    id: "alerts",
    off: true,
    icon: "bell",
    label: "Staff alerts",
    group: "Security",
    stage: 4,
    desc: "Who is told about emergency or medical questions and unanswered questions piling up.",
  },
  {
    id: "versions",
    off: true,
    icon: "undo",
    label: "Versions",
    group: "Admin",
    stage: 5,
    desc: "Each publish is saved so you can roll back.",
  },
];

/** The sections in use (turned-off ones left out). */
export const ON_SECTIONS = SECTIONS.filter((s) => !s.off);

/** Who may open the console: BB Admin and clinic managers. */
export const canUseConsole = (role: string | undefined) =>
  role === "bb_admin" || role === "clinic_manager";
