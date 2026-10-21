// Entry for the full widget (<id>.app.js). Picks up the handle the loader created and renders into it.
import { render } from 'preact';
import { useCallback, useEffect, useRef, useState } from 'preact/hooks';
import baseCss from './styles/base.css?inline';
import { injectStyles } from './shadow';
import { getHandle, type WidgetHandle } from './registry';
import { ApiError, createApi, type Api } from './api';
import { getVisitorId, getSession } from './session';
import type { ChatEvent, ChatRequest } from './types';
import { Panel } from './components/Panel';
import { Messages, type Entry } from './components/Messages';
import t from './i18n/en.json';

export interface Face {
  clinicId: string;
  botName: string;
}

const isMobile = () => matchMedia('(max-width: 640px)').matches;

function Widget({ handle, face, api }: { handle: WidgetHandle; face: Face; api: Api }) {
  const [open, setOpen] = useState(handle.isOpen);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [busy, setBusy] = useState(false);
  const nextId = useRef(0);
  const started = useRef(false);
  // The last request, so "Try again" can send it once more.
  const last = useRef<{ event: ChatEvent; payload: ChatRequest['payload'] } | null>(null);
  const close = useCallback(() => handle.setOpen(false), [handle]);

  useEffect(() => {
    handle.onOpenChange = setOpen;
    return () => {
      handle.onOpenChange = undefined;
    };
  }, [handle]);

  const add = (from: Entry['from'], text: string, error?: boolean) =>
    setEntries((list) => [...list, { id: nextId.current++, from, text, error }]);

  const send = useCallback(
    async (event: ChatEvent, payload: ChatRequest['payload'] = {}) => {
      last.current = { event, payload };
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
        res.messages.forEach((m) => add('bot', m.text));
      } catch (err) {
        // The API client has already retried server and network errors.
        console.warn('[neo-widget]', err);
        const offline = err instanceof ApiError && err.kind === 'offline';
        add('bot', offline ? t.error_offline : t.error_generic, true);
      } finally {
        setBusy(false);
      }
    },
    [api, face.clinicId],
  );

  const retry = useCallback(() => {
    if (!last.current) return;
    setEntries((list) => list.filter((e) => !e.error));
    void send(last.current.event, last.current.payload);
  }, [send]);

  // The first open of this page view starts (or resumes) the conversation.
  useEffect(() => {
    if (open && !started.current) {
      started.current = true;
      void send('start');
    }
  }, [open, send]);

  // The widget stays mounted while closed, so the conversation is kept when the patient reopens it.
  if (!open) return null;
  return (
    <Panel botName={face.botName} onClose={close}>
      <Messages entries={entries} busy={busy} onRetry={retry} />
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
