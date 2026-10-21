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

  // A reply's block goes into the conversation too. The main menu sits above the greeting (approved mockups);
  // every other block sits under the text it belongs to.
  const addReply = (res: ChatResponse) => {
    const texts: Entry[] = res.messages.map((m) => ({ id: nextId.current++, from: 'bot', text: m.text }));
    const ui: Entry[] = res.ui ? [{ id: nextId.current++, from: 'ui', block: res.ui }] : [];
    setEntries((list) => [...list, ...(res.ui?.type === 'menu' ? [...ui, ...texts] : [...texts, ...ui])]);
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
      botName={face.botName}
      onClose={close}
      onRestart={restart}
      composer={<Composer mode={mode} placeholder={placeholder} busy={busy} onSend={type} />}
    >
      <Messages entries={entries} busy={busy} onRetry={retry} onChoose={choose} />
    </Panel>
  );
}

// Dev playground only: the mock backend answers unless ?api=<url> points at a real backend.
// import.meta.env.DEV is false in the production build, so the mock is never bundled.
function devFetch(): typeof fetch | undefined {
  if (import.meta.env.DEV && !new URLSearchParams(location.search).has('api')) {
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
  injectStyles(handle.shadow, baseCss);
  const apiBase = (import.meta.env.DEV && new URLSearchParams(location.search).get('api')) || handle.apiBase;
  const api = createApi(apiBase, face.clinicId, { fetchImpl: devFetch() });
  render(<Widget handle={handle} face={face} api={api} />, handle.mountPoint);
}
