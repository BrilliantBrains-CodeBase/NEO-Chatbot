// The visible chat, kept on the patient's device so it survives a reload or a move to another page.
// Kept for 3 days after the last message (client decision), then dropped. Restart clears it.
import type { Entry } from './components/Messages';

const TTL_MS = 3 * 24 * 60 * 60 * 1000;
const MAX_ENTRIES = 200;
const key = (clinicId: string) => `neo_chat_${clinicId}`;

// Storage can throw (private mode, blocked site data); the chat then simply is not kept.
export function loadHistory(clinicId: string): Entry[] {
  try {
    const saved = JSON.parse(localStorage.getItem(key(clinicId)) || 'null') as {
      t: number;
      entries: Entry[];
    } | null;
    if (saved && Date.now() - saved.t < TTL_MS && Array.isArray(saved.entries)) return saved.entries;
    localStorage.removeItem(key(clinicId));
  } catch {
    // corrupt or blocked: start empty
  }
  return [];
}

export function saveHistory(clinicId: string, entries: Entry[]) {
  // Error bubbles are not kept; their "Try again" would resend an old request.
  const keep = entries.filter((e) => e.from === 'ui' || !e.error).slice(-MAX_ENTRIES);
  try {
    if (keep.length) localStorage.setItem(key(clinicId), JSON.stringify({ t: Date.now(), entries: keep }));
    else localStorage.removeItem(key(clinicId));
  } catch {
    // ignore: the chat is kept for this page view only
  }
}
