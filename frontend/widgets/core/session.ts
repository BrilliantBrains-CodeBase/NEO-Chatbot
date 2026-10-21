// visitor_id and session_id only. No personal data is ever stored in the browser.

const VISITOR_KEY = 'neo_vid';
const SESSION_IDLE_MS = 30 * 60 * 1000;

function randomId(prefix: string) {
  // 16 bytes (128 bits), so ids stay unique across many visitors. randomUUID needs HTTPS, this does not.
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return prefix + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

// Storage can throw (private mode, blocked site data), so the widget must work without it.
function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore, ids then last for this page view only
  }
}

function remove(key: string) {
  try {
    localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

export function getVisitorId(): string {
  let id = read(VISITOR_KEY);
  if (!id) {
    id = randomId('v_');
    write(VISITOR_KEY, id);
  }
  return id;
}

const sessionKey = (clinicId: string) => `neo_sid_${clinicId}`;

// Same session after a page reload; a new one after 30 minutes without activity.
export function getSession(clinicId: string): { id: string; isNew: boolean } {
  try {
    const saved = JSON.parse(read(sessionKey(clinicId)) || 'null') as { id: string; t: number } | null;
    if (saved && Date.now() - saved.t < SESSION_IDLE_MS) {
      touchSession(clinicId, saved.id);
      return { id: saved.id, isNew: false };
    }
  } catch {
    // corrupt value, start a new session
  }
  const id = randomId('s_');
  touchSession(clinicId, id);
  return { id, isNew: true };
}

export function touchSession(clinicId: string, id: string) {
  write(sessionKey(clinicId), JSON.stringify({ id, t: Date.now() }));
}

export function resetSession(clinicId: string): string {
  remove(sessionKey(clinicId));
  return getSession(clinicId).id;
}
