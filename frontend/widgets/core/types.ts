// Widget and backend contract (README "Widget and backend contract").

export type ChatEvent = 'start' | 'text' | 'button' | 'input' | 'restart';

export type UiType =
  | 'menu'
  | 'chips'
  | 'phone'
  | 'email'
  | 'month_calendar'
  | 'week_strip'
  | 'time_grid'
  | 'doctor_carousel'
  | 'doctor_card'
  | 'treatment_card'
  | 'summary'
  | 'link_buttons'
  | 'emergency'
  | 'status_line';

export type InputMode = 'text' | 'phone' | 'email' | 'none';

export interface ChatRequest {
  client_id: string;
  session_id: string;
  visitor_id: string;
  event: ChatEvent;
  payload: { action?: string; value?: unknown; text?: string };
  context: { page_url: string; device: 'mobile' | 'desktop'; lang: 'en' };
}

export interface BotMessage {
  type: 'text';
  text: string;
}

export interface UiBlock {
  type: UiType;
  [key: string]: unknown;
}

export interface ChatResponse {
  messages: BotMessage[];
  ui?: UiBlock | null;
  input: { mode: InputMode; placeholder?: string };
  quick?: string[];
}

// Per-clinic settings served by the config API (dynamic JSON in Supabase). Filled in Step 7.
export interface WidgetConfig {
  client_id: string;
  bot_name: string;
  [key: string]: unknown;
}
