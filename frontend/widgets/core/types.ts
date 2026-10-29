// Widget and backend contract (README "Widget and backend contract"). All traffic is JSON.

export type ChatEvent = 'start' | 'text' | 'button' | 'restart';

export interface ChatRequest {
  client_id: string;
  session_id: string;
  visitor_id: string;
  event: ChatEvent;
  // button: action and value of the tapped choice. text: what was typed; cc is the country code in phone mode.
  payload: { action?: string; value?: string; text?: string; cc?: string };
  context: { page_url: string; device: 'mobile' | 'desktop'; lang: 'en' };
}

export interface BotMessage {
  type: 'text';
  // Plain text. "**bold**" is shown in bold and "\n" starts a new line; nothing else is interpreted.
  text: string;
}

// Anything the patient can tap. With href it opens a link (call, WhatsApp, website) instead of sending an event.
export interface Choice {
  label: string;
  action?: string;
  value?: string;
  href?: string;
  icon?: string;
  primary?: boolean;
  variant?: 'wa' | 'sos';
}

interface Nav {
  // Ghost links under the group.
  back?: Choice;
  main?: boolean;
}

export interface MenuBlock {
  type: 'menu';
  layout: 'cards3' | 'tiles2' | 'pills';
  items: Choice[];
}

export interface ChipsBlock extends Nav {
  type: 'chips';
  options: Choice[];
}

export interface CalendarBlock {
  type: 'month_calendar';
  action: string;
  // Dates are YYYY-MM-DD in the clinic's time zone.
  today: string;
  min: string;
  max: string;
  closed_weekdays: number[]; // 0 = Sunday
}

export interface TimeGridBlock {
  type: 'time_grid';
  action: string;
  slots: string[]; // HH:MM, 24 hour
  first: number; // shown before "More times"
  any_time: boolean;
}

export interface DoctorCardBlock extends Nav {
  type: 'doctor_card';
  name: string;
  title: string;
  quals: string;
  stats: { value: string; label: string }[];
  options: Choice[];
}

export type UiBlock = MenuBlock | ChipsBlock | CalendarBlock | TimeGridBlock | DoctorCardBlock;

export type InputMode = 'text' | 'phone' | 'email';

export interface ChatResponse {
  messages: BotMessage[];
  ui?: UiBlock | null;
  input: { mode: InputMode; placeholder: string };
  quick?: Choice[];
}

// The clinic's Call and WhatsApp for the mobile contact row ("" when not set).
export interface ClinicContact {
  phone: string;
  whatsapp: string;
}

// Dashboard → Templates as published: how the main menu looks, and the one button filled in the main colour.
export interface MenuTemplate {
  id: 'tiles' | 'pills' | 'cards';
  columns: 2 | 3;
  filled_button: string;
}

// Dashboard → Appearance as the clinic published it (GET /v1/widget/config/<clinic>; null: the built-in look).
export interface Appearance {
  look: {
    name: string;
    avatar_letter: string;
    logo: string;
    location: string;
    tagline: string;
    header_arc: boolean;
    enabled: boolean;
  };
  colours: Record<
    | 'main'
    | 'main_dark'
    | 'accent'
    | 'tint'
    | 'highlight'
    | 'surface'
    | 'line'
    | 'text'
    | 'muted'
    | 'whatsapp'
    | 'dark_page'
    | 'dark_card'
    | 'dark_text'
    | 'dark_line',
    string
  > & { dark_mode: boolean };
  widget: {
    size: 'small' | 'medium' | 'large';
    radius: 'square' | 'rounded' | 'round';
    border: Level;
    shadow: 'none' | 'soft' | 'strong';
    font: 'Figtree' | 'Inter' | 'System';
    footer_on: boolean;
    footer_text: string;
    footer_link: string;
    mobile_contact_row: boolean;
    contact_buttons: ('call' | 'book' | 'whatsapp')[];
  };
  launcher: {
    position: 'bottom_right' | 'bottom_left';
    offset_x: number;
    offset_y: number;
    background: string;
    icon_color: string;
    label_on: boolean;
    label_text: string;
    label_after_s: number;
    mobile_offset_x: number;
    mobile_offset_y: number;
    shape: 'pill' | 'rounded' | 'circle';
    size: 'small' | 'medium' | 'large';
    border: Level;
    icon: 'chat' | 'logo';
    notification_dot: boolean;
    opens_as: 'panel' | 'full';
    open_on_first_visit: boolean;
    mobile_label: boolean;
  };
}
type Level = 'none' | 'subtle' | 'strong';
