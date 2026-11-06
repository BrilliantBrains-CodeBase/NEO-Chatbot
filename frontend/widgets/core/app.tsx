// Entry for the full widget (<id>.app.js). Picks up the handle the loader created and renders into it.
import { render } from 'preact';
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import baseCss from './styles/base.css?inline';
import { injectStyles } from './shadow';
import { getHandle, type WidgetHandle } from './registry';
import { ApiError, createApi, type Api } from './api';
import { getVisitorId, getSession, resetSession } from './session';
import type { ChatEvent, ChatRequest, ChatResponse, Choice, InputMode } from './types';
import { Panel } from './components/Panel';
import { Messages, type Entry } from './components/Messages';
import { Composer } from './components/Composer';
import { setMenuTemplate } from './components/Blocks';
import { ContactRow } from './components/ContactRow';
import { loadHistory, saveHistory } from './history';
import t from './i18n/en.json';

export interface Face {
  clinicId: string;
  botName: string;
}

const isMobile = () => matchMedia('(max-width: 640px)').matches;

function Widget({ handle, face, api }: { handle: WidgetHandle; face: Face; api: Api }) {
  const [open, setOpen] = useState(handle.isOpen);
  // The chat from the last 3 days on this device, if any (reload, another page of the site).
  const [entries, setEntries] = useState<Entry[]>(() => loadHistory(face.clinicId));
  const [busy, setBusy] = useState(false);
  const [placeholder, setPlaceholder] = useState(t.placeholder);
  const [mode, setMode] = useState<InputMode>('text');
  const nextId = useRef(entries.reduce((max, e) => Math.max(max, e.id + 1), 0));
  const restored = useRef(true);
  const started = useRef(false);
  // The last request, so "Try again" can send it once more.
  const last = useRef<{ event: ChatEvent; payload: ChatRequest['payload'] } | null>(null);
  // Bumped by restart, so a reply still on its way for the old conversation is dropped.
  const generation = useRef(0);
  const close = useCallback(() => handle.setOpen(false), [handle]);

  useEffect(() => {
    handle.onOpenChange = setOpen;
    return () => {
      handle.onOpenChange = undefined;
    };
  }, [handle]);

  const add = (from: 'bot' | 'me', text: string, error?: boolean) =>
    setEntries((list) => [...list, { id: nextId.current++, from, text, error }]);

  // A reply's block goes into the conversation too, under the text it belongs to
  // (the greeting sits above the main menu).
  const addReply = (res: ChatResponse) => {
    const texts: Entry[] = res.messages.map((m) => ({ id: nextId.current++, from: 'bot', text: m.text }));
    const ui: Entry[] = res.ui ? [{ id: nextId.current++, from: 'ui', block: res.ui }] : [];
    setEntries((list) => [...list, ...texts, ...ui]);
  };

  const send = useCallback(
    async (event: ChatEvent, payload: ChatRequest['payload'] = {}) => {
      last.current = { event, payload };
      const gen = generation.current;
      setBusy(true);
      try {
        const res = await api.send({
          client_id: face.clinicId,
          session_id: getSession(face.clinicId).id,
          visitor_id: getVisitorId(),
          event,
          payload,
          context: { page_url: location.href, device: isMobile() ? 'mobile' : 'desktop', lang: 'en' },
        });
        if (gen !== generation.current) return;
        addReply(res);
        setPlaceholder(res.input.placeholder || t.placeholder);
        setMode(res.input.mode);
      } catch (err) {
        if (gen !== generation.current) return;
        // The API client has already retried server and network errors.
        console.warn('[neo-widget]', err);
        const offline = err instanceof ApiError && err.kind === 'offline';
        add('bot', offline ? t.error_offline : t.error_generic, true);
      } finally {
        if (gen === generation.current) setBusy(false);
      }
    },
    [api, face.clinicId],
  );

  const retry = useCallback(() => {
    if (!last.current) return;
    setEntries((list) => list.filter((e) => e.from === 'ui' || !e.error));
    void send(last.current.event, last.current.payload);
  }, [send]);

  // Typed text: shown as the patient's bubble, then sent. A phone number carries its country code.
  const type = useCallback(
    (text: string, cc?: string) => {
      add('me', cc ? `${cc} ${text}` : text);
      void send('text', cc ? { text, cc } : { text });
    },
    [send],
  );

  // A tapped button: its label shows as the patient's bubble, then the choice is sent.
  const choose = useCallback(
    (choice: Choice) => {
      if (busy) return;
      add('me', choice.label);
      void send('button', { action: choice.action, value: choice.value });
    },
    [busy, send],
  );

  // Header restart: a new session and a fresh conversation.
  const restart = useCallback(() => {
    generation.current++;
    resetSession(face.clinicId);
    setEntries([]);
    setPlaceholder(t.placeholder);
    setMode('text');
    void send('restart');
  }, [face.clinicId, send]);

  // Keep the chat on this device. Skipped for the restored chat itself, so loading a page does not
  // extend the 3 days; only a new message does.
  useEffect(() => {
    if (restored.current) {
      restored.current = false;
      return;
    }
    saveHistory(face.clinicId, entries);
  }, [entries, face.clinicId]);

  // The first open of this page view starts the conversation. A chat restored within the same session
  // carries on as it was; after the session has expired the bot greets again under the old messages.
  useEffect(() => {
    if (open && !started.current) {
      started.current = true;
      if (!entries.length || getSession(face.clinicId).isNew) void send('start');
    }
  }, [open, send, entries.length, face.clinicId]);

  // The widget stays mounted while closed, so the conversation is kept when the patient reopens it.
  if (!open) return null;
  return (
    <Panel
      botName={handle.appearance?.look.name || face.botName}
      appearance={handle.appearance}
      onClose={close}
      onRestart={restart}
      composer={
        <>
          {handle.appearance?.widget.mobile_contact_row && (
            <ContactRow
              buttons={handle.appearance.widget.contact_buttons}
              contact={handle.contact}
              onChoose={choose}
            />
          )}
          <Composer mode={mode} placeholder={placeholder} busy={busy} onSend={type} />
        </>
      }
    >
      <Messages entries={entries} busy={busy} onRetry={retry} onChoose={choose} />
    </Panel>
  );
}

