// Entry for the full widget (<id>.app.js). Picks up the handle the loader created and renders into it.
import { render } from 'preact';
import { useEffect, useState } from 'preact/hooks';
import baseCss from './styles/base.css?inline';
import { injectStyles } from './shadow';
import { getHandle, type WidgetHandle } from './registry';
import { createApi } from './api';
import { getVisitorId, getSession } from './session';
import t from './i18n/en.json';

export interface Face {
  clinicId: string;
  botName: string;
}

function Widget({ handle, face }: { handle: WidgetHandle; face: Face }) {
  const [open, setOpen] = useState(handle.isOpen);

  useEffect(() => {
    handle.onOpenChange = setOpen;
    return () => {
      handle.onOpenChange = undefined;
    };
  }, [handle]);

  if (!open) return null;
  // Step 2 placeholder panel. Step 3 replaces it with the header, message list, typing bar and footer.
  return (
    <div role="dialog" aria-label={`${face.botName} chat`} class="nb-panel-placeholder">
      <b>{face.botName}</b> <span>{t.subtitle}</span>
    </div>
  );
}

export function mountApp(face: Face) {
  const handle = getHandle(face.clinicId);
  if (!handle) {
    console.warn(`[neo-widget] loader for ${face.clinicId} not found`);
    return;
  }
  injectStyles(handle.shadow, baseCss);
  // Created here so later steps can use them; nothing is sent until Step 5.
  createApi(handle.apiBase, face.clinicId);
  getVisitorId();
  getSession(face.clinicId);
  render(<Widget handle={handle} face={face} />, handle.mountPoint);
}