// Dev playground only: the local real backend (http://127.0.0.1:8000) answers, or ?api=<url>; ?mock uses the
// mock backend instead (no database: no knowledge base, phrases or reviews).
// Preview build (npm run build:preview): the mock is bundled so the widget can be tried on a real page
// with no backend; nothing is saved. Both flags are false in the production build, so the mock is never
// bundled there.
const DEV_API = 'http://127.0.0.1:8000';
// Clinics the real backend has content for; the others use the mock until theirs is built.
const ON_BACKEND = ['NFHT', 'DS', 'NF', 'NS6'];
function devFetch(clinicId: string): typeof fetch | undefined {
  const q = new URLSearchParams(location.search);
  const mock = import.meta.env.DEV
    ? q.has('mock') || (!q.has('api') && !ON_BACKEND.includes(clinicId))
    : import.meta.env.VITE_PREVIEW === '1';
  if (mock) {
    const mock = import('../mock/fetch');
    return (input, init) => mock.then((m) => m.mockFetch(input, init));
  }
  return undefined;
}

export function mountApp(face: Face) {
  const handle = getHandle(face.clinicId);
  if (!handle) {
    console.warn(`[neo-widget] loader for ${face.clinicId} not found`);
    return;
  }
  injectStyles(handle.shadow, baseCss + handle.lookCss);
  setMenuTemplate(handle.template);
  const params = new URLSearchParams(location.search);
  const apiBase = import.meta.env.DEV ? params.get('api') || DEV_API : handle.apiBase;
  const api = createApi(apiBase, { fetchImpl: devFetch(face.clinicId) });
  render(<Widget handle={handle} face={face} api={api} />, handle.mountPoint);
}
